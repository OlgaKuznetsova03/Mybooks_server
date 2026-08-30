from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from accounts.models import Profile
from accounts.services import (
    MONTHLY_CHALLENGE_GOAL_EDIT_COST,
    charge_feature_access,
    get_feature_payment_context,
)
from books.models import Book
from books.utils import build_book_search_filter
from shelves.models import ReadingLog, ShelfItem
from shelves.services import (
    ALL_DEFAULT_READ_SHELF_NAMES,
    DEFAULT_HOME_LIBRARY_SHELF,
    DEFAULT_READING_SHELF,
    DEFAULT_WANT_SHELF,
)

from ..models import MonthlyChallenge, MonthlyChallengeBook
from .monthly_awards import build_monthly_challenge_award_url


MONTHLY_CHALLENGE_SLUG_PREFIX = "monthly-"
MONTHLY_CHALLENGE_CARD_SLUGS = (
    "monthly-mini-books",
    "monthly-book-list",
    "monthly-pages-minutes",
)

MONTHLY_MINI_BOOKS_MIN_TARGET = 2
MONTHLY_BOOK_LIST_MIN_BOOKS = 2
MONTHLY_PAGES_MIN_TARGET = 500
MONTHLY_MINUTES_MIN_TARGET = 600

MONTHLY_CHALLENGE_TITLES = {
    MonthlyChallenge.Kind.MINI_BOOKS: "Мини книжный вызов",
    MonthlyChallenge.Kind.BOOK_LIST: "Список на месяц",
    MonthlyChallenge.Kind.PAGES_MINUTES: "Страницы и минуты",
}

MONTHLY_CHALLENGE_DESCRIPTIONS = {
    MonthlyChallenge.Kind.MINI_BOOKS: "Задайте количество книг на месяц, а прочитанные книги засчитаются автоматически.",
    MonthlyChallenge.Kind.BOOK_LIST: "Соберите личный список книг на месяц и получите награду, когда все книги будут прочитаны.",
    MonthlyChallenge.Kind.PAGES_MINUTES: "Выберите цель по страницам, аудиоминутам или сразу по двум форматам.",
}

MONTHLY_CHALLENGE_HIGHLIGHTS = {
    MonthlyChallenge.Kind.MINI_BOOKS: (
        "Цель по количеству книг",
        "Автоматический зачет с полки «Прочитано»",
        "Награда в конце месяца",
    ),
    MonthlyChallenge.Kind.BOOK_LIST: (
        "Свой список книг",
        "Зачет только выбранных книг",
        "Награда за закрытый список",
    ),
    MonthlyChallenge.Kind.PAGES_MINUTES: (
        "Цель по страницам и аудио",
        "Прогресс из трекера чтения",
        "Награда за выполненный план",
    ),
}


def kind_from_slug(slug: str) -> str | None:
    if not slug.startswith(MONTHLY_CHALLENGE_SLUG_PREFIX):
        return None
    kind = slug.removeprefix(MONTHLY_CHALLENGE_SLUG_PREFIX)
    return kind if kind in MonthlyChallenge.Kind.values else None


def slug_from_kind(kind: str) -> str:
    return f"{MONTHLY_CHALLENGE_SLUG_PREFIX}{kind}"


def current_month_start() -> date:
    today = timezone.localdate()
    return today.replace(day=1)


def parse_month(value: Any | None = None) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.replace(day=1)
    if isinstance(value, datetime):
        return value.date().replace(day=1)
    if isinstance(value, str):
        cleaned = value.strip()
        if len(cleaned) == 7 and cleaned[2] == ".":
            return date(int(cleaned[3:]), int(cleaned[:2]), 1)
        if len(cleaned) >= 7 and cleaned[4] == "-":
            return date(int(cleaned[:4]), int(cleaned[5:7]), 1)
    return current_month_start()


def next_month_start(month: date) -> date:
    year = month.year + (1 if month.month == 12 else 0)
    month_number = 1 if month.month == 12 else month.month + 1
    return date(year, month_number, 1)


def month_bounds(month: date) -> tuple[datetime, datetime]:
    start = timezone.make_aware(datetime.combine(month, time.min))
    end = timezone.make_aware(datetime.combine(next_month_start(month), time.min))
    return start, end


