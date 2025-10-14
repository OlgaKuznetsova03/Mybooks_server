from __future__ import annotations

import json
import logging
from datetime import timedelta

from django.db.models import (
    Q,
    F,
    Min,
    Max,
    Prefetch,
    Case,
    When,
    OuterRef,
    Subquery,
    Avg,
    Count,
)
from typing import Optional
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import mark_safe
from django.utils.text import slugify
from django.views.decorators.http import require_GET, require_POST
from shelves.forms import HomeLibraryQuickAddForm
from shelves.models import BookProgress, ShelfItem, HomeLibraryEntry, ProgressAnnotation
from shelves.services import (
    DEFAULT_READ_SHELF,
    DEFAULT_READING_SHELF,
    DEFAULT_WANT_SHELF,
    get_home_library_shelf,
    move_book_to_read_shelf,
)
from games.services.read_before_buy import ReadBeforeBuyGame
from user_ratings.services import award_for_review
from reading_clubs.models import ReadingClub
from .models import Author, Book, Genre, Rating, ISBNModel
from .forms import BookForm, RatingForm
from .services import EditionRegistrationResult, register_book_edition
from .api_clients import google_books_client
from .utils import normalize_isbn


logger = logging.getLogger(__name__)


def _isbn_query(value: Optional[str]) -> str:
    return normalize_isbn(value)


def _book_cover_url(book: Book) -> str:
    """Вернуть URL обложки для отображения в подборках."""

    return book.get_cover_url()


SHELF_BOOKS_LIMIT = 12


def _serialize_book_for_shelf(
    book: Book, *, extra: dict[str, object] | None = None
) -> dict[str, object]:
    if (
        hasattr(book, "_prefetched_objects_cache")
        and "authors" in book._prefetched_objects_cache
    ):
        authors_qs = book._prefetched_objects_cache["authors"]
        authors = [author.name for author in authors_qs if author.name]
    else:
        authors = list(
            book.authors.order_by("name").values_list("name", flat=True)
        )

    title = (book.title or "").strip()

    data: dict[str, object] = {
        "id": book.pk,
        "title": title,
        "detail_url": reverse("book_detail", args=[book.pk]),
        "cover_url": _book_cover_url(book),
        "authors": authors,
        "average_rating": getattr(book, "average_rating", None),
        "rating_count": int(getattr(book, "rating_count", 0) or 0),
        "initial": (title[:1] or "?").upper(),
    }

    if extra:
        data.update(extra)

    return data


def _russian_plural(value: int, forms: tuple[str, str, str]) -> str:
    """Return the correct Russian plural form for ``value``."""

    number = abs(int(value))
    if number % 10 == 1 and number % 100 != 11:
        return forms[0]
    if 2 <= number % 10 <= 4 and not (12 <= number % 100 <= 14):
        return forms[1]
    return forms[2]


def _matching_books_for_isbns(isbn_values: list[str]) -> list[dict[str, object]]:
    """Найти книги на сайте, которые содержат указанные ISBN."""

    normalized = [normalize_isbn(value) for value in isbn_values if normalize_isbn(value)]
    if not normalized:
        return []

    isbn_filter = Q()
    for value in normalized:
        isbn_filter |= Q(isbn__iexact=value) | Q(isbn13__iexact=value)

    if not isbn_filter.children:
        return []

    matched_isbns = ISBNModel.objects.filter(isbn_filter)
    if not matched_isbns.exists():
        return []

    books = (
        Book.objects.filter(isbn__in=matched_isbns)
        .distinct()
        .prefetch_related("isbn")
    )

    matches: list[dict[str, object]] = []
    for book in books:
        book_matches = set()
        for isbn_instance in book.isbn.filter(isbn_filter):
            if isbn_instance.isbn and normalize_isbn(isbn_instance.isbn) in normalized:
                book_matches.add(isbn_instance.isbn)
            if isbn_instance.isbn13 and normalize_isbn(isbn_instance.isbn13) in normalized:
                book_matches.add(isbn_instance.isbn13)

        matches.append(
            {
                "id": book.pk,
                "title": book.title,
                "detail_url": reverse("book_detail", args=[book.pk]),
                "edition_count": book.isbn.count(),
                "cover_url": _book_cover_url(book),
                "matching_isbns": sorted(book_matches),
            }
        )
    return matches


def _serialize_external_item(item) -> dict[str, object]:
    metadata = item.to_metadata_mapping()
    combined_isbns = item.combined_isbns()
    return {
        "title": item.title,
        "subtitle": item.subtitle,
        "authors": item.authors,
        "publishers": item.publishers,
        "publish_date": item.publish_date,
        "number_of_pages": item.number_of_pages,
        "physical_format": item.physical_format,
        "subjects": item.subjects,
        "languages": item.languages,
        "description": item.description,
        "cover_url": item.cover_url,
        "source_url": item.source_url,
        "isbn_list": combined_isbns,
        "metadata": metadata,
        "matching_editions": _matching_books_for_isbns(combined_isbns),
    }


