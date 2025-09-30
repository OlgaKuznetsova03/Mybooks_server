from __future__ import annotations

"""Utility helpers for manipulating user shelves."""

from django.contrib.auth.models import User
from django.db import transaction

from books.models import Book
from .models import Shelf, ShelfItem


DEFAULT_WANT_SHELF = "Хочу прочитать"
DEFAULT_READING_SHELF = "Читаю"
DEFAULT_READ_SHELF = "Прочитал"


def _get_default_shelf(user: User, name: str) -> Shelf:
    shelf, _ = Shelf.objects.get_or_create(
        user=user,
        name=name,
        defaults={"is_default": True, "is_public": True},
    )
    return shelf


def _remove_book_from_named_shelf(user: User, book: Book, shelf_name: str) -> None:
    shelf = Shelf.objects.filter(user=user, name=shelf_name).first()
    if shelf:
        ShelfItem.objects.filter(shelf=shelf, book=book).delete()


def remove_book_from_want_shelf(user: User, book: Book) -> None:
    """Ensure the book is not present on the "Хочу прочитать" shelf."""
    if not user.is_authenticated:
        return
    _remove_book_from_named_shelf(user, book, DEFAULT_WANT_SHELF)


def move_book_to_read_shelf(user: User, book: Book) -> None:
    """Move the book from the "Читаю" shelf to "Прочитал" for the user."""
    if not user.is_authenticated:
        return

    with transaction.atomic():
        _remove_book_from_named_shelf(user, book, DEFAULT_READING_SHELF)
        _remove_book_from_named_shelf(user, book, DEFAULT_WANT_SHELF)

        read_shelf = _get_default_shelf(user, DEFAULT_READ_SHELF)
        ShelfItem.objects.get_or_create(shelf=read_shelf, book=book)

    try:
        from games.services.read_before_buy import ReadBeforeBuyGame
    except ImportError:
        return

    ReadBeforeBuyGame.ensure_completion_awarded(user, read_shelf, book)