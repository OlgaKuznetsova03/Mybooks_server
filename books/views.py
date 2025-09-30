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
)
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import mark_safe
from django.utils.text import slugify
from shelves.models import BookProgress
from shelves.services import move_book_to_read_shelf
from games.services.read_before_buy import ReadBeforeBuyGame
from .models import Book, Rating, ISBNModel
from .forms import BookForm, RatingForm
from .services import EditionRegistrationResult, register_book_edition

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
    qs = (
        Book.objects.all()
        .select_related("audio")
        .prefetch_related("authors", "genres", "publisher", "isbn")
    )
    if q:
        qs = qs.filter(
            Q(title__icontains=q) |
            Q(authors__name__icontains=q) |
            Q(genres__name__icontains=q)
        ).distinct()

    group_leader_subquery = (
        Book.objects.filter(edition_group_key=OuterRef("edition_group_key"))
        .order_by("pk")
        .values("pk")[:1]
    )

    qs = (
        qs.order_by("edition_group_key", "pk")
        .annotate(
            edition_leader=Case(
                When(edition_group_key="", then=F("pk")),
                default=Subquery(group_leader_subquery),
            )
        )
        .filter(pk=F("edition_leader"))
    )

    paginator = Paginator(qs, 12)
    page = request.GET.get("page")
    page_obj = paginator.get_page(page)
    return render(request, "books/books_list.html", {"page_obj": page_obj, "q": q})

def book_detail(request, pk):
    book = get_object_or_404(
        Book.objects.prefetch_related(
            "authors",
            "genres",
            "publisher",
            "ratings__user",
            Prefetch("isbn", queryset=ISBNModel.objects.prefetch_related("authors")),
        ),
        pk=pk
    )
    ratings = book.ratings.select_related("user").order_by("-id")  # последние сверху
    rating_summary = book.get_rating_summary()

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

        header_parts = []
        if publisher:
            header_parts.append(publisher)
        if publish_date:
            header_parts.append(publish_date)
        if binding:
            header_parts.append(binding)

        meta = []
        if active_edition.isbn:
            meta.append({"label": "ISBN-10", "value": active_edition.isbn})
        if active_edition.isbn13:
            meta.append({"label": "ISBN-13", "value": active_edition.isbn13})
        if active_edition.total_pages:
            meta.append({"label": "Страниц", "value": f"{active_edition.total_pages} стр."})
        if language:
            meta.append({"label": "Язык", "value": language})

        active_edition_details = {
            "title": (active_edition.title or "").strip() or book.title,
            "header_text": " · ".join(header_parts),
            "subjects": subjects,
            "authors_display": authors_display,
            "meta": meta,
            }

        active_publisher_name = publisher
    else:
        publisher_names = list(
            book.publisher.order_by("name").values_list("name", flat=True)
        )
        if publisher_names:
            active_publisher_name = ", ".join(publisher_names)

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
    })

@login_required
def book_create(request):
    duplicate_candidates = []
    duplicate_resolution = request.POST.get("duplicate_resolution") if request.method == "POST" else None

    if request.method == "POST":
        form = BookForm(request.POST, request.FILES)
        if form.is_valid():
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

    cover_url = request.build_absolute_uri(book.cover.url) if book.cover else None

    context = {
        "book": book,
        "rating": rating,
        "cover_url": cover_url,
        "authors": book.authors.all(),
        "reading_start": reading_start,
        "reading_end": reading_end,
        "notes": notes,
        "characters": characters,
    }

    html = render_to_string("books/review_print.html", context)
    filename = slugify(book.title) or "book-review"
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}-review.html"'
    return response