@login_required
@require_GET
def book_lookup(request):
    title = (request.GET.get("title") or "").strip()
    author = (request.GET.get("author") or "").strip()
    isbn_raw = request.GET.get("isbn")
    isbn = _isbn_query(isbn_raw)
    force_external = str(request.GET.get("force_external", "")).lower() in {"1", "true", "yes"}

    if not any([title, author, isbn]):
        return JsonResponse({"error": "Укажите название, автора или ISBN."}, status=400)

    qs = Book.objects.all().prefetch_related("authors", "isbn")
    if title:
        qs = qs.filter(title__icontains=title)
    if author:
        qs = qs.filter(authors__name__icontains=author)
    if isbn:
        qs = qs.filter(Q(isbn__isbn__iexact=isbn) | Q(isbn__isbn13__iexact=isbn))

    local_results = []
    for book in qs.distinct()[:10]:
        isbn_values = list(book.isbn.values("isbn", "isbn13"))
        isbn_candidates = []
        for entry in isbn_values:
            primary = normalize_isbn(entry.get("isbn")) if entry.get("isbn") else ""
            secondary = normalize_isbn(entry.get("isbn13")) if entry.get("isbn13") else ""
            isbn_candidates.extend([primary, secondary])
        seen_isbns = []
        for candidate in isbn_candidates:
            if candidate and candidate not in seen_isbns:
                seen_isbns.append(candidate)
        local_results.append({
            "id": book.pk,
            "title": book.title,
            "authors": list(book.authors.order_by("name").values_list("name", flat=True)),
            "isbn_list": seen_isbns,
            "detail_url": reverse("book_detail", args=[book.pk]),
            "edition_count": len(isbn_values),
        })

    external_results = []
    external_error = None
    if force_external or not local_results:
        try:
            search_results = google_books_client.search(
                title=title or None,
                author=author or None,
                isbn=isbn or None,
                limit=5,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Google Books lookup failed: %s", exc)
            search_results = []
            external_error = "Не удалось получить данные от Google Books. Попробуйте позже."

        for item in search_results:
            external_results.append(_serialize_external_item(item))

    return JsonResponse(
        {
            "query": {"title": title, "author": author, "isbn": isbn, "raw_isbn": isbn_raw},
            "local_results": local_results,
            "external_results": external_results,
            "external_error": external_error,
            "force_external": force_external,
        }
    )

@login_required
@require_POST
def book_prefill_external(request):
    payload = request.POST.get("payload")
    redirect_url = reverse("book_create")
    if not payload:
        messages.error(request, "Не удалось подготовить данные книги. Попробуйте ещё раз.")
        return redirect(redirect_url)

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        messages.error(request, "Получены повреждённые данные из внешнего поиска.")
        return redirect(redirect_url)

    request.session["book_prefill"] = data
    return redirect(redirect_url)


def _find_books_with_same_title_and_authors(title, authors):
    """Вернуть книги, у которых совпадает название и состав авторов."""

    normalized_title = (title or "").strip()
    if not normalized_title or not authors:
        return []

    author_ids = {author.id for author in authors if author.id is not None}
    if not author_ids:
        return []

    candidates = (
        Book.objects.filter(title__iexact=normalized_title)
        .prefetch_related("authors", "isbn", "publisher")
    )

    matches = []
    for book in candidates:
        existing_author_ids = set(book.authors.values_list("id", flat=True))
        if existing_author_ids == author_ids:
            matches.append(book)
    return matches


def _notify_about_registration(request, result: EditionRegistrationResult) -> None:
    if result.created:
        messages.success(request, "Книга успешно добавлена.")
    elif result.added_isbns:
        messages.success(request, "Новое издание добавлено к существующей книге.")
    else:
        messages.info(
            request,
            "Книга уже была на сайте. Мы обновили связанные данные издания.",
        )


def book_list(request):
    q = (request.GET.get("q") or "").strip()
    view_mode = (request.GET.get("view") or "discover").lower()
    if q:
        view_mode = "grid"
    if view_mode not in {"grid", "discover"}:
        view_mode = "discover"

    active_sort = (request.GET.get("sort") or "popular").lower()

    base_qs = (
        Book.objects.all()
        .select_related("audio")
        .prefetch_related("authors", "genres", "publisher", "isbn")
    )

    group_leader_subquery = (
        Book.objects.filter(edition_group_key=OuterRef("edition_group_key"))
        .order_by("pk")
        .values("pk")[:1]
    )

    annotated_books = base_qs.annotate(
        edition_leader=Case(
            When(edition_group_key="", then=F("pk")),
            default=Subquery(group_leader_subquery),
        ),
        average_rating=Avg("ratings__score"),
        rating_count=Count("ratings__score"),
    ).filter(pk=F("edition_leader"))

    total_books = annotated_books.count()

    sort_definitions = {
        "popular": {
            "label": "Популярные",
            "icon": "bi-fire",
            "order": ("-rating_count", "-average_rating", "title"),
        },
        "rating": {
            "label": "Высокий рейтинг",
            "icon": "bi-star-fill",
            "order": ("-average_rating", "-rating_count", "title"),
        },
        "recent": {
            "label": "Недавно добавлены",
            "icon": "bi-clock-history",
            "order": ("-created_at", "-pk"),
        },
        "title": {
            "label": "По алфавиту",
            "icon": "bi-sort-alpha-down",
            "order": ("title",),
        },
    }

    if active_sort not in sort_definitions:
        active_sort = "popular"

    page_obj = None
    sort_options: list[dict[str, object]] = []
    external_suggestions: list[dict[str, object]] = []
    external_error = None
    discovery_shelves: list[dict[str, object]] = []

    if view_mode == "grid":
        qs = annotated_books
        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(authors__name__icontains=q)
                | Q(genres__name__icontains=q)
            ).distinct()

        qs = qs.order_by(*sort_definitions[active_sort]["order"])

        paginator = Paginator(qs, 12)
        page = request.GET.get("page")
        page_obj = paginator.get_page(page)

        preserved_query = request.GET.copy()
        preserved_query._mutable = True
        preserved_query.pop("page", None)
        preserved_query["view"] = "grid"

        for key, definition in sort_definitions.items():
            params = preserved_query.copy()
            params["sort"] = key
            sort_options.append(
                {
                    "key": key,
                    "label": definition["label"],
                    "icon": definition["icon"],
                    "url": f"?{params.urlencode()}",
                }
            )

        if q and page_obj.paginator.count == 0:
            isbn_candidate = normalize_isbn(q)
            title_query = q if len(isbn_candidate) not in (10, 13) else ""
            try:
                results = google_books_client.search(
                    title=title_query or None,
                    isbn=isbn_candidate or None,
                    limit=6,
                )
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Google Books search for list failed: %s", exc)
                results = []
                external_error = "Не удалось получить данные из Google Books. Попробуйте позже."

            for item in results:
                serialized = _serialize_external_item(item)
                payload = {
                    "query": {"title": q, "author": "", "isbn": isbn_candidate},
                    "external_result": serialized,
                }
                external_suggestions.append(
                    {
                        "data": serialized,
                        "payload": json.dumps(payload, ensure_ascii=False),
                    }
                )
    else:
        now = timezone.now()
        recent_cutoff = now - timedelta(days=10)
        recent_books = list(
            annotated_books.filter(created_at__gte=recent_cutoff)
            .order_by("-created_at", "-pk")[:SHELF_BOOKS_LIMIT]
        )
        if not recent_books and total_books:
            recent_books = list(
                annotated_books.order_by("-created_at", "-pk")[:SHELF_BOOKS_LIMIT]
            )
        if recent_books:
            discovery_shelves.append(
                {
                    "title": "Недавно добавленные",
                    "subtitle": "Свежие книги за последние 10 дней.",
                    "variant": "profile",
                    "texture_url": None,
                    "cta": {
                        "url": "?view=grid&sort=recent",
                        "label": "Все новинки",
                    },
                    "books": [
                        _serialize_book_for_shelf(
                            book,
                            extra={
                                "added_at": getattr(book, "created_at", None),
                            },
                        )
                        for book in recent_books
                    ],
                }
            )

        popular_window = now - timedelta(days=30)
        popular_stats = list(
            BookProgress.objects.filter(updated_at__gte=popular_window)
            .values("book")
            .annotate(reader_count=Count("user", distinct=True))
            .order_by("-reader_count", "book")[: SHELF_BOOKS_LIMIT * 3]
        )

        popular_ids = [entry["book"] for entry in popular_stats if entry["book"]]
        if popular_ids:
            popular_books_qs = (
                annotated_books.filter(pk__in=popular_ids)
                .annotate(
                    recent_reader_count=Count(
                        "bookprogress__user",
                        filter=Q(bookprogress__updated_at__gte=popular_window),
                        distinct=True,
                    )
                )
            )
            popular_book_map = {book.pk: book for book in popular_books_qs}
            ordered_popular_books = [
                popular_book_map[pk]
                for pk in popular_ids
                if pk in popular_book_map
            ][:SHELF_BOOKS_LIMIT]
            if ordered_popular_books:
                discovery_shelves.append(
                    {
                        "title": "Популярные сейчас",
                        "subtitle": "Больше всего читателей за последние 30 дней.",
                        "variant": "profile",
                        "texture_url": None,
                        "cta": {
                            "url": "?view=grid&sort=popular",
                            "label": "Открыть каталог",
                        },
                        "books": [
                            _serialize_book_for_shelf(
                                book,
                                extra={
                                    "reader_count": int(
                                        getattr(book, "recent_reader_count", 0) or 0
                                    ),
                                },
                            )
                            for book in ordered_popular_books
                        ],
                    }
                )

        popular_genres = list(
            Genre.objects.annotate(
                recent_reader_count=Count(
                    "books__bookprogress__user",
                    filter=Q(books__bookprogress__updated_at__gte=popular_window),
                    distinct=True,
                )
            )
            .filter(recent_reader_count__gt=0)
            .order_by("-recent_reader_count", "name")[:4]
        )

        for genre in popular_genres:
            top_books = list(
                annotated_books.filter(genres=genre)
                .annotate(
                    recent_reader_count=Count(
                        "bookprogress__user",
                        filter=Q(bookprogress__updated_at__gte=popular_window),
                        distinct=True,
                    )
                )
                .order_by("-recent_reader_count", "-rating_count", "title")
                .distinct()[:SHELF_BOOKS_LIMIT]
            )
            if not top_books:
                continue

            genre_reader_count = int(
                getattr(genre, "recent_reader_count", 0) or 0
            )
            if genre_reader_count:
                subtitle = (
                    f"{genre_reader_count} "
                    f"{_russian_plural(genre_reader_count, ('читатель', 'читателя', 'читателей'))} за 30 дней"
                )
            else:
                subtitle = "Популярный жанр сообщества."

            discovery_shelves.append(
                {
                    "title": genre.name,
                    "subtitle": subtitle,
                    "variant": "profile",
                    "texture_url": None,
                    "cta": {
                        "url": genre.get_absolute_url(),
                        "label": "Все книги жанра",
                    },
                    "books": [
                        _serialize_book_for_shelf(
                            book,
                            extra={
                                "reader_count": int(
                                    getattr(book, "recent_reader_count", 0) or 0
                                ),
                            },
                        )
                        for book in top_books
                    ],
                }
            )

    return render(
        request,
        "books/books_list.html",
        {
            "page_obj": page_obj,
            "q": q,
            "active_sort": active_sort,
            "sort_options": sort_options,
            "external_suggestions": external_suggestions,
            "external_error": external_error,
            "total_books": total_books,
            "view_mode": view_mode,
            "discovery_shelves": discovery_shelves,
        },
    )


