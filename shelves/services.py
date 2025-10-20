from __future__ import annotations

"""Utility helpers for manipulating user shelves."""

from collections.abc import Iterable
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone


from books.models import Book
from .models import BookProgress, Shelf, ShelfItem


DEFAULT_WANT_SHELF = "Хочу прочитать"
DEFAULT_READING_SHELF = "Читаю"
DEFAULT_READ_SHELF = "Прочитал"
DEFAULT_READ_SHELF_ALIASES: tuple[str, ...] = ("Прочитал",)
ALL_DEFAULT_READ_SHELF_NAMES: tuple[str, ...] = (
    DEFAULT_READ_SHELF,
    *DEFAULT_READ_SHELF_ALIASES,
)
DEFAULT_HOME_LIBRARY_SHELF = "Моя домашняя библиотека"
READING_PROGRESS_LABEL = "Читаю сейчас"


def _get_default_shelf(
    user: User,
    name: str,
    *,
    is_public: bool = True,
    aliases: tuple[str, ...] | None = None,
) -> Shelf:
    """Получить (или создать) стандартную полку ``name`` для пользователя."""

    lookup_names = [name]
    if aliases:
        lookup_names.extend(alias for alias in aliases if alias)

    shelf = (
        Shelf.objects
        .filter(user=user, name__in=lookup_names)
        .order_by("-is_default")
        .first()
    )

    if shelf:
        if not shelf.is_default:
            shelf.is_default = True
            shelf.is_public = is_public
            shelf.save(update_fields=["is_default", "is_public"])
        return shelf

    shelf = Shelf.objects.create(
        user=user,
        name=name,
        is_default=True,
        is_public=is_public,
    )
    return shelf


def get_home_library_shelf(user: User) -> Shelf:
    """Получить (или создать) стандартную полку домашней библиотеки пользователя."""

    return _get_default_shelf(user, DEFAULT_HOME_LIBRARY_SHELF, is_public=False)


def _remove_book_from_named_shelf(
    user: User,
    book: Book,
    shelf_name: str | Iterable[str],
) -> None:
    if isinstance(shelf_name, (list, tuple, set, frozenset)):
        shelf = Shelf.objects.filter(user=user, name__in=shelf_name).first()
    else:
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
        _remove_book_from_named_shelf(user, book, ALL_DEFAULT_READ_SHELF_NAMES)
        _remove_book_from_named_shelf(user, book, DEFAULT_WANT_SHELF)

        read_shelf = _get_default_shelf(
            user,
            DEFAULT_READ_SHELF,
            aliases=DEFAULT_READ_SHELF_ALIASES,
        )
        ShelfItem.objects.get_or_create(shelf=read_shelf, book=book)

    try:
        from games.services.read_before_buy import ReadBeforeBuyGame
    except ImportError:
        return

    home_shelf = get_home_library_shelf(user)
    ReadBeforeBuyGame.ensure_completion_awarded(
        user,
        home_shelf,
        book,
        occurred_at=timezone.now(),
    )


def move_book_to_reading_shelf(user: User, book: Book) -> None:
    """Ensure the book is on the user's "Читаю" shelf."""

    if not user.is_authenticated:
        return

    with transaction.atomic():
        _remove_book_from_named_shelf(user, book, ALL_DEFAULT_READ_SHELF_NAMES)
        _remove_book_from_named_shelf(user, book, DEFAULT_WANT_SHELF)

        reading_shelf = _get_default_shelf(user, DEFAULT_READING_SHELF)
        ShelfItem.objects.get_or_create(shelf=reading_shelf, book=book)


def get_default_shelf_status_map(
    user: User,
    book_ids: Iterable[int | str | None],
) -> dict[int, dict[str, object]]:
    """Return mapping of book ids to default shelf status for ``user``.

    The status respects the priority order of the default shelves: "Хочу прочитать"
    < "Читаю" < "Прочитал". Unknown or malformed book identifiers are ignored.
    """

    if not getattr(user, "is_authenticated", False):
        return {}

    normalized_ids: list[int] = []
    seen: set[int] = set()

    for raw_id in book_ids:
        try:
            value = int(raw_id) if raw_id is not None else None
        except (TypeError, ValueError):
            continue
        if value is None or value <= 0 or value in seen:
            continue
        seen.add(value)
        normalized_ids.append(value)

    if not normalized_ids:
        return {}

    read_shelf_names = tuple({name for name in ALL_DEFAULT_READ_SHELF_NAMES if name})

    shelf_items = (
        ShelfItem.objects
        .filter(
            shelf__user=user,
            shelf__name__in=[
                DEFAULT_WANT_SHELF,
                DEFAULT_READING_SHELF,
                *read_shelf_names,
            ],
            book_id__in=normalized_ids,
        )
        .select_related("shelf")
    )

    priority_map = {"want": 1, "reading": 2, "read": 3}
    status_map: dict[int, dict[str, object]] = {}

    for item in shelf_items:
        shelf_name = item.shelf.name
        if shelf_name in read_shelf_names:
            code = "read"
        elif shelf_name == DEFAULT_READING_SHELF:
            code = "reading"
        else:
            code = "want"

        existing = status_map.get(item.book_id)
        if not existing or priority_map[code] > priority_map[existing["code"]]:
            status_map[item.book_id] = {
                "code": code,
                "label": shelf_name,
                "added_at": item.added_at,
            }

    pending_completion_ids = [
        book_id
        for book_id in normalized_ids
        if status_map.get(book_id, {}).get("code") != "read"
    ]

    if pending_completion_ids:
        completed_progresses = (
            BookProgress.objects
            .filter(
                user=user,
                event__isnull=True,
                book_id__in=pending_completion_ids,
                percent__gte=Decimal("100"),
            )
            .only("book_id", "updated_at")
        )

        for progress in completed_progresses:
            existing = status_map.get(progress.book_id)
            if existing and priority_map[existing["code"]] >= priority_map["read"]:
                continue
            status_map[progress.book_id] = {
                "code": "read",
                "label": DEFAULT_READ_SHELF,
                "added_at": progress.updated_at,
            }

    return status_map
