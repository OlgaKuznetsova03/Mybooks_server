from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from django.db import transaction

from .models import Book, ISBNModel, Publisher, Genre, AudioBook
from .utils import build_edition_group_key, store_additional_cover


@dataclass
class EditionRegistrationResult:
    book: Book
    created: bool
    added_isbns: List[ISBNModel]
    cover_applied_to_isbns: List[int]

    @property
    def attached_to_existing(self) -> bool:
        return not self.created


def _ensure_sequence(value: Optional[Iterable]):
    if not value:
        return []
    return list(value)


def register_book_edition(
    *,
    title: str,
    authors: Sequence,
    genres: Sequence[Genre] | None = None,
    publishers: Sequence[Publisher] | None = None,
    isbn_entries: Sequence[ISBNModel] | None = None,
    synopsis: str | None = None,
    series: str | None = None,
    series_order: int | None = None,
    age_rating: str | None = None,
    language: str | None = None,
    audio: AudioBook | None = None,
    cover_file=None,
    target_book: Book | None = None,
    force_new: bool = False,
) -> EditionRegistrationResult:
    """Register a new edition and attach it to an existing book when possible."""

    authors = _ensure_sequence(authors)
    if not authors:
        raise ValueError("At least one author is required to register an edition")

    genres = _ensure_sequence(genres)
    publishers = _ensure_sequence(publishers)
    isbn_entries = _ensure_sequence(isbn_entries)

    with transaction.atomic():
        book: Optional[Book]

        if target_book is not None:
            book = Book.objects.select_for_update().get(pk=target_book.pk)
        else:
            key = build_edition_group_key(title, [author.name for author in authors])
            book = None
            if key and not force_new:
                book = (
                    Book.objects.select_for_update()
                    .filter(edition_group_key=key)
                    .first()
                )

        created = False
        if book is None:
            book = Book.objects.create(
                title=title,
                synopsis=synopsis or "",
                series=series or None,
                series_order=series_order,
                age_rating=age_rating or None,
                language=language or None,
                audio=audio,
            )
            book.authors.set(authors)
            if genres:
                book.genres.set(genres)
            if publishers:
                book.publisher.set(publishers)
            created = True
        else:
            # ensure M2M relations
            existing_authors = set(book.authors.values_list("pk", flat=True))
            missing_authors = [author for author in authors if author.pk not in existing_authors]
            if missing_authors:
                book.authors.add(*missing_authors)

            if genres:
                book.genres.add(*genres)
            if publishers:
                book.publisher.add(*publishers)

            updates = []
            if synopsis and not book.synopsis:
                book.synopsis = synopsis
                updates.append("synopsis")
            if series and not book.series:
                book.series = series
                updates.append("series")
            if series_order and not book.series_order:
                book.series_order = series_order
                updates.append("series_order")
            if age_rating and not book.age_rating:
                book.age_rating = age_rating
                updates.append("age_rating")
            if language and not book.language:
                book.language = language
                updates.append("language")
            if audio and not book.audio:
                book.audio = audio
                updates.append("audio")

            if updates:
                book.save(update_fields=updates)

        added_isbns: List[ISBNModel] = []
        existing_isbn_ids = set(book.isbn.values_list("id", flat=True))
        for isbn in isbn_entries:
            if isbn.pk not in existing_isbn_ids:
                book.isbn.add(isbn)
                added_isbns.append(isbn)

        if not book.primary_isbn and (added_isbns or isbn_entries):
            book.primary_isbn = (added_isbns or isbn_entries)[0]
            book.save(update_fields=["primary_isbn"])

        cover_reference = ""
        new_cover_uploaded = bool(cover_file)
        if cover_file:
            if not book.cover:
                book.cover = cover_file
                book.save(update_fields=["cover"])
                cover_reference = book.cover.name or ""
            else:
                cover_reference = store_additional_cover(book, cover_file)

        cover_applied_ids: List[int] = []
        if cover_reference:
            for isbn in added_isbns:
                isbn.image = cover_reference
                isbn.save(update_fields=["image"])
                cover_applied_ids.append(isbn.pk or 0)

        if not created and cover_reference and not added_isbns:
            # Update primary ISBN image if book cover changed but no new ISBNs added
            primary = book.primary_isbn
            if primary and (new_cover_uploaded or not primary.image):
                primary.image = cover_reference
                primary.save(update_fields=["image"])
                cover_applied_ids.append(primary.pk or 0)

        book.refresh_edition_group_key()

        return EditionRegistrationResult(
            book=book,
            created=created,
            added_isbns=added_isbns,
            cover_applied_to_isbns=cover_applied_ids,
        )