def genre_detail(request, slug):
    genre = get_object_or_404(Genre, slug=slug)

    base_qs = (
        genre.books.prefetch_related(
            Prefetch("authors", queryset=Author.objects.order_by("name"))
        )
        .annotate(
            average_rating=Avg("ratings__score"),
            rating_count=Count("ratings__score"),
        )
    )

    total_books = base_qs.count()

    shelves: list[dict[str, object]] = []

    popular_selection = list(
        base_qs.order_by("-rating_count", "-average_rating", "title")[
            :SHELF_BOOKS_LIMIT
        ]
    )
    if popular_selection:
        shelves.append(
            {
                "title": "Популярное",
                "subtitle": "Читатели выбирают чаще всего.",
                "variant": None,
                "texture_url": None,
                "cta": None,
                "books": [
                    _serialize_book_for_shelf(book)
                    for book in popular_selection
                ],
            }
        )

    top_rated_selection = list(
        base_qs.filter(average_rating__isnull=False)
        .order_by("-average_rating", "-rating_count", "title")[:SHELF_BOOKS_LIMIT]
    )
    if top_rated_selection:
        shelves.append(
            {
                "title": "С высоким рейтингом",
                "subtitle": "Лучшие оценки сообщества ReadTogether.",
                "variant": None,
                "texture_url": None,
                "cta": None,
                "books": [
                    _serialize_book_for_shelf(book)
                    for book in top_rated_selection
                ],
            }
        )

    newest_selection = list(base_qs.order_by("-pk")[:SHELF_BOOKS_LIMIT])
    if newest_selection:
        shelves.append(
            {
                "title": "Недавно добавлены",
                "subtitle": "Свежие истории в этом жанре.",
                "variant": None,
                "texture_url": None,
                "cta": None,
                "books": [
                    _serialize_book_for_shelf(book)
                    for book in newest_selection
                ],
            }
        )

    other_genres = (
        Genre.objects.exclude(pk=genre.pk)
        .annotate(book_count=Count("books", distinct=True))
        .filter(book_count__gt=0)
        .order_by("-book_count", "name")[:12]
    )

    return render(
        request,
        "books/genre_detail.html",
        {
            "genre": genre,
            "shelves": shelves,
            "total_books": total_books,
            "other_genres": other_genres,
        },
    )

