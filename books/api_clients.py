"""Clients for integrating with external book APIs."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional
from urllib import parse, request, error


logger = logging.getLogger(__name__)


OPEN_LIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"
OPEN_LIBRARY_EDITION_URL_TEMPLATE = "https://openlibrary.org/books/{olid}.json"
OPEN_LIBRARY_BASE_URL = "https://openlibrary.org"
OPEN_LIBRARY_COVER_URL_TEMPLATE = "https://covers.openlibrary.org/b/{kind}/{value}-L.jpg"
OPEN_LIBRARY_AUTHOR_URL_TEMPLATE = "https://openlibrary.org{key}.json"


def _normalize_isbn(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit() or ch.upper() == "X")


def _coerce_list(value: Any) -> List[str]:
    if not value:
        return []
    result: List[str] = []
    if isinstance(value, (list, tuple, set)):
        iterable: Iterable[Any] = value
    else:
        iterable = [value]
    for item in iterable:
        if isinstance(item, dict):
            if "name" in item:
                result.append(str(item["name"]).strip())
            elif "value" in item:
                result.append(str(item["value"]).strip())
            elif "key" in item:
                result.append(str(item["key"]).split("/")[-1])
        else:
            result.append(str(item).strip())
    return [item for item in result if item]


def _deduplicate(sequence: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in sequence:
        if not item:
            continue
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(item)
    return result


def _coerce_int(value: Any) -> Optional[int]:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip()
        if value.isdigit():
            return int(value)
        try:
            return int(float(value))
        except ValueError:
            return None
    if isinstance(value, (list, tuple)):
        for item in value:
            parsed = _coerce_int(item)
            if parsed is not None:
                return parsed
    return None


def _extract_description(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, dict):
        if "value" in value:
            return str(value["value"]).strip() or None
        if "description" in value:
            return str(value["description"]).strip() or None
    return str(value).strip() or None


@dataclass
class ExternalBookData:
    """Normalized representation of a book returned by an external API."""

    title: str
    subtitle: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    publishers: List[str] = field(default_factory=list)
    publish_date: Optional[str] = None
    number_of_pages: Optional[int] = None
    physical_format: Optional[str] = None
    subjects: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)
    isbn_10: List[str] = field(default_factory=list)
    isbn_13: List[str] = field(default_factory=list)
    description: Optional[str] = None
    cover_url: Optional[str] = None
    source_url: Optional[str] = None
    olid: Optional[str] = None

    def combined_isbns(self) -> List[str]:
        seen = set()
        merged = []
        for value in self.isbn_13 + self.isbn_10:
            normalized = _normalize_isbn(value)
            if normalized and normalized not in seen:
                seen.add(normalized)
                merged.append(normalized)
        return merged

    def to_metadata_mapping(self) -> Dict[str, Dict[str, Any]]:
        """Return metadata keyed by ISBN suitable for form consumption."""

        metadata = {
            "title": self.title,
            "subtitle": self.subtitle,
            "authors": self.authors,
            "publishers": self.publishers,
            "publish_date": self.publish_date,
            "number_of_pages": self.number_of_pages,
            "physical_format": self.physical_format,
            "subjects": self.subjects,
            "languages": self.languages,
            "description": self.description,
            "cover_url": self.cover_url,
            "isbn_10_list": self.isbn_10,
            "isbn_13_list": self.isbn_13,
        }

        result: Dict[str, Dict[str, Any]] = {}
        for isbn in self.combined_isbns():
            result[isbn] = metadata
        return result


class OpenLibraryClient:
    """Lightweight client for the Open Library public API."""

    user_agent = "MyBooksLibraryBot/1.0 (https://openlibrary.org)"

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def _fetch_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if params:
            query = parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
            url = f"{url}?{query}"
        req = request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8")
        except error.URLError as exc:  # pragma: no cover - network errors covered by logging
            logger.warning("Failed to fetch %s: %s", url, exc)
            return {}
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:  # pragma: no cover - guard against invalid responses
            logger.warning("Received invalid JSON from %s", url)
            return {}
        return data if isinstance(data, dict) else {}

    def _edition_details(self, olid: str) -> Dict[str, Any]:
        url = OPEN_LIBRARY_EDITION_URL_TEMPLATE.format(olid=olid)
        return self._fetch_json(url)

    def _author_name(self, author_key: str) -> Optional[str]:
        if not author_key:
            return None
        data = self._fetch_json(OPEN_LIBRARY_AUTHOR_URL_TEMPLATE.format(key=author_key))
        name = data.get("name") if isinstance(data, dict) else None
        if not name:
            return None
        return str(name).strip() or None

    def search(
        self,
        *,
        title: Optional[str] = None,
        author: Optional[str] = None,
        isbn: Optional[str] = None,
        limit: int = 5,
    ) -> List[ExternalBookData]:
        params = {
            "title": title or None,
            "author": author or None,
            "isbn": _normalize_isbn(isbn or "") or None,
            "limit": max(1, min(limit, 20)),
        }

        search_data = self._fetch_json(OPEN_LIBRARY_SEARCH_URL, params)
        docs = search_data.get("docs") if isinstance(search_data, dict) else None
        if not docs:
            return []

        results: List[ExternalBookData] = []
        for doc in docs[:limit]:
            edition_keys = doc.get("edition_key") or []
            edition_details: Dict[str, Any] = {}
            olid: Optional[str] = None
            for key in edition_keys:
                details = self._edition_details(key)
                if details:
                    edition_details = details
                    olid = key
                    break

            title_value = (
                edition_details.get("title")
                or doc.get("title")
                or doc.get("title_suggest")
                or ""
            )
            if not title_value:
                continue

            subtitle = edition_details.get("subtitle") or doc.get("subtitle")

            doc_authors = _coerce_list(doc.get("author_name"))
            authors = doc_authors or []
            if not authors:
                edition_authors = edition_details.get("authors")
                author_keys: List[str] = []
                if isinstance(edition_authors, list):
                    for entry in edition_authors:
                        if isinstance(entry, dict) and entry.get("key"):
                            author_keys.append(str(entry["key"]))
                fetched_authors: List[str] = []
                for key in author_keys[:5]:
                    name = self._author_name(key)
                    if name:
                        fetched_authors.append(name)
                if fetched_authors:
                    authors = fetched_authors
            authors = _deduplicate(authors)

            publishers = _coerce_list(
                edition_details.get("publishers") or doc.get("publisher")
            )
            publishers = _deduplicate(publishers)

            subjects = _coerce_list(
                edition_details.get("subjects") or doc.get("subject")
            )
            subjects = _deduplicate(subjects)

            languages = _deduplicate(_coerce_list(edition_details.get("languages")))

            isbn_10 = _deduplicate(_coerce_list(edition_details.get("isbn_10")))
            isbn_13 = _deduplicate(_coerce_list(edition_details.get("isbn_13")))
            if not isbn_10 and not isbn_13:
                isbn_10 = _deduplicate(_coerce_list(doc.get("isbn")))

            number_of_pages = _coerce_int(edition_details.get("number_of_pages"))
            if number_of_pages is None:
                number_of_pages = _coerce_int(edition_details.get("number_of_pages_median"))
            if number_of_pages is None:
                number_of_pages = _coerce_int(doc.get("number_of_pages_median"))

            physical_format = (
                edition_details.get("physical_format")
                or edition_details.get("physical_format_display")
            )

            description = _extract_description(
                edition_details.get("description") or doc.get("description")
            )

            publish_date = edition_details.get("publish_date")
            if not publish_date:
                publish_date = doc.get("first_publish_year")
                if publish_date:
                    publish_date = str(publish_date)

            cover_url = None
            cover_ids = edition_details.get("covers")
            if isinstance(cover_ids, list) and cover_ids:
                cover_url = OPEN_LIBRARY_COVER_URL_TEMPLATE.format(
                    kind="id", value=cover_ids[0]
                )
            elif doc.get("cover_i"):
                cover_url = OPEN_LIBRARY_COVER_URL_TEMPLATE.format(
                    kind="id", value=doc["cover_i"]
                )
            else:
                candidate_isbns = isbn_13 or isbn_10
                if candidate_isbns:
                    cover_url = OPEN_LIBRARY_COVER_URL_TEMPLATE.format(
                        kind="isbn", value=_normalize_isbn(candidate_isbns[0])
                    )

            source_url = None
            if olid:
                source_url = f"{OPEN_LIBRARY_BASE_URL}/books/{olid}"
            elif doc.get("key"):
                source_url = f"{OPEN_LIBRARY_BASE_URL}{doc['key']}"

            results.append(
                ExternalBookData(
                    title=title_value,
                    subtitle=subtitle or None,
                    authors=authors,
                    publishers=publishers,
                    publish_date=publish_date or None,
                    number_of_pages=number_of_pages,
                    physical_format=str(physical_format).strip() if physical_format else None,
                    subjects=subjects,
                    languages=languages,
                    isbn_10=[_normalize_isbn(val) for val in isbn_10],
                    isbn_13=[_normalize_isbn(val) for val in isbn_13],
                    description=description,
                    cover_url=cover_url,
                    source_url=source_url,
                    olid=olid,
                )
            )

        return results


open_library_client = OpenLibraryClient()