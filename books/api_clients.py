"""Clients for integrating with external book APIs."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional
from urllib import parse, request, error


logger = logging.getLogger(__name__)


GOOGLE_BOOKS_SEARCH_URL = "https://www.googleapis.com/books/v1/volumes"
GOOGLE_BOOKS_USER_AGENT = "MyBooksLibraryBot/1.0 (+https://github.com)"


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
    external_id: Optional[str] = None

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


class GoogleBooksClient:
    """Lightweight client for the Google Books public API."""

    def __init__(self, *, api_key: Optional[str] = None, timeout: float = 10.0):
        self.api_key = api_key
        self.timeout = timeout

    def _fetch_json(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query_params = {k: v for k, v in params.items() if v not in (None, "")}
        if self.api_key:
            query_params["key"] = self.api_key
        query = parse.urlencode(query_params)
        url = f"{GOOGLE_BOOKS_SEARCH_URL}?{query}"
        req = request.Request(url, headers={"User-Agent": GOOGLE_BOOKS_USER_AGENT})
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

    def _build_query(
        self,
        *,
        title: Optional[str] = None,
        author: Optional[str] = None,
        isbn: Optional[str] = None,
    ) -> Optional[str]:
        terms: List[str] = []

        def _quoted(value: str) -> str:
            return "\"" + value.replace("\"", " ").strip() + "\""

        if title:
            terms.append(f"intitle:{_quoted(str(title))}")
        if author:
            terms.append(f"inauthor:{_quoted(str(author))}")
        normalized_isbn = _normalize_isbn(isbn or "") if isbn else ""
        if normalized_isbn:
            terms.append(f"isbn:{normalized_isbn}")

        fallback = str(title or author or normalized_isbn or "").strip()
        if not terms and fallback:
            terms.append(fallback)

        if not terms:
            return None
        return " ".join(terms)

    def _pick_cover_url(self, volume_info: Dict[str, Any]) -> Optional[str]:
        links = volume_info.get("imageLinks")
        if not isinstance(links, dict):
            return None
        for key in [
            "extraLarge",
            "large",
            "medium",
            "small",
            "thumbnail",
            "smallThumbnail",
        ]:
            value = links.get(key)
            if value:
                candidate = str(value).strip()
                if not candidate:
                    continue

                parsed = parse.urlparse(candidate)
                if (
                    parsed.netloc == "books.google.com"
                    and parsed.path.startswith("/books/content")
                ):
                    params = parse.parse_qsl(
                        parsed.query, keep_blank_values=True
                    )
                    zoom_found = False
                    download_found = False
                    updated_params = []
                    for name, raw_value in params:
                        if name == "zoom":
                            try:
                                zoom_value = int(raw_value)
                            except (TypeError, ValueError):
                                zoom_value = 0
                            updated_params.append((name, str(max(zoom_value, 3))))
                            zoom_found = True
                        elif name == "download":
                            updated_params.append((name, "1"))
                            download_found = True
                        else:
                            updated_params.append((name, raw_value))

                    if not zoom_found:
                        updated_params.append(("zoom", "3"))
                    if not download_found:
                        updated_params.append(("download", "1"))

                    candidate = parse.urlunparse(
                        parsed._replace(
                            scheme="https",
                            query=parse.urlencode(updated_params, doseq=True),
                        )
                    )

                return candidate
        return None

    def _parse_volume(self, item: Dict[str, Any]) -> Optional[ExternalBookData]:
        volume_info = item.get("volumeInfo")
        if not isinstance(volume_info, dict):
            return None

        title = str(volume_info.get("title") or "").strip()
        if not title:
            return None
        
        subtitle = str(volume_info.get("subtitle") or "").strip() or None
        authors = _deduplicate(_coerce_list(volume_info.get("authors")))
        publishers = _deduplicate(_coerce_list(volume_info.get("publisher")))
        publish_date = str(volume_info.get("publishedDate") or "").strip() or None
        number_of_pages = _coerce_int(volume_info.get("pageCount"))
        physical_format = str(volume_info.get("printType") or "").strip() or None
        subjects = _deduplicate(_coerce_list(volume_info.get("categories")))
        language = str(volume_info.get("language") or "").strip()
        languages = [language] if language else []
        description = _extract_description(volume_info.get("description"))

        isbn_10: List[str] = []
        isbn_13: List[str] = []
        identifiers = volume_info.get("industryIdentifiers")
        if isinstance(identifiers, list):
            for entry in identifiers:
                if not isinstance(entry, dict):
                    continue
                identifier = str(entry.get("identifier") or "").strip()
                normalized = _normalize_isbn(identifier)
                if not normalized:
                    continue
                identifier_type = str(entry.get("type") or "").upper()
                if identifier_type == "ISBN_10" and normalized not in isbn_10:
                    isbn_10.append(normalized)
                elif identifier_type == "ISBN_13" and normalized not in isbn_13:
                    isbn_13.append(normalized)
                elif not identifier_type:
                    if len(normalized) == 10 and normalized not in isbn_10:
                        isbn_10.append(normalized)
                    elif len(normalized) == 13 and normalized not in isbn_13:
                        isbn_13.append(normalized)

        cover_url = self._pick_cover_url(volume_info)
        source_url = (
            str(volume_info.get("infoLink") or "").strip()
            or str(volume_info.get("canonicalVolumeLink") or "").strip()
            or str(item.get("selfLink") or "").strip()
            or None
        )

        return ExternalBookData(
            title=title,
            subtitle=subtitle,
            authors=authors,
            publishers=publishers,
            publish_date=publish_date,
            number_of_pages=number_of_pages,
            physical_format=physical_format,
            subjects=subjects,
            languages=languages,
            isbn_10=isbn_10,
            isbn_13=isbn_13,
            description=description,
            cover_url=cover_url,
            source_url=source_url,
            external_id=str(item.get("id") or "").strip() or None,
        )

    def search(
        self,
        *,
        title: Optional[str] = None,
        author: Optional[str] = None,
        isbn: Optional[str] = None,
        limit: int = 5,
    ) -> List[ExternalBookData]:
        query = self._build_query(title=title, author=author, isbn=isbn)
        if not query:
            return []
        
        params = {
            "q": query,
            "maxResults": max(1, min(limit, 40)),
            "printType": "books",
            "orderBy": "relevance",
        }

        data = self._fetch_json(params)
        items = data.get("items") if isinstance(data, dict) else None
        if not items or not isinstance(items, list):
            return []

        results: List[ExternalBookData] = []
        for item in items:
            parsed = self._parse_volume(item) if isinstance(item, dict) else None
            if not parsed:
                continue

            results.append(parsed)
            if len(results) >= limit:
                break
        return results


google_books_client = GoogleBooksClient()