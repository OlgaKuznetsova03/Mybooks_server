from django.db.models import Q, Min, Max, Prefetch
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
from .models import Book, Rating, ISBNModel
from .forms import BookForm, RatingForm

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


def book_list(request):
    q = (request.GET.get("q") or "").strip()
    qs = Book.objects.all().select_related("audio").prefetch_related("authors", "genres", "publisher", "isbn")
    if q:
        qs = qs.filter(
            Q(title__icontains=q) |
            Q(authors__name__icontains=q) |
            Q(genres__name__icontains=q)
        ).distinct()
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

    show_cover_thumbnails = any(not variant.get("is_primary") for variant in cover_variants)
    cover_label = active_cover.get("label") if active_cover else None
    isbn_editions = []

    for index, isbn in enumerate(isbn_entries):
        subjects = []
        if isbn.subjects:
            subjects = [subject.strip() for subject in isbn.subjects.split(",") if subject.strip()]

        authors_qs = isbn.authors.all()
        authors_display = ", ".join(author.name for author in authors_qs if author.name)

        header_parts = []
        publisher = (isbn.publisher or "").strip()
        publish_date = (isbn.publish_date or "").strip()
        binding = (isbn.binding or "").strip()

        if publisher:
            header_parts.append(publisher)
        if publish_date:
            header_parts.append(publish_date)
        if binding:
            header_parts.append(binding)

        meta = []
        if isbn.isbn:
            meta.append({"label": "ISBN-10", "value": isbn.isbn})
        if isbn.isbn13:
            meta.append({"label": "ISBN-13", "value": isbn.isbn13})
        if isbn.total_pages:
            meta.append({"label": "Страниц", "value": f"{isbn.total_pages} стр."})
        if isbn.language:
            meta.append({"label": "Язык", "value": isbn.language})

        isbn_editions.append({
            "id": str(isbn.pk),
            "display_title": (isbn.title or "").strip() or book.title,
            "header_text": " · ".join(header_parts),
            "subjects": subjects,
            "authors_display": authors_display,
            "meta": meta,
            "is_primary": isbn.pk == display_primary_isbn_id,
            "is_active": str(isbn.pk) == (edition_active_id or ""),
        })

    return render(request, "books/book_detail.html", {
        "book": book,
        "form": form,
        "ratings": ratings,
        "rating_summary": rating_summary,
        "rating_category_fields": rating_category_fields,
        "rating_scale": range(1, 11),
        "cover_variants": cover_variants,
        "active_cover": active_cover,
        "cover_label": cover_label,
        "show_cover_thumbnails": show_cover_thumbnails,
        "isbn_editions": isbn_editions,
        "active_edition": active_edition,
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
                        book = form.save()
                        messages.success(request, "Книга успешно добавлена.")
                        return redirect("book_detail", pk=book.pk)

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
                        new_isbns = form.cleaned_data.get("isbn") or []
                        existing_isbn_ids = set(
                            selected_book.isbn.values_list("id", flat=True)
                        )
                        unique_isbns = [
                            isbn for isbn in new_isbns if isbn.pk not in existing_isbn_ids
                        ]
                        if not unique_isbns:
                            form.add_error(
                                "isbn",
                                "Все указанные ISBN уже привязаны к этой книге. Укажите новый ISBN для издания.",
                            )
                        else:
                            for isbn in unique_isbns:
                                selected_book.isbn.add(isbn)

                            publishers = form.cleaned_data.get("publisher") or []
                            if publishers:
                                selected_book.publisher.add(*publishers)

                            genres = form.cleaned_data.get("genres") or []
                            if genres:
                                selected_book.genres.add(*genres)

                            cover = form.cleaned_data.get("cover")
                            if cover:
                                selected_book.cover = cover

                            synopsis = form.cleaned_data.get("synopsis")
                            if synopsis and not selected_book.synopsis:
                                selected_book.synopsis = synopsis

                            language = form.cleaned_data.get("language")
                            if language and not selected_book.language:
                                selected_book.language = language

                            age_rating = form.cleaned_data.get("age_rating")
                            if age_rating and not selected_book.age_rating:
                                selected_book.age_rating = age_rating

                            audio = form.cleaned_data.get("audio")
                            if audio and not selected_book.audio:
                                selected_book.audio = audio

                            series = form.cleaned_data.get("series")
                            if series and not selected_book.series:
                                selected_book.series = series

                            series_order = form.cleaned_data.get("series_order")
                            if series_order and not selected_book.series_order:
                                selected_book.series_order = series_order

                            if not selected_book.primary_isbn:
                                selected_book.primary_isbn = unique_isbns[0]

                            selected_book.save()

                            messages.success(
                                request,
                                "Новое издание добавлено к существующей книге.",
                            )
                            return redirect("book_detail", pk=selected_book.pk)
                    else:
                        form.add_error(None, "Неизвестный вариант выбора.")
            else:
                book = form.save()
                messages.success(request, "Книга успешно добавлена.")
                return redirect("book_detail", pk=book.pk)

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