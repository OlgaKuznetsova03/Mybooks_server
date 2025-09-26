from django.db.models import Q, Min, Max
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
from .models import Book, Rating
from .forms import BookForm, RatingForm


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
        Book.objects.prefetch_related("authors", "genres", "publisher", "isbn", "ratings__user"),
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


    return render(request, "books/book_detail.html", {
        "book": book,
        "form": form,
        "ratings": ratings,
        "rating_summary": rating_summary,
        "rating_category_fields": rating_category_fields,
        "rating_scale": range(1, 11),
    })

@login_required
@permission_required("books.add_book", raise_exception=True)
def book_create(request):
    if request.method == "POST":
        form = BookForm(request.POST, request.FILES)
        if form.is_valid():
            book = form.save()
            return redirect("book_detail", pk=book.pk)
    else:
        form = BookForm()
    return render(request, "books/book_form.html", {"form": form})

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