"""Clients for integrating with external book APIs (ISBNdb)."""

from __future__ import annotations

import copy
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional
from urllib import error, parse, request

from django.conf import settings


logger = logging.getLogger(__name__)

# --- ISBNdb endpoints (v2) ---
ISBNDB_BOOK_URL = "https://api2.isbndb.com/book"    # /book/{isbn}
ISBNDB_SEARCH_BOOKS_URL = "https://api2.isbndb.com/search/books"
ISBNDB_BOOKS_COLLECTION_URL = "https://api2.isbndb.com/books"
ISBNDB_USER_AGENT = "MyBooksLibraryBot/1.0 (+https://github.com)"


# ----------------- helpers: coercion & normalization -----------------

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
    """Return the first integer found; supports '256 p.' / ['','256'] etc."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        s = value.strip()
        m = re.search(r"\d+", s)
        return int(m.group()) if m else None
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


# ----------------- genre translation helpers (ISBNdb subjects -> RU) -----------------

GENRE_EN_RU: Dict[str, str] = {
    # Базовые
    "Fiction": "Художественная литература",
    "Nonfiction": "Нехудожественная литература",
    "Poetry": "Поэзия",
    "Drama": "Драма",
    "Short Stories": "Рассказы",
    "Essays": "Эссе",
    "Classics": "Классическая литература",

    # Детектив / триллер / ужасы
    "Mystery": "Детективы",
    "Detective": "Детективы",
    "Crime": "Криминальные романы",
    "Thriller": "Триллеры",
    "Suspense": "Саспенс",
    "Horror": "Ужасы",
    "True Crime": "Реальные преступления",

    # Романы о любви / отношения
    "Romance": "Любовные романы",
    "Contemporary Romance": "Современная романтика",
    "Historical Romance": "Историческая романтика",
    "Family & Relationships": "Семья и отношения",
    "Women's Fiction": "Женская проза",

    # Фантастика / фэнтези
    "Science Fiction": "Научная фантастика",
    "Fantasy": "Фэнтези",
    "Urban Fantasy": "Городское фэнтези",
    "Paranormal": "Паранормальное",
    "Dystopian": "Антиутопия",
    "Space Opera": "Космическая опера",

    # История / биографии
    "History": "История",
    "Biography": "Биографии",
    "Memoir": "Мемуары",
    "Autobiography": "Автобиографии",
    "Historical Studies": "Исторические исследования",

    # Соцнауки / политика / право
    "Sociology": "Социология",
    "Politics": "Политика",
    "Economics": "Экономика",
    "Law": "Право",
    "Education": "Образование",
    "Anthropology": "Антропология",

    # Наука и техника
    "Mathematics": "Математика",
    "Physics": "Физика",
    "Chemistry": "Химия",
    "Biology": "Биология",
    "Medicine": "Медицина",
    "Engineering": "Инженерия",
    "Computer Science": "Информатика",
    "Technology": "Технологии",
    "Data Science": "Наука о данных",
    "Artificial Intelligence": "Искусственный интеллект",

    # Бизнес
    "Business": "Бизнес",
    "Finance": "Финансы",
    "Marketing": "Маркетинг",
    "Management": "Менеджмент",
    "Entrepreneurship": "Предпринимательство",
    "Investing": "Инвестиции",
    "Personal Finance": "Личные финансы",

    # Дом / хобби / досуг
    "Cooking": "Кулинария",
    "Food & Drink": "Еда и напитки",
    "Crafts & Hobbies": "Рукоделие и хобби",
    "Gardening": "Садоводство",
    "Home Improvement": "Дом и интерьер",
    "Pets": "Домашние животные",
    "Travel": "Путешествия",
    "Health & Fitness": "Здоровье и фитнес",
    "Self-Help": "Саморазвитие",

    # Детям и подросткам
    "Children's Books": "Детская литература",
    "Young Adult": "Подростковая литература",
    "Picture Books": "Книги с иллюстрациями",
    "Fairy Tales": "Сказки",

    # Искусство и культура
    "Art": "Искусство",
    "Photography": "Фотография",
    "Music": "Музыка",
    "Performing Arts": "Сценическое искусство",
    "Architecture": "Архитектура",
    "Design": "Дизайн",
    "Comics & Graphic Novels": "Комиксы и графические романы",

    # Религия / духовные практики
    "Religion": "Религия",
    "Spirituality": "Духовные практики",
    "Occult": "Оккультизм",
}


GENRE_ALIASES: Dict[str, str] = {
    # Fiction
    "lit": "Fiction",
    "literature": "Fiction",
    "novel": "Fiction",
    "novels": "Fiction",

    # Nonfiction
    "non-fiction": "Nonfiction",
    "non fiction": "Nonfiction",

    # Mystery/Detective
    "mystery & detective": "Mystery",
    "detective & mystery": "Mystery",

    # Crime/Thriller
    "crime fiction": "Crime",
    "noir": "Crime",
    "legal thriller": "Thriller",
    "psychological thriller": "Thriller",

    # Horror
    "dark fiction": "Horror",

    # Romance
    "romantic fiction": "Romance",
    "rom-com": "Romance",
    "romcom": "Romance",
    "new adult romance": "Contemporary Romance",

    # Fantasy
    "high fantasy": "Fantasy",
    "epic fantasy": "Fantasy",
    "dark fantasy": "Fantasy",
    "ya fantasy": "Fantasy",
    "urban-fantasy": "Urban Fantasy",

    # Sci-Fi
    "sci-fi": "Science Fiction",
    "scifi": "Science Fiction",
    "sf": "Science Fiction",
    "hard science fiction": "Science Fiction",
    "cyberpunk": "Science Fiction",
    "space-opera": "Space Opera",

    # Dystopian
    "post-apocalyptic": "Dystopian",
    "post apocalyptic": "Dystopian",

    # History/Bio
    "historical": "History",
    "historical fiction": "History",
    "bio": "Biography",
    "autobio": "Autobiography",

    # Social Sciences
    "political science": "Politics",
    "econ": "Economics",

    # CS/Tech
    "cs": "Computer Science",
    "programming": "Computer Science",
    "software engineering": "Computer Science",
    "information technology": "Technology",
    "ai": "Artificial Intelligence",
    "machine learning": "Data Science",
    "ml": "Data Science",
    "data analytics": "Data Science",

    # Business
    "personal finance": "Personal Finance",
    "startup": "Entrepreneurship",
    "startups": "Entrepreneurship",

    # Cooking
    "cookbook": "Cooking",
    "food": "Food & Drink",
    "drinks": "Food & Drink",

    # Children/YA
    "ya": "Young Adult",
    "kid lit": "Children's Books",

    # Arts
    "graphic novels": "Comics & Graphic Novels",
    "graphic novel": "Comics & Graphic Novels",
    "performing arts": "Performing Arts",

    # Religion/Spiritual
    "occult & esoterica": "Occult",
    "esoterica": "Occult",
}


_ALIAS_HINTS: List[tuple[re.Pattern, str]] = [
    (re.compile(r"\bya\b|\byoung adult\b", re.I), "Young Adult"),
    (re.compile(r"\bgraphic novel", re.I), "Comics & Graphic Novels"),
    (re.compile(r"\bspace opera\b", re.I), "Space Opera"),
    (re.compile(r"\b(post[- ]apocalyptic|dystop(i|a))", re.I), "Dystopian"),
    (re.compile(r"\b(paranormal|vampire|werewolf|witch)", re.I), "Paranormal"),
    (re.compile(r"\b(cozy mystery)\b", re.I), "Mystery"),
    (re.compile(r"\b(self[- ]help)\b", re.I), "Self-Help"),
    (re.compile(r"\b(rom[- ]?com|romcom)\b", re.I), "Romance"),
    (re.compile(r"\b(cyberpunk|hard sci[- ]?fi|hard sf)\b", re.I), "Science Fiction"),
]


def _canonize_key(text: str) -> str:
    """Normalize key for alias lookup."""

    return re.sub(r"\s+", " ", text.strip().lower())


def _map_subject(raw: str) -> Optional[str]:
    """Return canonical English subject key or None if not found."""

    if not raw:
        return None

    candidate = raw.strip()
    if not candidate:
        return None

    for en_name in GENRE_EN_RU.keys():
        if candidate.lower() == en_name.lower():
            return en_name

    alias_key = _canonize_key(candidate)
    if alias_key in GENRE_ALIASES:
        return GENRE_ALIASES[alias_key]

    for pattern, target in _ALIAS_HINTS:
        if pattern.search(candidate):
            return target

    if any(separator in candidate for separator in {"&", "/", "-"}):
        for part in re.split(r"[&/,-]+", candidate):
            mapped = _map_subject(part.strip())
            if mapped:
                return mapped

    return None


def _translate_subjects(subjects: Iterable[str]) -> List[str]:
    """Translate known ISBNdb subjects to Russian equivalents."""

    translated: List[str] = []
    seen: set[str] = set()

    for raw in subjects:
        if not raw:
            continue

        canonical = _map_subject(raw)
        if canonical:
            mapped = GENRE_EN_RU.get(canonical, raw)
        else:
            mapped = raw

        normalized = mapped.strip()
        if not normalized:
            continue

        lowered = normalized.lower()
        if lowered in seen:
            continue

        seen.add(lowered)
        translated.append(normalized)

    return translated


# ----------------- data model -----------------

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
        # Independent copies so mutating one ISBN block won't affect others.
        for isbn in self.combined_isbns():
            result[isbn] = copy.deepcopy(metadata)
        return result


# ----------------- Transliteration helpers (Latin -> Cyrillic) -----------------

_LATIN_MULTI_CHAR = [
    ("shch", "щ"),
    ("sch", "щ"),
    ("yo", "ё"),
    ("jo", "ё"),
    ("yu", "ю"),
    ("ju", "ю"),
    ("ya", "я"),
    ("ja", "я"),
    ("ye", "е"),
    ("je", "е"),
    ("yi", "ый"),
    ("iy", "ий"),
    ("ia", "я"),
    ("ie", "ие"),
    ("io", "ио"),
    ("iu", "ю"),
    ("zh", "ж"),
    ("kh", "х"),
    ("ts", "ц"),
    ("ch", "ч"),
    ("sh", "ш"),
]

_LATIN_SINGLE_CHAR = {
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф", "g": "г",
    "h": "х", "i": "и", "j": "й", "k": "к", "l": "л", "m": "м", "n": "н",
    "o": "о", "p": "п", "q": "к", "r": "р", "s": "с", "t": "т", "u": "у",
    "v": "в", "w": "в", "x": "кс", "y": "й", "z": "з",
}

_LATIN_RE = re.compile(r"[A-Za-z]")


def _apply_case(sample: str, replacement: str) -> str:
    if not replacement:
        return replacement
    if sample.isupper():
        return replacement.upper()
    if sample[0].isupper():
        if len(replacement) == 1:
            return replacement.upper()
        return replacement[0].upper() + replacement[1:]
    return replacement


def _should_transliterate(value: str) -> bool:
    if not value:
        return False
    if not value.isascii():
        return False
    return bool(_LATIN_RE.search(value))


def _transliterate_text(value: str) -> str:
    if not _should_transliterate(value):
        return value
    result: List[str] = []
    index = 0
    length = len(value)
    while index < length:
        matched = False
        for latin, cyrillic in _LATIN_MULTI_CHAR:
            chunk = value[index : index + len(latin)]
            if chunk.lower() == latin:
                result.append(_apply_case(chunk, cyrillic))
                index += len(latin)
                matched = True
                break
        if matched:
            continue
        char = value[index]
        mapped = _LATIN_SINGLE_CHAR.get(char.lower())
        result.append(_apply_case(char, mapped) if mapped else char)
        index += 1
    return "".join(result)


def _transliterate_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return _transliterate_text(value)


def _transliterate_list(values: List[str]) -> List[str]:
    return [_transliterate_text(item) for item in values]


# ----------------- ISBNdb client -----------------

class ISBNDBClient:
    """Client for interacting with the ISBNdb API."""

    def __init__(self, *, api_key: Optional[str] = None, timeout: float = 10.0):
        key = api_key or getattr(settings, "ISBNDB_API_KEY", None)
        if isinstance(key, str):
            key = key.strip()
        self.api_key = key
        self.timeout = timeout

    # --- low-level HTTP ---

    def _fetch_json_url(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        query_params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        query = parse.urlencode(query_params)
        full_url = f"{url}?{query}" if query else url

        headers = {"User-Agent": ISBNDB_USER_AGENT}
        if self.api_key:
            # ВАЖНО для api2.isbndb.com: именно Authorization, не x-api-key
            headers["Authorization"] = self.api_key

        req = request.Request(full_url, headers=headers)
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8")
        except error.HTTPError as exc:  # pragma: no cover
            logger.warning(
                "HTTP %s on %s (auth=%s): %s",
                exc.code, full_url, "yes" if "Authorization" in headers else "no", exc.reason
            )
            return {}
        except error.URLError as exc:  # pragma: no cover
            logger.warning("Network error for %s: %s", full_url, exc)
            return {}

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:  # pragma: no cover
            logger.warning("Invalid JSON from %s", full_url)
            return {}
        return data if isinstance(data, dict) else {}

    # --- normalization helpers ---

    def _normalize_language(self, value: str) -> List[str]:
        normalized = (value or "").strip()
        if not normalized:
            return []
        lowered = normalized.lower()
        if lowered in {"ru", "rus", "russian"}:
            return ["ru"]
        if "ru" in lowered:
            return ["ru"]
        return [normalized]

    def _apply_russian_transliteration(self, data: ExternalBookData) -> ExternalBookData:
        if not any(lang.lower() == "ru" for lang in data.languages):
            return data
        data.title = _transliterate_text(data.title)
        data.subtitle = _transliterate_optional(data.subtitle)
        data.authors = _transliterate_list(data.authors)
        data.publishers = _transliterate_list(data.publishers)
        # Genres are now translated separately, no transliteration needed
        data.description = _transliterate_optional(data.description)
        data.physical_format = _transliterate_optional(data.physical_format)
        data.languages = ["ru"]
        return data

    def _parse_book(self, item: Dict[str, Any]) -> Optional[ExternalBookData]:
        title = str(item.get("title") or "").strip()
        if not title:
            return None

        subtitle = str(item.get("title_long") or "").strip() or None
        authors = _deduplicate(_coerce_list(item.get("authors")))
        publishers = _deduplicate(_coerce_list(item.get("publisher")))
        publish_date = str(item.get("date_published") or "").strip() or None
        number_of_pages = _coerce_int(item.get("pages"))
        physical_format = str(item.get("binding") or "").strip() or None
        subjects = _translate_subjects(_deduplicate(_coerce_list(item.get("subjects"))))
        language_value = str(item.get("language") or item.get("language_code") or "").strip()
        languages = self._normalize_language(language_value)
        description = _extract_description(
            item.get("synopsis") or item.get("overview") or item.get("excerpt")
        )

        isbn_10: List[str] = []
        isbn_13: List[str] = []

        primary_isbn = _normalize_isbn(str(item.get("isbn") or ""))
        if primary_isbn:
            if len(primary_isbn) == 10:
                isbn_10.append(primary_isbn)
            elif len(primary_isbn) == 13:
                isbn_13.append(primary_isbn)

        secondary_isbn = _normalize_isbn(str(item.get("isbn13") or ""))
        if secondary_isbn:
            if len(secondary_isbn) == 13 and secondary_isbn not in isbn_13:
                isbn_13.append(secondary_isbn)
            elif len(secondary_isbn) == 10 and secondary_isbn not in isbn_10:
                isbn_10.append(secondary_isbn)

        for raw_value in _coerce_list(item.get("isbns")):
            normalized = _normalize_isbn(str(raw_value))
            if not normalized:
                continue
            if len(normalized) == 13 and normalized not in isbn_13:
                isbn_13.append(normalized)
            elif len(normalized) == 10 and normalized not in isbn_10:
                isbn_10.append(normalized)

        cover_url = (
            str(
                item.get("image_l")
                or item.get("image")
                or item.get("image_m")
                or item.get("image_s")
                or ""
            ).strip()
            or None
        )

        source_url = (
            str(item.get("url") or "").strip()
            or str(item.get("link") or "").strip()
            or None
        )

        ext_id = str(item.get("id") or secondary_isbn or primary_isbn or "").strip() or None

        # Fallback source page on ISBNdb if we have any ISBN
        if not source_url:
            first_isbn = (isbn_13 or isbn_10 or [])
            if first_isbn:
                source_url = f"https://isbndb.com/book/{first_isbn[0]}"

        data = ExternalBookData(
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
            external_id=ext_id,
        )
        return self._apply_russian_transliteration(data)

    # --- query building & search ---

    def _build_params(
        self,
        *,
        title: Optional[str] = None,
        author: Optional[str] = None,
        isbn: Optional[str] = None,
        limit: int,
    ) -> Dict[str, Any]:
        page_size = max(1, min(limit, 100))
        params: Dict[str, Any] = {"pageSize": page_size}

        normalized_isbn = _normalize_isbn(isbn or "") if isbn else ""
        if normalized_isbn:
            params["_direct_isbn"] = normalized_isbn
            return params

        query_parts: List[str] = []
        if title:
            query_parts.append(str(title).strip())
        elif author:
            query_parts.append(str(author).strip())

        if query_parts:
            q_text = " ".join(part for part in query_parts if part)
            params["_search_q"] = q_text
            if author:
                params["author"] = str(author).strip()
            return params

        # Ничего не передано — вернём пустой результат в search()
        return params

    def search(
        self,
        *,
        title: Optional[str] = None,
        author: Optional[str] = None,
        isbn: Optional[str] = None,
        limit: int = 5,
    ) -> List[ExternalBookData]:
        params = self._build_params(title=title, author=author, isbn=isbn, limit=limit)

        # /book/{isbn} - exact lookup
        direct_isbn = params.pop("_direct_isbn", None)
        if direct_isbn:
            data = self._fetch_json_url(f"{ISBNDB_BOOK_URL}/{direct_isbn}")
            item = data.get("book") if isinstance(data, dict) else None
            if isinstance(item, dict):
                parsed = self._parse_book(item)
                return [parsed] if parsed else []
            return []

        # /search?q=... — безопасно для Unicode/кириллицы
        search_q = params.pop("_search_q", None)
        if search_q:
            q_params = copy.deepcopy(params)
            q_params.update({"q": search_q, "pageSize": max(1, min(limit, 100))})
            data = self._fetch_json_url(ISBNDB_SEARCH_BOOKS_URL, q_params)
            # У /search иногда "books", иногда "data"
            items = data.get("books") or data.get("data")

            if not isinstance(items, list):
                # Fallback: публичное API ISBNdb может не поддерживать /search/books
                # (возвращает 404). В таком случае пробуем коллекцию /books/<q>.
                fallback_url = f"{ISBNDB_BOOKS_COLLECTION_URL}/{parse.quote(search_q)}"
                data = self._fetch_json_url(fallback_url, params)
                items = data.get("books") or data.get("data")

            if not isinstance(items, list):
                return []
            
            results: List[ExternalBookData] = []
            for item in items:
                parsed = self._parse_book(item) if isinstance(item, dict) else None
                if parsed:
                    results.append(parsed)
                    if len(results) >= limit:
                        break
            return results

        return []


isbndb_client = ISBNDBClient()
