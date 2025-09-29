from __future__ import annotations

from typing import Iterable

from django.core.files.uploadedfile import UploadedFile

# We import lazily in functions to avoid circular imports during Django app
# initialization.


def normalize_title(title: str | None) -> str:
    if not title:
        return ""
    return " ".join(part for part in (title or "").strip().split())


def build_edition_group_key(title: str | None, authors: Iterable[str]) -> str:
    normalized_title = normalize_title(title).casefold()
    normalized_authors = sorted(normalize_title(author).casefold() for author in authors if author)
    return "::".join([normalized_title, *normalized_authors]) if normalized_title or normalized_authors else ""


def store_additional_cover(book: "Book", uploaded_file: UploadedFile) -> str:
    if not uploaded_file:
        return ""

    try:
        uploaded_file.seek(0)
    except (AttributeError, ValueError):
        pass

    field_file = book.cover
    filename = field_file.field.generate_filename(book, uploaded_file.name)
    return field_file.storage.save(filename, uploaded_file)
