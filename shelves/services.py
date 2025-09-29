from __future__ import annotations

"""Utility helpers for manipulating user shelves."""

from django.contrib.auth.models import User
from django.db import transaction

from books.models import Book
from .models import Shelf, ShelfItem


DEFAULT_READING_SHELF = "Читаю"
DEFAULT_READ_SHELF = "Прочитал"


def _get_default_shelf(user: User, name: str) -> Shelf:
    shelf, _ = Shelf.objects.get_or_create(
        user=user,
        name=name,
        defaults={"is_default": True, "is_public": True},
    )
    return shelf


def move_book_to_read_shelf(user: User, book: Book) -> None:
    """Move the book from the "Читаю" shelf to "Прочитал" for the user."""
    if not user.is_authenticated:
        return

    with transaction.atomic():
        reading_shelf = Shelf.objects.filter(user=user, name=DEFAULT_READING_SHELF).first()
        if reading_shelf:
            ShelfItem.objects.filter(shelf=reading_shelf, book=book).delete()

        read_shelf = _get_default_shelf(user, DEFAULT_READ_SHELF)
        ShelfItem.objects.get_or_create(shelf=read_shelf, book=book)