def book_detail(request, pk):
    book = get_object_or_404(
        Book.objects.prefetch_related(
            Prefetch("authors", queryset=Author.objects.order_by("name")),
            "genres",
            "publisher",
            "ratings__user",
            Prefetch("isbn", queryset=ISBNModel.objects.prefetch_related("authors")),
        ),
        pk=pk
    )
    ratings = book.ratings.select_related("user").order_by("-id")  # последние сверху
    rating_summary = book.get_rating_summary()

    home_library_form: HomeLibraryQuickAddForm | None = None
    home_library_item: ShelfItem | None = None
    home_library_entry: HomeLibraryEntry | None = None
    home_library_edit_url: str | None = None
    default_shelf_status: dict[str, object] | None = None

    if request.user.is_authenticated:
        home_library_shelf = get_home_library_shelf(request.user)
        home_library_item = (
            ShelfItem.objects
            .filter(shelf=home_library_shelf, book=book)
            .select_related("home_entry")
            .first()
        )
        home_library_entry = getattr(home_library_item, "home_entry", None) if home_library_item else None
        if home_library_item and home_library_entry is None:
            home_library_entry = HomeLibraryEntry.objects.filter(shelf_item=home_library_item).first()

        is_home_library_action = request.method == "POST" and request.POST.get("action") == "home-library-add"
        if is_home_library_action:
            home_library_form = HomeLibraryQuickAddForm(request.POST)
            if home_library_form.is_valid():
                purchase_date = home_library_form.cleaned_data.get("purchase_date")
                home_library_item, created = ShelfItem.objects.get_or_create(
                    shelf=home_library_shelf,
                    book=book,
                )
                entry, entry_created = HomeLibraryEntry.objects.get_or_create(shelf_item=home_library_item)
                home_library_entry = entry
                updated = False
                if purchase_date and entry.acquired_at != purchase_date:
                    entry.acquired_at = purchase_date
                    entry.save(update_fields=["acquired_at", "updated_at"])
                    updated = True

                if created or entry_created:
                    messages.success(
                        request,
                        f"«{book.title}» добавлена в полку «{home_library_shelf.name}».",
                    )
                elif updated:
                    messages.success(request, "Дата покупки обновлена для этой книги.")
                else:
                    messages.info(
                        request,
                        f"«{book.title}» уже находится на полке «{home_library_shelf.name}».",
                    )
                return redirect("book_detail", pk=book.pk)
        if home_library_form is None:
            initial: dict[str, object] = {}
            if home_library_entry and home_library_entry.acquired_at:
                initial["purchase_date"] = home_library_entry.acquired_at
            home_library_form = HomeLibraryQuickAddForm(initial=initial)
        if home_library_item:
            home_library_edit_url = reverse("home_library_edit", args=[home_library_item.pk])

        default_shelf_items = (
            ShelfItem.objects
            .filter(
                shelf__user=request.user,
                shelf__name__in=[
                    DEFAULT_WANT_SHELF,
                    DEFAULT_READING_SHELF,
                    DEFAULT_READ_SHELF,
                ],
                book=book,
            )
            .select_related("shelf")
        )

        items_by_name = {item.shelf.name: item for item in default_shelf_items}

        if DEFAULT_READ_SHELF in items_by_name:
            item = items_by_name[DEFAULT_READ_SHELF]
            default_shelf_status = {
                "code": "read",
                "label": DEFAULT_READ_SHELF,
                "added_at": item.added_at,
            }
        elif DEFAULT_READING_SHELF in items_by_name:
            item = items_by_name[DEFAULT_READING_SHELF]
            default_shelf_status = {
                "code": "reading",
                "label": DEFAULT_READING_SHELF,
                "added_at": item.added_at,
            }
        elif DEFAULT_WANT_SHELF in items_by_name:
            item = items_by_name[DEFAULT_WANT_SHELF]
            default_shelf_status = {
                "code": "want",
                "label": DEFAULT_WANT_SHELF,
                "added_at": item.added_at,
            }

    form = RatingForm(
        user=request.user if request.user.is_authenticated else None,
        initial={"book": book.pk}
    )

    rating_category_fields = [
        form[field_name]
        for field_name, _ in Rating.get_category_fields()
    ]

    cover_variants = []
    display_primary_isbn_id = book.primary_isbn_id
    requested_edition_id = request.GET.get("edition")
    if requested_edition_id:
        requested_edition_id = requested_edition_id.strip()
        if not requested_edition_id.isdigit():
            requested_edition_id = None

    isbn_entries = list(book.isbn.all())
    isbn_entries.sort(
        key=lambda item: (
            0 if item.pk == book.primary_isbn_id else 1,
            item.pk or 0,
        )
    )

    available_edition_ids = {
        str(isbn.pk)
        for isbn in isbn_entries
        if isbn.pk is not None
    }

    selected_edition_id = None
    if requested_edition_id and requested_edition_id in available_edition_ids:
        selected_edition_id = requested_edition_id

    if not display_primary_isbn_id and isbn_entries:
        display_primary_isbn_id = isbn_entries[0].pk

    if book.cover:
        cover_variants.append({
            "key": "book-cover",
            "image": book.cover.url,
            "alt": f"Обложка книги «{book.title}»",
            "label": "Текущее издание",
            "is_primary": True,
            "is_active": False,
            "edition_id": str(display_primary_isbn_id or ""),
        })

    for isbn in isbn_entries:
        image_url = isbn.get_image_url()
        if not image_url:
            continue

        title = (isbn.title or "").strip()
        isbn_display = isbn.isbn13 or isbn.isbn
        label_parts = []
        if title:
            label_parts.append(title)
        if isbn_display:
            label_parts.append(f"ISBN {isbn_display}")
        label = " · ".join(label_parts) if label_parts else "Дополнительное издание"

        is_primary_isbn = isbn.pk == display_primary_isbn_id
        cover_variants.append({
            "key": f"isbn-{isbn.pk}",
            "image": image_url,
            "alt": f"Обложка издания «{title or book.title}»",
            "label": label,
            "is_primary": is_primary_isbn,
            "is_active": False,
            "edition_id": str(isbn.pk),
            "page_count": isbn.total_pages,
        })

    active_cover = None
    active_cover_edition_id = None
    if selected_edition_id:
        for preferred_key in ("non-primary", "any"):
            for variant in cover_variants:
                if preferred_key == "non-primary" and variant.get("key") == "book-cover":
                    continue
                if variant.get("edition_id") == selected_edition_id and variant.get("image"):
                    variant["is_active"] = True
                    active_cover = variant
                    active_cover_edition_id = variant.get("edition_id") or None
                else:
                    variant["is_active"] = False
                if active_cover:
                    break
            if active_cover:
                break

    if not active_cover:
        for variant in cover_variants:
            if variant.get("is_primary") and (variant.get("image") or not active_cover):
                variant["is_active"] = True
                active_cover = variant
                active_cover_edition_id = variant.get("edition_id") or None
                break

    if not active_cover and cover_variants:
        cover_variants[0]["is_active"] = True
        active_cover = cover_variants[0]
        active_cover_edition_id = active_cover.get("edition_id") or None

    edition_active_id = selected_edition_id or active_cover_edition_id
    if not edition_active_id and display_primary_isbn_id:
        edition_active_id = str(display_primary_isbn_id)
    if not edition_active_id:
        edition_active_id = next(
            (
                str(isbn.pk)
                for isbn in isbn_entries
                if isbn.pk is not None
            ),
            None,
        )

    active_edition = None
    if edition_active_id:
        active_edition = next(
            (isbn for isbn in isbn_entries if str(isbn.pk) == edition_active_id),
            None,
        )

    cover_label = active_cover.get("label") if active_cover else None
    additional_cover_variants = []
    active_cover_key = active_cover.get("key") if active_cover else None
    primary_edition_id = str(display_primary_isbn_id) if display_primary_isbn_id else ""

    for variant in cover_variants:
        key = variant.get("key")
        image_url = variant.get("image")
        if not image_url:
            continue

        edition_id = variant.get("edition_id") or ""
        if key == "book-cover":
            # Показываем обложку основного издания среди миниатюр, чтобы можно было
            # быстро вернуться к нему после выбора другого издания.
            if not book.cover:
                continue
            if not edition_id and primary_edition_id:
                edition_id = primary_edition_id
            if active_cover_key == "book-cover":
                # Когда основная обложка активна, миниатюра не нужна — иначе будет
                # дублирование одной и той же картинки.
                continue
        elif not edition_id:
            continue

        alt_text = variant.get("alt") or variant.get("label") or f"Обложка книги «{book.title}»"
        query_suffix = f"?edition={edition_id}" if edition_id else ""

        additional_cover_variants.append(
            {
                "image": image_url,
                "alt": alt_text,
                "label": variant.get("label"),
                "edition_id": edition_id,
                "is_active": variant.get("is_active"),
                "url_query": query_suffix,
            }
        )

    show_cover_thumbnails = bool(additional_cover_variants)

    cover_thumbnail_pages = []
    active_thumbnail_page_index = 0
    if additional_cover_variants:
        thumbnails_per_page = 3
        for start in range(0, len(additional_cover_variants), thumbnails_per_page):
            page_variants = additional_cover_variants[start : start + thumbnails_per_page]
            cover_thumbnail_pages.append(
                {
                    "variants": page_variants,
                    "is_active": any(variant.get("is_active") for variant in page_variants),
                }
            )

        if cover_thumbnail_pages and not any(page["is_active"] for page in cover_thumbnail_pages):
            cover_thumbnail_pages[0]["is_active"] = True

        for index, page in enumerate(cover_thumbnail_pages):
            if page.get("is_active"):
                active_thumbnail_page_index = index
                break
    book_quick_facts: list[dict[str, str]] = []
    book_metadata: list[dict[str, str]] = []
    metadata_labels: set[str] = set()
    quick_fact_labels: set[str] = set()

    def add_quick_fact(label: str, value) -> None:
        if value is None:
            return
        value_str = str(value).strip()
        if not value_str:
            return
        if label in quick_fact_labels:
            return
        book_quick_facts.append({"label": label, "value": value_str})
        quick_fact_labels.add(label)

    def add_book_metadata(label: str, value) -> None:
        if value is None:
            return
        value_str = str(value).strip()
        if not value_str or label in metadata_labels or label in quick_fact_labels:
            return
        book_metadata.append({"label": label, "value": value_str})
        metadata_labels.add(label)

    genre_names = [
        genre.name.strip()
        for genre in book.genres.all()
        if getattr(genre, "name", "").strip()
    ]

    def add_genre_quick_fact() -> None:
        if not genre_names:
            return
        genre_label = "Жанры" if len(genre_names) > 1 else "Жанр"
        add_quick_fact(genre_label, ", ".join(genre_names))

    active_publisher_name = ""
    active_edition_details = None

    if active_edition:
        subjects = []
        if active_edition.subjects:
            subjects = [
                subject.strip()
                for subject in active_edition.subjects.split(",")
                if subject.strip()
            ]

        authors_qs = active_edition.authors.all()
        authors_display = ", ".join(author.name for author in authors_qs if author.name)

        publisher = (active_edition.publisher or "").strip()
        publish_date = (active_edition.publish_date or "").strip()
        binding = (active_edition.binding or "").strip()
        language = (active_edition.language or "").strip()

        if active_edition.total_pages:
            add_quick_fact("Страниц", active_edition.total_pages)
        if active_edition.isbn13:
            isbn13 = active_edition.isbn13.strip()
            if isbn13:
                add_quick_fact("ISBN-13", isbn13)
        add_genre_quick_fact()
        if publisher:
            add_quick_fact("Издательство", publisher)
        if publish_date:
            add_quick_fact("Издано", publish_date)

        edition_meta: list[dict[str, str]] = []
        if binding:
            edition_meta.append({"label": "Переплёт", "value": binding})
        if language:
            edition_meta.append({"label": "Язык", "value": language})
        header_parts = []
        if publisher:
            header_parts.append(publisher)
        if publish_date:
            header_parts.append(publish_date)
        if binding:
            header_parts.append(binding)

        active_edition_details = {
            "title": (active_edition.title or "").strip() or book.title,
            "header_text": " · ".join(header_parts),
            "subjects": subjects,
            "authors_display": authors_display,
            "meta": edition_meta,
            "quick_facts": list(book_quick_facts),
        }

        metadata_labels.update(item["label"] for item in edition_meta)

        active_publisher_name = publisher
    else:
        publisher_names = list(
            book.publisher.order_by("name").values_list("name", flat=True)
        )
        if publisher_names:
            publishers_display = ", ".join(publisher_names)
            active_publisher_name = publishers_display
            add_quick_fact("Издательство", publishers_display)

        edition_meta: list[dict[str, str]] = []
        primary_isbn = book.primary_isbn
        if primary_isbn:
            if primary_isbn.total_pages:
                add_quick_fact("Страниц", primary_isbn.total_pages)
            publish_date = (primary_isbn.publish_date or "").strip()
            if publish_date:
                add_quick_fact("Издано", publish_date)

            binding = (primary_isbn.binding or "").strip()
            if binding:
                edition_meta.append({"label": "Переплёт", "value": binding})

            language = (primary_isbn.language or "").strip()
            if language:
                edition_meta.append({"label": "Язык", "value": language})

            if primary_isbn.isbn13:
                isbn13 = primary_isbn.isbn13.strip()
                if isbn13:
                    add_quick_fact("ISBN-13", isbn13)
            add_genre_quick_fact()

        book_metadata.extend(edition_meta)
        metadata_labels.update(item["label"] for item in edition_meta)

    add_genre_quick_fact()
    
    if not book_quick_facts and active_publisher_name:
        add_quick_fact("Издательство", active_publisher_name)

    if book.series:
        series_value = book.series.strip()
        if series_value:
            if book.series_order:
                order_value = str(book.series_order).strip()
                if order_value:
                    series_value = f"{series_value} · книга {order_value}"
            add_book_metadata("Серия", series_value)
    elif book.series_order:
        add_book_metadata("Номер в серии", book.series_order)

    if book.age_rating:
        add_book_metadata("Возрастное ограничение", book.age_rating)

    if book.language:
        add_book_metadata("Язык", book.language)

    if book.audio:
        add_book_metadata("Аудиоверсия", book.audio.title)

    genre_shelves: list[dict[str, object]] = []
    for genre in book.genres.all():
        related_qs = (
            genre.books.exclude(pk=book.pk)
            .prefetch_related(
                Prefetch("authors", queryset=Author.objects.order_by("name"))
            )
            .annotate(
                average_rating=Avg("ratings__score"),
                rating_count=Count("ratings__score"),
            )
        )

        related_selection = related_qs.order_by(
            "-rating_count", "-average_rating", "title"
        )[:SHELF_BOOKS_LIMIT]

        related_books = [
            _serialize_book_for_shelf(related)
            for related in related_selection
        ]

        if related_books:
            genre_shelves.append(
                {
                    "title": f"Ещё в жанре «{genre.name}»",
                    "subtitle": "Популярные книги, которые выбирают читатели.",
                    "variant": "profile",
                    "texture_url": None,
                    "cta": {
                        "url": genre.get_absolute_url(),
                        "label": "Все книги жанра",
                    },
                    "books": related_books,
                }
            )

    reading_clubs_by_status = {
        "active": [],
        "upcoming": [],
        "past": [],
    }
    reading_clubs_qs = (
        ReadingClub.objects.filter(book=book)
        .select_related("creator")
        .prefetch_related("participants__user")
        .with_message_count()
    )

    for club in reading_clubs_qs:
        club.set_prefetched_message_count(club.message_count)
        reading_clubs_by_status[club.status].append(club)

    return render(request, "books/book_detail.html", {
        "book": book,
        "form": form,
        "ratings": ratings,
        "rating_summary": rating_summary,
        "rating_category_fields": rating_category_fields,
        "rating_scale": range(1, 11),
        "cover_variants": cover_variants,
        "additional_cover_variants": additional_cover_variants,
        "cover_thumbnail_pages": cover_thumbnail_pages,
        "active_thumbnail_page_index": active_thumbnail_page_index,
        "active_cover": active_cover,
        "cover_label": cover_label,
        "show_cover_thumbnails": show_cover_thumbnails,
        "active_edition": active_edition,
        "active_edition_details": active_edition_details,
        "active_publisher_name": active_publisher_name,
        "book_quick_facts": book_quick_facts,
        "book_metadata": book_metadata,
        "home_library_form": home_library_form,
        "home_library_item": home_library_item,
        "home_library_entry": home_library_entry,
        "home_library_edit_url": home_library_edit_url,
        "default_shelf_status": default_shelf_status,
        "genre_shelves": genre_shelves,
        "reading_clubs_by_status": reading_clubs_by_status,
    })