def month_display(month: date) -> str:
    return month.strftime("%m.%Y")


def deadline_display(month: date) -> str:
    last_day = monthrange(month.year, month.month)[1]
    return f"{last_day:02d}.{month.month:02d}.{month.year}"


def parse_monthly_target(value: Any | None) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def absolute_url(request, url: str | None) -> str | None:
    if not url:
        return None
    if str(url).startswith(("http://", "https://", "//", "data:", "blob:")):
        return str(url)
    if request is None:
        return str(url)
    return request.build_absolute_uri(url)


def serialize_book(request, book: Book, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    authors = ", ".join(book.authors.all().values_list("name", flat=True))
    cover_url = None
    original_getter = getattr(book, "get_original_cover_url", None)
    if callable(original_getter):
        cover_url = original_getter()
    if not cover_url:
        cover_url = book.get_cover_url()
    payload = {
        "id": book.id,
        "book_id": book.id,
        "title": book.title,
        "authors": authors,
        "cover_url": absolute_url(request, cover_url),
        "app_path": f"/books/{book.id}",
        "site_path": f"/books/{book.id}/",
        "tracker_url": f"/books/{book.id}/tracker",
    }
    if extra:
        payload.update(extra)
    return payload


def get_or_create_challenge(user, kind: str, month: date | None = None) -> MonthlyChallenge:
    challenge_month = month or current_month_start()
    challenge, _created = MonthlyChallenge.objects.get_or_create(
        user=user,
        kind=kind,
        month=challenge_month,
    )
    return challenge


def monthly_goal_is_configured(challenge: MonthlyChallenge) -> bool:
    if challenge.kind == MonthlyChallenge.Kind.MINI_BOOKS:
        return bool(challenge.target_books)
    if challenge.kind == MonthlyChallenge.Kind.BOOK_LIST:
        return challenge.books.count() >= MONTHLY_BOOK_LIST_MIN_BOOKS
    if challenge.kind == MonthlyChallenge.Kind.PAGES_MINUTES:
        return bool(challenge.target_pages or challenge.target_minutes)
    return False


def get_monthly_goal_edit_payment(user, challenge: MonthlyChallenge) -> dict[str, Any]:
    profile, _created = Profile.objects.get_or_create(user=user)
    return {
        "required": monthly_goal_is_configured(challenge),
        **get_feature_payment_context(
            profile,
            cost=MONTHLY_CHALLENGE_GOAL_EDIT_COST,
        ),
    }


def get_read_book_items(user, month: date):
    start, end = month_bounds(month)
    return (
        ShelfItem.objects.filter(
            shelf__user=user,
            shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
            added_at__gte=start,
            added_at__lt=end,
        )
        .select_related("book")
        .prefetch_related("book__authors")
        .order_by("-added_at", "book__title")
    )


def get_monthly_log_totals(user, month: date) -> dict[str, int]:
    start = month
    end = next_month_start(month) - timedelta(days=1)
    totals = ReadingLog.objects.filter(
        progress__user=user,
        log_date__gte=start,
        log_date__lte=end,
    ).aggregate(
        pages=Sum("pages_equivalent"),
        audio_seconds=Sum("audio_seconds"),
    )
    pages = int(totals["pages"] or Decimal("0"))
    minutes = int((totals["audio_seconds"] or 0) // 60)
    return {"pages": pages, "minutes": minutes}


def get_available_books_for_list(
    request,
    user,
    challenge: MonthlyChallenge,
    *,
    query: str | None = None,
) -> list[dict[str, Any]]:
    selected_ids = set(challenge.books.values_list("book_id", flat=True))
    read_book_ids = (
        ShelfItem.objects.filter(
            shelf__user=user,
            shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
        )
        .values_list("book_id", flat=True)
        .distinct()
    )
    books = (
        Book.objects.visible_to_user(user)
        .exclude(id__in=selected_ids)
        .exclude(id__in=read_book_ids)
        .prefetch_related("authors")
    )

    cleaned_query = (query or "").strip()
    if cleaned_query:
        books = books.filter(build_book_search_filter(cleaned_query)).distinct()
    else:
        shelf_book_ids = (
            ShelfItem.objects.filter(
                shelf__user=user,
                shelf__name__in=[DEFAULT_WANT_SHELF, DEFAULT_READING_SHELF, DEFAULT_HOME_LIBRARY_SHELF],
            )
            .exclude(book_id__in=selected_ids)
            .exclude(book_id__in=read_book_ids)
            .values_list("book_id", flat=True)
            .distinct()
        )
        books = books.filter(id__in=shelf_book_ids)

    books = books.order_by("title")[:120]
    return [serialize_book(request, book) for book in books]


def user_has_read_book(user, book_id: int) -> bool:
    return ShelfItem.objects.filter(
        shelf__user=user,
        shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
        book_id=book_id,
    ).exists()


def add_monthly_challenge_book(
    user,
    book_id: int,
    *,
    month: date | str | None = None,
) -> MonthlyChallenge:
    challenge = get_or_create_challenge(user, MonthlyChallenge.Kind.BOOK_LIST, parse_month(month))
    book = Book.objects.visible_to_user(user).filter(id=book_id).first()
    if not book:
        raise ValueError("Книга недоступна.")
    if user_has_read_book(user, book.id):
        raise ValueError("Прочитанную книгу нельзя добавить в список месяца.")

    next_order = challenge.books.count() + 1
    MonthlyChallengeBook.objects.get_or_create(
        challenge=challenge,
        book=book,
        defaults={"order": next_order},
    )
    return challenge


def remove_monthly_challenge_book(
    user,
    book_id: int,
    *,
    month: date | str | None = None,
) -> MonthlyChallenge:
    challenge = get_or_create_challenge(user, MonthlyChallenge.Kind.BOOK_LIST, parse_month(month))
    MonthlyChallengeBook.objects.filter(challenge=challenge, book_id=book_id).delete()
    return challenge


def calculate_completion(challenge: MonthlyChallenge) -> tuple[bool, dict[str, Any]]:
    user = challenge.user
    read_items = list(get_read_book_items(user, challenge.month))
    read_book_ids = {item.book_id for item in read_items}
    totals = get_monthly_log_totals(user, challenge.month)

    if challenge.kind == MonthlyChallenge.Kind.MINI_BOOKS:
        target = int(challenge.target_books or 0)
        completed = target > 0 and len(read_book_ids) >= target
        percent = min(100, round((len(read_book_ids) / target) * 100)) if target else 0
    elif challenge.kind == MonthlyChallenge.Kind.BOOK_LIST:
        selected_ids = set(challenge.books.values_list("book_id", flat=True))
        target = len(selected_ids)
        done = len(selected_ids & read_book_ids)
        completed = target >= MONTHLY_BOOK_LIST_MIN_BOOKS and done >= target
        percent = min(100, round((done / target) * 100)) if target else 0
    else:
        checks = []
        if challenge.target_pages:
            checks.append(totals["pages"] >= challenge.target_pages)
        if challenge.target_minutes:
            checks.append(totals["minutes"] >= challenge.target_minutes)
        completed = bool(checks) and all(checks)
        page_percent = min(100, round((totals["pages"] / challenge.target_pages) * 100)) if challenge.target_pages else 0
        minute_percent = min(100, round((totals["minutes"] / challenge.target_minutes) * 100)) if challenge.target_minutes else 0
        percent = min(page_percent, minute_percent) if challenge.target_pages and challenge.target_minutes else max(page_percent, minute_percent)

    return completed, {
        "read_items": read_items,
        "read_book_ids": read_book_ids,
        "log_totals": totals,
        "progress_percent": percent,
    }


def ensure_award_state(challenge: MonthlyChallenge, completed: bool) -> MonthlyChallenge:
    if completed and not challenge.awarded_at:
        challenge.awarded_at = timezone.now()
        challenge.save(update_fields=["awarded_at", "updated_at"])
    return challenge


def serialize_monthly_challenge(request, user, kind: str, *, month: date | str | None = None, book_query: str | None = None) -> dict[str, Any]:
    challenge_month = parse_month(month)
    challenge = get_or_create_challenge(user, kind, challenge_month)
    completed, progress = calculate_completion(challenge)
    ensure_award_state(challenge, completed)

    selected_books = list(
        challenge.books.select_related("book")
        .prefetch_related("book__authors")
        .order_by("order", "id")
    )
    read_book_ids = progress["read_book_ids"]
    books = [
        serialize_book(
            request,
            item.book,
            extra={
                "is_read": item.book_id in read_book_ids,
                "status": "completed" if item.book_id in read_book_ids else "planned",
            },
        )
        for item in selected_books
    ]
    read_books = [
        serialize_book(
            request,
            item.book,
            extra={
                "read_at": item.added_at.isoformat() if item.added_at else None,
                "read_at_display": timezone.localtime(item.added_at).strftime("%d.%m.%Y") if item.added_at else None,
                "is_read": True,
            },
        )
        for item in progress["read_items"][:30]
    ]
    log_totals = progress["log_totals"]
    is_configured = monthly_goal_is_configured(challenge)
    award_earned = bool(challenge.awarded_at or completed)

    return {
        "kind": kind,
        "slug": slug_from_kind(kind),
        "title": MONTHLY_CHALLENGE_TITLES[kind],
        "description": MONTHLY_CHALLENGE_DESCRIPTIONS[kind],
        "month": challenge.month.isoformat(),
        "month_key": month_display(challenge.month),
        "month_display": month_display(challenge.month),
        "deadline_display": deadline_display(challenge.month),
        "target_books": challenge.target_books,
        "target_pages": challenge.target_pages,
        "target_minutes": challenge.target_minutes,
        "progress_books": len({item.book_id for item in progress["read_items"]}),
        "progress_pages": log_totals["pages"],
        "progress_minutes": log_totals["minutes"],
        "progress_percent": progress["progress_percent"],
        "is_configured": is_configured,
        "is_completed": award_earned,
        "goal_edit_payment": get_monthly_goal_edit_payment(user, challenge),
        "awarded_at": challenge.awarded_at.isoformat() if challenge.awarded_at else None,
        "award_url": build_monthly_challenge_award_url(kind, month=challenge.month, awarded=award_earned),
        "locked_award_url": build_monthly_challenge_award_url(kind, month=challenge.month, state=1),
        "earned_award_url": build_monthly_challenge_award_url(kind, month=challenge.month, state=2),
        "books": books,
        "read_books": read_books,
        "available_books": get_available_books_for_list(request, user, challenge, query=book_query) if kind == MonthlyChallenge.Kind.BOOK_LIST else [],
        "book_query": (book_query or "").strip(),
    }


def serialize_monthly_game_card(kind: str, *, month: date | None = None) -> dict[str, Any]:
    challenge_month = month or current_month_start()
    return {
        "slug": slug_from_kind(kind),
        "title": MONTHLY_CHALLENGE_TITLES[kind],
        "description": MONTHLY_CHALLENGE_DESCRIPTIONS[kind],
        "status": "available",
        "mechanic": "monthly",
        "badge": month_display(challenge_month),
        "highlights": list(MONTHLY_CHALLENGE_HIGHLIGHTS[kind]),
        "icon_url": build_monthly_challenge_award_url(kind, month=challenge_month, state=1),
        "site_path": f"/games/{slug_from_kind(kind)}/",
    }


def monthly_game_detail(request, user, kind: str, *, book_query: str | None = None) -> dict[str, Any]:
    game = serialize_monthly_game_card(kind)
    challenge = serialize_monthly_challenge(request, user, kind, book_query=book_query)
    return {
        **game,
        "summary": game["description"],
        "stats": [
            {"label": "Месяц", "value": challenge["month_display"], "hint": "дедлайн " + challenge["deadline_display"]},
            {"label": "Прогресс", "value": f"{challenge['progress_percent']}%", "hint": "по цели"},
            {"label": "Награда", "value": "получена" if challenge["is_completed"] else "закрыта", "hint": "до выполнения"},
        ],
        "checklist": list(MONTHLY_CHALLENGE_HIGHLIGHTS[kind]),
        "sections": [],
        "stages": [],
        "monthly_game": challenge,
    }


@transaction.atomic
def save_monthly_challenge(user, kind: str, payload: dict[str, Any]) -> MonthlyChallenge:
    challenge = get_or_create_challenge(user, kind, parse_month(payload.get("month")))
    challenge = MonthlyChallenge.objects.select_for_update().get(pk=challenge.pk)
    was_configured = monthly_goal_is_configured(challenge)
    goal_changed = False
    update_fields: list[str] = []
    replacement_books: list[Book] | None = None

    if kind == MonthlyChallenge.Kind.MINI_BOOKS:
        target_books = parse_monthly_target(payload.get("target_books"))
        if target_books < MONTHLY_MINI_BOOKS_MIN_TARGET or target_books > 500:
            raise ValueError("Укажите количество книг от 2 до 500.")
        goal_changed = int(challenge.target_books or 0) != target_books
        challenge.target_books = target_books
        update_fields = ["target_books", "updated_at"]
    elif kind == MonthlyChallenge.Kind.PAGES_MINUTES:
        target_pages = parse_monthly_target(payload.get("target_pages"))
        target_minutes = parse_monthly_target(payload.get("target_minutes"))
        if target_pages <= 0 and target_minutes <= 0:
            raise ValueError("Укажите минимум 500 страниц или 600 минут.")
        if 0 < target_pages < MONTHLY_PAGES_MIN_TARGET:
            raise ValueError("Минимальная цель по страницам — 500.")
        if 0 < target_minutes < MONTHLY_MINUTES_MIN_TARGET:
            raise ValueError("Минимальная цель по минутам — 600.")
        normalized_pages = target_pages or None
        normalized_minutes = target_minutes or None
        goal_changed = (
            challenge.target_pages != normalized_pages
            or challenge.target_minutes != normalized_minutes
        )
        challenge.target_pages = normalized_pages
        challenge.target_minutes = normalized_minutes
        update_fields = ["target_pages", "target_minutes", "updated_at"]
    elif kind == MonthlyChallenge.Kind.BOOK_LIST:
        if hasattr(payload, "getlist"):
            raw_ids = payload.getlist("book_ids") or payload.getlist("books")
        else:
            raw_ids = payload.get("book_ids") or payload.get("books") or []
        if isinstance(raw_ids, str):
            raw_ids = [item.strip() for item in raw_ids.split(",") if item.strip()]
        book_ids = []
        for raw_id in raw_ids:
            try:
                book_ids.append(int(raw_id))
            except (TypeError, ValueError):
                continue
        book_ids = list(dict.fromkeys(book_ids))
        if len(book_ids) < MONTHLY_BOOK_LIST_MIN_BOOKS:
            raise ValueError("Выберите минимум 2 книги для списка.")
        books_by_id = {
            book.id: book
            for book in Book.objects.visible_to_user(user).filter(id__in=book_ids)
        }
        replacement_books = [books_by_id[book_id] for book_id in book_ids if book_id in books_by_id]
        if len(replacement_books) < MONTHLY_BOOK_LIST_MIN_BOOKS:
            raise ValueError("Выберите минимум 2 доступные книги для списка.")
        current_book_ids = list(
            challenge.books.order_by("order", "id").values_list("book_id", flat=True)
        )
        goal_changed = current_book_ids != [book.id for book in replacement_books]
    else:
        raise ValueError("Неизвестный ежемесячный вызов.")

    if was_configured and goal_changed:
        profile, _created = Profile.objects.get_or_create(user=user)
        profile = Profile.objects.select_for_update().get(pk=profile.pk)
        charge_feature_access(
            profile,
            cost=MONTHLY_CHALLENGE_GOAL_EDIT_COST,
            description=(
                "Изменение цели ежемесячной игры "
                f"«{MONTHLY_CHALLENGE_TITLES[kind]}» за {month_display(challenge.month)}"
            ),
        )

    if goal_changed:
        if kind == MonthlyChallenge.Kind.BOOK_LIST:
            MonthlyChallengeBook.objects.filter(challenge=challenge).delete()
            for index, book in enumerate(replacement_books or [], start=1):
                MonthlyChallengeBook.objects.create(
                    challenge=challenge,
                    book=book,
                    order=index,
                )
            challenge.save(update_fields=["updated_at"])
        else:
            challenge.save(update_fields=update_fields)

    completed, _progress = calculate_completion(challenge)
    ensure_award_state(challenge, completed)
    return challenge
