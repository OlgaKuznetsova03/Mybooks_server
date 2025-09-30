from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Mapping, Any

from django.db import transaction

from .models import Book, ISBNModel, Publisher, Genre, AudioBook, Author
from .utils import (
    build_edition_group_key,
    store_additional_cover,
    normalize_isbn,
    download_cover_from_url,
)


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


def _apply_isbn_metadata(
    isbn: ISBNModel,
    metadata_map: Mapping[str, Mapping[str, Any]],
) -> None:
    if not metadata_map:
        return

    candidates = []
    if isbn.isbn:
        candidates.append(normalize_isbn(isbn.isbn))
    if isbn.isbn13:
        candidates.append(normalize_isbn(isbn.isbn13))

    metadata: Optional[Mapping[str, Any]] = None
    for key in candidates:
        if key and key in metadata_map:
            metadata = metadata_map[key]
            break
    if not metadata:
        return

    updates: List[str] = []

    def set_if_empty(field: str, value) -> None:
        if value in (None, ""):
            return
        current = getattr(isbn, field)
        if current:
            return
        setattr(isbn, field, value)
        updates.append(field)

    title = metadata.get("title") or metadata.get("subtitle")
    set_if_empty("title", title)

    publish_date = metadata.get("publish_date")
    set_if_empty("publish_date", publish_date)

    number_of_pages = metadata.get("number_of_pages")
    if number_of_pages and not isbn.total_pages:
        try:
            isbn.total_pages = int(number_of_pages)
            updates.append("total_pages")
        except (TypeError, ValueError):
            pass

    physical_format = metadata.get("physical_format")
    set_if_empty("binding", physical_format)

    publishers = metadata.get("publishers")
    if publishers and not isbn.publisher:
        if isinstance(publishers, (list, tuple)):
            publisher_value = ", ".join(str(p).strip() for p in publishers if p)
        else:
            publisher_value = str(publishers)
        set_if_empty("publisher", publisher_value.strip())

    subjects = metadata.get("subjects")
    if subjects and not isbn.subjects:
        if isinstance(subjects, (list, tuple)):
            subject_value = ", ".join(str(s).strip() for s in subjects if s)
        else:
            subject_value = str(subjects)
        set_if_empty("subjects", subject_value.strip())

    languages = metadata.get("languages")
    if languages and not isbn.language:
        if isinstance(languages, (list, tuple)):
            language_value = ", ".join(str(l).strip() for l in languages if l)
        else:
            language_value = str(languages)
        set_if_empty("language", language_value.strip())

    description = metadata.get("description")
    set_if_empty("synopsis", description)

    cover_url = metadata.get("cover_url")
    if cover_url and not isbn.image:
        isbn.image = str(cover_url).strip()
        updates.append("image")

    if not isbn.isbn13:
        isbn13_candidates = metadata.get("isbn_13_list")
        if isinstance(isbn13_candidates, (list, tuple)):
            for candidate in isbn13_candidates:
                normalized = normalize_isbn(str(candidate))
                if len(normalized) == 13:
                    isbn.isbn13 = normalized
                    updates.append("isbn13")
                    break

    if updates:
        isbn.save(update_fields=list(dict.fromkeys(updates)))

    author_names = metadata.get("authors")
    if author_names:
        if not isinstance(author_names, (list, tuple)):
            author_names = [author_names]
        author_objects: List[Author] = []
        existing_ids = set(isbn.authors.values_list("id", flat=True))
        for name in author_names:
            name_str = str(name).strip()
            if not name_str:
                continue
            author, _ = Author.objects.get_or_create(name=name_str)
            if author.pk not in existing_ids:
                author_objects.append(author)
        if author_objects:
            isbn.authors.add(*author_objects)


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
    isbn_metadata: Mapping[str, Mapping[str, Any]] | None = None,
) -> EditionRegistrationResult:
    """Register a new edition and attach it to an existing book when possible."""

    authors = _ensure_sequence(authors)
    if not authors:
        raise ValueError("At least one author is required to register an edition")

    genres = _ensure_sequence(genres)
    publishers = _ensure_sequence(publishers)
    isbn_entries = _ensure_sequence(isbn_entries)

    metadata_map: dict[str, Mapping[str, Any]] = {}
    metadata_cover_url: str | None = None
    if isbn_metadata:
        for key, details in isbn_metadata.items():
            if isinstance(details, Mapping) and not metadata_cover_url:
                cover_candidate = str(details.get("cover_url") or "").strip()
                if cover_candidate:
                    metadata_cover_url = cover_candidate
            normalized = normalize_isbn(str(key))
            if not normalized:
                continue
            if isinstance(details, Mapping):
                metadata_map[normalized] = details

    if not cover_file and metadata_cover_url:
        downloaded_cover = download_cover_from_url(metadata_cover_url)
        if downloaded_cover:
            cover_file = downloaded_cover
    
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
            _apply_isbn_metadata(isbn, metadata_map)

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