@login_required
def book_create(request):
    duplicate_candidates = []
    duplicate_resolution = request.POST.get("duplicate_resolution") if request.method == "POST" else None
    prefill_data = request.session.pop("book_prefill", None)

    if request.method == "POST":
        form = BookForm(request.POST, request.FILES)
        if form.is_valid():
            isbn_metadata = form.cleaned_data.get("isbn_metadata") or {}
            duplicate_candidates = _find_books_with_same_title_and_authors(
                form.cleaned_data.get("title"),
                form.cleaned_data.get("authors"),
            )

            if duplicate_candidates:
                if not duplicate_resolution:
                    form.add_error(
                        None,
                        "Мы нашли книгу с таким же названием и авторами. Выберите, что сделать.",
                    )
                else:
                    if duplicate_resolution == "new":
                        result = register_book_edition(
                            title=form.cleaned_data.get("title"),
                            authors=form.cleaned_data.get("authors"),
                            genres=form.cleaned_data.get("genres"),
                            publishers=form.cleaned_data.get("publisher"),
                            isbn_entries=form.cleaned_data.get("isbn"),
                            synopsis=form.cleaned_data.get("synopsis"),
                            series=form.cleaned_data.get("series"),
                            series_order=form.cleaned_data.get("series_order"),
                            age_rating=form.cleaned_data.get("age_rating"),
                            language=form.cleaned_data.get("language"),
                            audio=form.cleaned_data.get("audio"),
                            cover_file=form.cleaned_data.get("cover"),
                            force_new=True,
                            isbn_metadata=isbn_metadata,
                        )
                        _notify_about_registration(request, result)
                        return redirect("book_detail", pk=result.book.pk)

                    action, _, pk = duplicate_resolution.partition(":")
                    selected_book = next(
                        (book for book in duplicate_candidates if str(book.pk) == pk),
                        None,
                    )

                    if not selected_book:
                        form.add_error(None, "Выберите корректный вариант из списка.")
                    elif action == "same":
                        messages.info(
                            request,
                            "Эта книга уже есть на сайте. Мы перенаправили вас на её страницу.",
                        )
                        return redirect("book_detail", pk=selected_book.pk)
                    elif action == "edition":
                        result = register_book_edition(
                            title=form.cleaned_data.get("title"),
                            authors=form.cleaned_data.get("authors"),
                            genres=form.cleaned_data.get("genres"),
                            publishers=form.cleaned_data.get("publisher"),
                            isbn_entries=form.cleaned_data.get("isbn"),
                            synopsis=form.cleaned_data.get("synopsis"),
                            series=form.cleaned_data.get("series"),
                            series_order=form.cleaned_data.get("series_order"),
                            age_rating=form.cleaned_data.get("age_rating"),
                            language=form.cleaned_data.get("language"),
                            audio=form.cleaned_data.get("audio"),
                            cover_file=form.cleaned_data.get("cover"),
                            target_book=selected_book,
                            isbn_metadata=isbn_metadata,
                        )
                        
                        _notify_about_registration(request, result)
                        return redirect("book_detail", pk=result.book.pk)
                    else:
                        form.add_error(None, "Неизвестный вариант выбора.")
            else:
                result = register_book_edition(
                    title=form.cleaned_data.get("title"),
                    authors=form.cleaned_data.get("authors"),
                    genres=form.cleaned_data.get("genres"),
                    publishers=form.cleaned_data.get("publisher"),
                    isbn_entries=form.cleaned_data.get("isbn"),
                    synopsis=form.cleaned_data.get("synopsis"),
                    series=form.cleaned_data.get("series"),
                    series_order=form.cleaned_data.get("series_order"),
                    age_rating=form.cleaned_data.get("age_rating"),
                    language=form.cleaned_data.get("language"),
                    audio=form.cleaned_data.get("audio"),
                    cover_file=form.cleaned_data.get("cover"),
                    force_new=False,
                    isbn_metadata=isbn_metadata,
                )

                _notify_about_registration(request, result)
                return redirect("book_detail", pk=result.book.pk)

        else:
            messages.error(request, "Не удалось сохранить книгу. Проверьте форму.")
    else:
        form = BookForm()
    context = {
        "form": form,
        "duplicate_candidates": duplicate_candidates,
        "duplicate_resolution": duplicate_resolution,
        "prefill_data": prefill_data,
    }
    return render(request, "books/book_form.html", context)

