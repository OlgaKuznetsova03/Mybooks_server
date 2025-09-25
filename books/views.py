from django.db.models import Q
from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required
from .models import Book
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

    form = RatingForm(
        user=request.user if request.user.is_authenticated else None,
        initial={"book": book.pk}
    )

    return render(request, "books/book_detail.html", {
        "book": book,
        "form": form,
        "ratings": ratings,
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
    return redirect("book_detail", pk=book.pk)