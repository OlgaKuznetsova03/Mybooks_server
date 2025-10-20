"""Custom template tags and filters for shelf templates."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django import template

from ..services import get_default_shelf_status_map

register = template.Library()


def _normalize_book_id(value: Any) -> int | None:
    """Convert ``value`` to a positive integer book identifier."""

    if isinstance(value, bool) or value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def _extract_book_id(entry: Any) -> int | None:
    """Best-effort extraction of a book identifier from ``entry``."""

    candidates: list[Any] = []
    if isinstance(entry, dict):
        book = entry.get("book")
        candidates.append(entry.get("book_id"))
    else:
        book = getattr(entry, "book", None)
        candidates.append(getattr(entry, "book_id", None))

    if book is not None:
        if isinstance(book, dict):
            candidates.extend([book.get("pk"), book.get("id")])
        else:
            candidates.extend([getattr(book, "pk", None), getattr(book, "id", None)])

    if isinstance(entry, dict):
        candidates.extend([entry.get("pk"), entry.get("id")])
    else:
        candidates.extend([getattr(entry, "pk", None), getattr(entry, "id", None)])
        
    for candidate in candidates:
        book_id = _normalize_book_id(candidate)
        if book_id is not None:
            return book_id
    return None


@register.simple_tag(takes_context=True)
def default_shelf_status_map(
    context,
    entries: Iterable[Any] | None,
    user: Any | None = None,
) -> dict[int, dict[str, object]]:
    """Return mapping of book ids in ``entries`` to the default shelf status for ``user``.

    ``user`` can be provided explicitly (for example, when rendering shelves that belong
    to another account). When omitted, the current request user is used.
    """

    if not entries:
        return {}

    target_user = user
    if target_user is None:
        request = context.get("request")
        target_user = getattr(request, "user", None) if request else None

    if not getattr(target_user, "is_authenticated", False):
        return {}

    book_ids: list[int] = []
    seen: set[int] = set()
    for entry in entries:
        book_id = _extract_book_id(entry)
        if book_id is None or book_id in seen:
            continue
        seen.add(book_id)
        book_ids.append(book_id)

    if not book_ids:
        return {}

    return get_default_shelf_status_map(target_user, book_ids)


@register.filter
def dict_get(mapping: Any, key: Any):
    """Return ``mapping[key]`` with graceful fallbacks for templates."""

    if mapping is None:
        return None
    if hasattr(mapping, "get"):
        result = mapping.get(key)
        if result is not None:
            return result
        normalized = _normalize_book_id(key)
        if normalized is None or normalized == key:
            return result
        return mapping.get(normalized)
    try:
        normalized = _normalize_book_id(key)
        if normalized is None:
            return None
        return mapping[normalized]
    except Exception:  # pragma: no cover - template safety
        return None


@register.filter
def coalesce(value: Any, fallback: Any):
    """Return ``value`` if it is truthy, otherwise ``fallback``."""

    return value or fallback


@register.filter
def ru_pluralize(value, forms: str = "книга,книги,книг") -> str:
    """Return the correct Russian plural form for ``value``.

    ``forms`` should contain three comma-separated forms: singular,
    paucal (2-4), and plural (others). For example::

        {{ books_count|ru_pluralize:"книга,книги,книг" }}

    The implementation follows the Russian pluralization rules that depend
    on the last digits of the number while being resilient to invalid input.
    """

    if not forms:
        return ""

    try:
        number = abs(int(value))
    except (TypeError, ValueError):
        number = 0

    variants = [form.strip() for form in forms.split(",") if form.strip()]
    if len(variants) == 1:
        variants = variants * 3
    elif len(variants) == 2:
        variants.append(variants[-1])
    elif len(variants) > 3:
        variants = variants[:3]

    n100 = number % 100
    if 11 <= n100 <= 14:
        return variants[2]

    n10 = number % 10
    if n10 == 1:
        return variants[0]
    if 2 <= n10 <= 4:
        return variants[1]
    return variants[2]