@login_required
@permission_required("books.change_book", raise_exception=True)
def book_edit(request, pk):
    book = get_object_or_404(Book, pk=pk)
    if request.method == "POST":
        form = BookForm(request.POST, request.FILES, instance=book)
        if form.is_valid():
            form.save()
            return redirect("book_detail", pk=book.pk)
    else:
        form = BookForm(instance=book)
    return render(request, "books/book_form.html", {"form": form})

@login_required
def rate_book(request, pk):
    book = get_object_or_404(Book, pk=pk)
    if request.method == "POST":
        form = RatingForm(request.POST, user=request.user)
        if form.is_valid():
            rating = form.save(commit=False)
            rating.book = book
            rating.user = request.user
            rating.save()
            if rating.review and str(rating.review).strip():
                award_for_review(request.user, rating)
            ReadBeforeBuyGame.handle_review(request.user, book, rating.review)
            move_book_to_read_shelf(request.user, book)
            print_url = reverse("book_review_print", args=[book.pk])
            messages.success(
                request,
                mark_safe(
                    "Спасибо! Ваш отзыв сохранён. "
                    f"<a class=\"btn btn-sm btn-outline-light ms-2\" href=\"{print_url}\">Распечатать отзыв</a>"
                ),
            )
        else:
            messages.error(request, "Не удалось сохранить отзыв. Проверьте форму.")
    return redirect("book_detail", pk=book.pk)

