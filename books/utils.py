from __future__ import annotations

import mimetypes
import os
import re
import secrets
from typing import Iterable
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.core.files.base import ContentFile
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


_MULTISPACE_RE = re.compile(r"\s+")


_GENRE_SYNONYMS: dict[str, str] = {
    "детектив": "Детектив",
    "детективы": "Детектив",
    "современная литература": "Современная литература",
    "современная проза": "Современная литература",
}


def normalize_genre_name(name: str | None) -> str:
    """Return a cleaned up genre name that can be safely used as a key."""

    if not name:
        return ""

    normalized = str(name).strip(" \t\r\n.,;:!?\'\"«»()[]{}")
    if not normalized:
        return ""

    normalized = _MULTISPACE_RE.sub(" ", normalized)
    key = normalized.casefold()

    synonym = _GENRE_SYNONYMS.get(key)
    if synonym:
        return synonym

    if normalized.islower() or normalized.isupper():
        normalized = normalized.title()

    return normalized


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


def normalize_isbn(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in str(value).upper() if ch.isdigit() or ch == "X")


def download_cover_from_url(
    url: str,
    *,
    timeout: float = 5.0,
    max_bytes: int = 4 * 1024 * 1024,
) -> ContentFile | None:
    """Fetch an image from ``url`` and wrap it in ``ContentFile``.

    Returns ``None`` when the URL is invalid, not an image or downloading fails.
    The response size is capped to ``max_bytes`` to avoid exhausting memory when
    remote servers return very large files.
    """

    if not url:
        return None

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None

    request = Request(url, headers={"User-Agent": "ReadTogether/cover-fetcher"})

    try:
        mime_type = ""
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            mime_type = content_type.split(";", 1)[0].strip().lower()

            if mime_type and not mime_type.startswith("image/"):
                return None

            data = response.read(max_bytes + 1)
    except (URLError, OSError, ValueError):
        return None

    if not data or len(data) > max_bytes:
        return None

    extension = ""
    if mime_type:
        extension = mimetypes.guess_extension(mime_type) or ""

    if not extension:
        extension = os.path.splitext(parsed.path)[1].lower()

    if extension in {".jpe", ".jpeg"}:
        extension = ".jpg"

    allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    if extension not in allowed_extensions:
        extension = ".jpg"

    filename = f"metadata_{secrets.token_hex(8)}{extension}"
    return ContentFile(data, name=filename)