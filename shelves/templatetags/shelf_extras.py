"""Custom template tags and filters for shelf templates."""
from __future__ import annotations

from django import template

register = template.Library()


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