@login_required
def book_review_print(request, pk):
    book = get_object_or_404(
        Book.objects.prefetch_related("authors", "genres", "publisher"),
        pk=pk,
    )
    rating = get_object_or_404(Rating, book=book, user=request.user)

    progress = (
        BookProgress.objects.filter(user=request.user, book=book, event__isnull=True)
        .order_by("-updated_at")
        .first()
    )
    if not progress:
        progress = (
            BookProgress.objects.filter(user=request.user, book=book)
            .order_by("-updated_at")
            .first()
        )

    reading_start = None
    reading_end = None
    notes = ""
    characters = []
    saved_quotes = []
    saved_notes = []

    if progress:
        period = progress.logs.aggregate(start=Min("log_date"), end=Max("log_date"))
        reading_start = period.get("start")
        reading_end = period.get("end")
        if not reading_start and progress.updated_at:
            reading_start = progress.updated_at.date()
        if not reading_end and progress.updated_at:
            reading_end = progress.updated_at.date()
        notes = progress.reading_notes
        characters = list(progress.character_entries.all())
        saved_quotes = list(
            progress.annotations.filter(kind=ProgressAnnotation.KIND_QUOTE)
        )
        saved_notes = list(
            progress.annotations.filter(kind=ProgressAnnotation.KIND_NOTE)
        )

    cover_url = request.build_absolute_uri(book.cover.url) if book.cover else None

    context = {
        "book": book,
        "rating": rating,
        "cover_url": cover_url,
        "authors": book.authors.all(),
        "reading_start": reading_start,
        "reading_end": reading_end,
        "notes": notes,
        "saved_quotes": saved_quotes,
        "saved_notes": saved_notes,
        "characters": characters,
    }

    html = render_to_string("books/review_print.html", context)
    filename = slugify(book.title) or "book-review"
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}-review.html"'
    return response