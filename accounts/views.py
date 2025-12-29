import base64
import calendar
import json
import logging
import math
import io
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import render, redirect, get_object_or_404

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .models import PremiumPayment, BookChallenge
from django.db.models import Count, Max, Sum, Prefetch
from django.http import JsonResponse, Http404, HttpResponse, QueryDict, HttpRequest
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.template.loader import render_to_string

from collections import Counter

from weasyprint import HTML, CSS

from PIL import Image, ImageDraw, ImageFont


from shelves.models import Shelf, ShelfItem, BookProgress, HomeLibraryEntry, ReadingLog
from shelves.services import (
    DEFAULT_HOME_LIBRARY_SHELF,
    DEFAULT_READ_SHELF,
    DEFAULT_READ_SHELF_ALIASES,
    DEFAULT_READING_SHELF,
    DEFAULT_UNFINISHED_SHELF,
    DEFAULT_WANT_SHELF,
    ALL_DEFAULT_READ_SHELF_NAMES,
    READING_PROGRESS_LABEL,
    ensure_default_shelves,
)
from books.models import Rating, Book
from user_ratings.models import LeaderboardPeriod, UserPointEvent

from .forms import SignUpForm, ProfileForm, RoleForm, PremiumPurchaseForm
from .models import YANDEX_AD_REWARD_COINS
from .yookassa import (
    YooKassaPaymentResult,
    create_payment as yookassa_create_payment,
)

from games.models import (
    BookExchangeChallenge,
    BookJourneyAssignment,
    ForgottenBookEntry,
    GameShelfState,
    NobelLaureateAssignment,
)
from games.services.book_journey import BookJourneyMap
from games.services.forgotten_books import ForgottenBooksGame
from games.services.nobel_challenge import NobelLaureatesChallenge
from reading_marathons.models import MarathonParticipant, ReadingMarathon
from reading_clubs.models import ReadingClub, ReadingParticipant

MONTH_NAMES = [
    "",
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
]

BOOK_CHALLENGE_START_YEAR = 2025


WEEKDAY_LABELS = [
    "Пн",
    "Вт",
    "Ср",
    "Чт",
    "Пт",
    "Сб",
    "Вс",
]

MARATHON_STATUS_LABELS = {
    "upcoming": "Скоро старт",
    "active": "Идёт",
    "past": "Завершён",
}


READING_CLUB_STATUS_LABELS = {
    "upcoming": "Скоро старт",
    "active": "Идёт",
    "past": "Завершено",
}


logger = logging.getLogger(__name__)


def _is_mobile_app_request(request) -> bool:
    header_name = getattr(settings, "MOBILE_APP_CLIENT_HEADER", "X-MyBooks-Client")
    allowed_clients = getattr(settings, "MOBILE_APP_ALLOWED_CLIENTS", [])
    client_id = request.headers.get(header_name, "")
    return client_id.lower() in allowed_clients


def _ensure_mobile_app_request(request):
    if not _is_mobile_app_request(request):
        raise Http404()


def _parse_int(value, default):
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_calendar_url(params, year, month):
    query = params.copy()
    query["tab"] = "stats"
    query["calendar_year"] = str(year)
    query["calendar_month"] = str(month)
    return f"?{query.urlencode()}"


def _build_reading_calendar(user: User, params, read_items_qs, period_meta):
    today = timezone.localdate()
    calendar_year = _parse_int(params.get("calendar_year"), None)
    calendar_month = _parse_int(params.get("calendar_month"), None)

    if calendar_year is None:
        calendar_year = period_meta.get("selected_year") or today.year
    if calendar_month is None:
        calendar_month = period_meta.get("selected_month") or today.month

    if calendar_month < 1 or calendar_month > 12:
        calendar_month = today.month

    first_day = date(calendar_year, calendar_month, 1)
    _, last_day_num = calendar.monthrange(calendar_year, calendar_month)
    last_day = date(calendar_year, calendar_month, last_day_num)

    day_records: dict[date, dict[str, object]] = {}

    def ensure_day(day: date):
        return day_records.setdefault(
            day,
            {
                "books": {},
                "completed_ids": set(),
                "pages_equivalent": Decimal("0"),
                "audio_seconds": 0,
                "reading_sessions": 0,
            },
        )

    logs = (
        ReadingLog.objects.filter(
            progress__user=user,
            log_date__gte=first_day,
            log_date__lte=last_day,
        )
        .select_related("progress__book")
        .prefetch_related("progress__book__authors")
        .order_by("log_date", "progress__book__title")
    )
    for log in logs:
        book = log.progress.book
        record = ensure_day(log.log_date)
        books_map = record["books"]
        record["reading_sessions"] = (record.get("reading_sessions") or 0) + 1
        if log.medium != BookProgress.FORMAT_AUDIO and log.pages_equivalent:
            record["pages_equivalent"] = record.get("pages_equivalent") + log.pages_equivalent
        if log.audio_seconds:
            record["audio_seconds"] = (record.get("audio_seconds") or 0) + log.audio_seconds
        if book.id not in books_map:
            books_map[book.id] = {
                "id": book.id,
                "title": book.title,
                "cover_url": _resolve_cover(book),
                "authors": [author.name for author in book.authors.all()],
                "detail_url": reverse("book_detail", args=[book.id]),
                "pages_equivalent": Decimal("0"),
                "audio_seconds": 0,
            }

        if log.medium != BookProgress.FORMAT_AUDIO and log.pages_equivalent:
            books_map[book.id]["pages_equivalent"] = (
                books_map[book.id].get("pages_equivalent") or Decimal("0")
            ) + log.pages_equivalent

        if log.audio_seconds:
            books_map[book.id]["audio_seconds"] = (
                books_map[book.id].get("audio_seconds") or 0
            ) + log.audio_seconds

    if read_items_qs is not None:
        completed_items = (
            read_items_qs.filter(
                added_at__date__gte=first_day,
                added_at__date__lte=last_day,
            )
            .select_related("book")
            .prefetch_related("book__authors")
            .order_by("added_at")
        )
        for item in completed_items:
            added_at = timezone.localtime(item.added_at)
            finished_day = added_at.date()
            book = item.book
            record = ensure_day(finished_day)
            books_map = record["books"]
            if book.id not in books_map:
                books_map[book.id] = {
                    "id": book.id,
                    "title": book.title,
                    "cover_url": _resolve_cover(book),
                    "authors": [author.name for author in book.authors.all()],
                    "detail_url": reverse("book_detail", args=[book.id]),
                    "pages_equivalent": Decimal("0"),
                    "audio_seconds": 0,
                }
            record["completed_ids"].add(book.id)

    cal = calendar.Calendar(firstweekday=0)
    weeks = []
    has_activity = False
    month_pages_total = Decimal("0")
    month_reading_days: set[date] = set()
    month_completed_ids: set[int] = set()
    day_payloads: dict[str, dict[str, object]] = {}
    for week in cal.monthdatescalendar(calendar_year, calendar_month):
        week_days = []
        for day in week:
            record = day_records.get(day)
            books = []
            is_completion_day = False
            pages_total = Decimal("0")
            audio_seconds = 0
            reading_sessions = 0
            audio_minutes = None
            if record and day.month == calendar_month:
                completion_ids = record["completed_ids"]
                books = []
                for book_id, info in record["books"].items():
                    book_pages = _decimal_to_number(
                        info.get("pages_equivalent") or Decimal("0")
                    )
                    book_audio_seconds = info.get("audio_seconds") or 0
                    books.append(
                        {
                            "id": book_id,
                            "title": info["title"],
                            "cover_url": info["cover_url"],
                            "detail_url": info.get("detail_url"),
                            "authors": info.get("authors", []),
                            "is_completion": book_id in completion_ids,
                            "pages_total": book_pages,
                            "audio_minutes": math.ceil(book_audio_seconds / 60)
                            if book_audio_seconds
                            else None,
                            "audio_display": _format_duration(
                                timedelta(seconds=book_audio_seconds)
                            )
                            if book_audio_seconds
                            else None,
                        }
                    )
                books = sorted(books, key=lambda entry: entry["title"].lower())
                is_completion_day = bool(completion_ids)
                has_activity = True
                pages_total = record.get("pages_equivalent") or Decimal("0")
                audio_seconds = record.get("audio_seconds") or 0
                audio_minutes = math.ceil(audio_seconds / 60) if audio_seconds else None
                reading_sessions = record.get("reading_sessions") or 0
                if pages_total > 0:
                    month_pages_total += pages_total
                if completion_ids:
                    month_completed_ids.update(completion_ids)
                if pages_total > 0 or books:
                    month_reading_days.add(day)
            week_days.append(
                {
                    "date": day,
                    "in_month": day.month == calendar_month,
                    "books": books,
                    "is_completion_day": is_completion_day,
                    "pages_total": _decimal_to_number(pages_total),
                    "books_count": len(books),
                    "audio_minutes": audio_minutes,
                    "audio_display": _format_duration(timedelta(seconds=audio_seconds))
                    if audio_seconds
                    else None,
                    "reading_sessions": reading_sessions,
                }
            )
            if day.month == calendar_month:
                iso_date = day.isoformat()
                day_payloads[iso_date] = {
                    "date": iso_date,
                    "date_display": day.strftime("%d.%m.%Y"),
                    "pages_total": _decimal_to_number(pages_total),
                    "books_count": len(books),
                    "audio_minutes": audio_minutes,
                    "audio_display": _format_duration(timedelta(seconds=audio_seconds))
                    if audio_seconds
                    else None,
                    "reading_sessions": reading_sessions,
                    "books": books,
                    "has_completion": is_completion_day,
                }
        weeks.append(week_days)

    prev_month_anchor = first_day - timedelta(days=1)
    next_month_anchor = last_day + timedelta(days=1)
    prev_month_start = date(prev_month_anchor.year, prev_month_anchor.month, 1)
    next_month_start = date(next_month_anchor.year, next_month_anchor.month, 1)

    month_name = MONTH_NAMES[calendar_month] if 1 <= calendar_month < len(MONTH_NAMES) else str(calendar_month)

    month_stats = None
    if month_pages_total > 0 or month_completed_ids or month_reading_days:
        avg_pages = None
        if month_reading_days:
            avg_pages = (
                month_pages_total
                / Decimal(len(month_reading_days))
            ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        month_stats = {
            "pages_total": _decimal_to_number(month_pages_total),
            "books_count": len(month_completed_ids),
            "reading_days": len(month_reading_days),
            "avg_pages": _decimal_to_number(avg_pages) if avg_pages is not None else None,
        }

    return {
        "year": calendar_year,
        "month": calendar_month,
        "month_name": month_name,
        "weeks": weeks,
        "weekday_labels": WEEKDAY_LABELS,
        "has_activity": has_activity,
        "prev_url": _build_calendar_url(params, prev_month_start.year, prev_month_start.month),
        "next_url": _build_calendar_url(params, next_month_start.year, next_month_start.month),
        "month_totals": month_stats,
        "day_payloads": day_payloads,
    }


def _resolve_book_challenge_year(request: HttpRequest) -> tuple[int, list[int]]:
    today = timezone.localdate()
    start_year = BOOK_CHALLENGE_START_YEAR
    end_year = max(start_year, today.year)
    available_years = list(range(start_year, end_year + 1))

    selected_year = None
    raw_year = request.POST.get("book_challenge_year") or request.GET.get("book_challenge_year")
    if raw_year:
        try:
            selected_year = int(raw_year)
        except (TypeError, ValueError):
            selected_year = None

    if selected_year not in available_years:
        selected_year = today.year if today.year >= start_year else start_year
        if selected_year not in available_years:
            selected_year = available_years[-1]

    return selected_year, available_years


def _calculate_total_pages_for_period(user: User, start: date, end: date) -> Decimal:
    read_items = (
        ShelfItem.objects.filter(
            shelf__user=user,
            shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
            added_at__date__gte=start,
            added_at__date__lte=end,
        )
        .select_related("book")
    )

    book_ids = list(read_items.values_list("book_id", flat=True))
    progress_map = {
        progress.book_id: progress
        for progress in BookProgress.objects.filter(
            user=user,
            event__isnull=True,
            book_id__in=book_ids,
        )
    }

    total_pages = Decimal("0")
    for item in read_items:
        progress = progress_map.get(item.book_id)
        if progress and progress.is_audiobook:
            continue
        if progress:
            pages = progress.get_effective_total_pages() or 0
        else:
            pages = item.book.get_total_pages() or 0
        if pages:
            total_pages += Decimal(str(pages))

    logs_aggregate = (
        ReadingLog.objects.filter(
            progress__user=user,
            log_date__gte=start,
            log_date__lte=end,
        )
        .order_by()
        .values("medium")
        .annotate(pages_total=Sum("pages_equivalent"))
        .values("medium", "pages_total")
    )

    logged_pages_total = Decimal("0")
    for entry in logs_aggregate:
        medium = entry.get("medium")
        pages_total = entry.get("pages_total") or Decimal("0")
        if not isinstance(pages_total, Decimal):
            pages_total = Decimal(str(pages_total))
        if medium != BookProgress.FORMAT_AUDIO:
            logged_pages_total += pages_total

    if logged_pages_total > 0:
        total_pages = logged_pages_total

    return total_pages


def _calculate_latest_monthly_average(user: User, year: int) -> int | None:
    latest_read = (
        ShelfItem.objects.filter(
            shelf__user=user,
            shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
            added_at__year=year,
        )
        .aggregate(latest=Max("added_at"))
        .get("latest")
    )
    latest_log = (
        ReadingLog.objects.filter(
            progress__user=user,
            log_date__year=year,
        )
        .aggregate(latest=Max("log_date"))
        .get("latest")
    )

    latest_date = None
    for candidate in (latest_read, latest_log):
        if not candidate:
            continue
        if isinstance(candidate, datetime):
            candidate = candidate.date()
        if latest_date is None or candidate > latest_date:
            latest_date = candidate

    if not latest_date:
        return None

    month = latest_date.month
    _, last_day = calendar.monthrange(year, month)
    start = date(year, month, 1)
    end = date(year, month, last_day)

    total_pages = _calculate_total_pages_for_period(user, start, end)
    if total_pages <= 0:
        return None

    days_count = max(1, (end - start).days + 1)
    pages_average = (
        total_pages
        / Decimal(days_count)
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return int(pages_average)


def _format_duration(value):
    if not value:
        return None
    total_seconds = int(value.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _decimal_to_number(value):
    if value is None:
        return None
    if not isinstance(value, Decimal):
        return value
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _resolve_cover(book: Book) -> str:
    return book.get_cover_url()


def _resolve_stats_period(params, read_items, reading_logs=None):
    today = timezone.localdate()
    period = params.get("period", "week")

    reading_logs = reading_logs or ReadingLog.objects.none()

    available_years = sorted(
        {
            d.year
            for d in read_items.dates("added_at", "year", order="DESC")
        }
        | {d.year for d in reading_logs.dates("log_date", "year", order="DESC")},
        reverse=True,
    )
    selected_year = today.year
    if available_years:
        selected_year = available_years[0]
    if params.get("year"):
        try:
            selected_year = int(params["year"])
        except (TypeError, ValueError):
            selected_year = today.year
        if selected_year not in available_years and available_years:
            selected_year = available_years[0]

    available_months = []
    if available_years:
        month_dates = read_items.filter(added_at__year=selected_year).dates(
            "added_at", "month", order="DESC"
        )
        month_logs = reading_logs.filter(log_date__year=selected_year).dates(
            "log_date", "month", order="DESC"
        )
        available_months = sorted(
            {d.month for d in month_dates} | {d.month for d in month_logs},
            reverse=True,
        )

    selected_month = today.month
    if available_months:
        selected_month = available_months[0]
    if params.get("month"):
        try:
            selected_month = int(params["month"])
        except (TypeError, ValueError):
            selected_month = today.month
        if selected_month not in available_months and available_months:
            selected_month = available_months[0]

    available_days_all = sorted(
        {
            d
            for d in read_items.dates("added_at", "day", order="DESC")
        }
        | {d for d in reading_logs.dates("log_date", "day", order="DESC")},
        reverse=True,
    )

    available_days = available_days_all
    if period == "day" and available_days_all:
        days_for_year = [d for d in available_days_all if d.year == selected_year]
        if days_for_year:
            available_days = days_for_year
        if params.get("month"):
            days_for_month = [d for d in available_days if d.month == selected_month]
            if days_for_month:
                available_days = days_for_month

    selected_day = today
    if available_days:
        selected_day = available_days[0]

    if params.get("date"):
        try:
            selected_day = date.fromisoformat(params["date"])
        except (TypeError, ValueError):
            selected_day = today
        if selected_day not in available_days and available_days:
            selected_day = available_days[0]

    if period == "year":
        year = selected_year or today.year
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        label = f"{year} год"
    elif period == "month":
        year = selected_year or today.year
        month = selected_month or today.month
        _, last_day = calendar.monthrange(year, month)
        start = date(year, month, 1)
        end = date(year, month, last_day)
        month_name = MONTH_NAMES[month] if 1 <= month < len(MONTH_NAMES) else str(month)
        label = f"{month_name} {year}"
    elif period == "day":
        period = "day"
        day = selected_day or today
        start = day
        end = day
        month_name = MONTH_NAMES[day.month] if 1 <= day.month < len(MONTH_NAMES) else str(day.month)
        label = f"{day.day} {month_name} {day.year}"
        selected_year = day.year
        selected_month = day.month
    else:
        end = today
        start = today - timedelta(days=6)
        label = "Последние 7 дней"
        period = "week"

    available_days_meta = [
        {
            "iso": d.isoformat(),
            "display": d.strftime("%d.%m.%Y"),
        }
        for d in available_days
    ]
    first_available_day = available_days_meta[0] if available_days_meta else None
    last_available_day = available_days_meta[-1] if available_days_meta else None

    return {
        "period": period,
        "start": start,
        "end": end,
        "label": label,
        "available_years": available_years,
        "available_months": [
            {"value": m, "label": MONTH_NAMES[m]} for m in available_months
        ],
        "available_days": available_days_meta,
        "first_available_day": first_available_day,
        "last_available_day": last_available_day,
        "selected_year": selected_year,
        "selected_month": selected_month,
        "selected_day": selected_day if period == "day" else None,
    }


def _build_book_challenge_context(user: User, year: int, available_years: list[int]) -> dict[str, object]:
    today = timezone.localdate()␊
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    reference_date = min(max(today, start), end)

    challenge = BookChallenge.objects.filter(user=user, year=year).first()
    goal = challenge.goal if challenge and challenge.goal else None

    read_items = (
        ShelfItem.objects.filter(
            shelf__user=user,
            shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
            added_at__date__gte=start,
            added_at__date__lte=end,
        )
        .select_related("book")
        .order_by("-added_at")
    )
    year_books_count = read_items.count()

    monthly_counts_qs = (
        read_items.values("added_at__month")
        .annotate(total=Count("id"))
        .values("added_at__month", "total")
    )
    monthly_counts = {
        entry["added_at__month"]: entry["total"]
        for entry in monthly_counts_qs
        if entry.get("added_at__month")
    }

    monthly_covers: dict[int, list[dict[str, object]]] = {month: [] for month in range(1, 13)}
    max_covers = 6
    max_month = 12 if year != today.year else today.month
    for item in read_items:
        month = item.added_at.month
        if month > max_month:
            continue
        covers = monthly_covers[month]
        if len(covers) >= max_covers:
            continue
        cover_url = _resolve_cover(item.book)
        if cover_url:
            covers.append({"book": item.book, "cover_url": cover_url})

    month_labels = [MONTH_NAMES[month] for month in range(1, 13)]
    month_values = [monthly_counts.get(month, 0) for month in range(1, 13)]

    avg_pages_per_day = _calculate_latest_monthly_average(user, year)

    books_remaining = None
    monthly_goal = None
    target_by_month = None
    books_needed_this_month = None
    recommended_pages = None
    if goal:
        books_remaining = max(goal - year_books_count, 0)
        monthly_goal = int(math.ceil(goal / 12))
        target_by_month = int(math.ceil(goal * reference_date.month / 12))
        books_needed_this_month = max(target_by_month - year_books_count, 0)
        if avg_pages_per_day and books_remaining > 0:
            days_remaining = max(1, (end - reference_date).days + 1)
            max_pages_total = avg_pages_per_day * days_remaining
            recommended_pages = int(max_pages_total // books_remaining) if max_pages_total > 0 else 0

    monthly_summaries = []
    summary_end_month = 12 if year != today.year else today.month
    for month in range(1, summary_end_month + 1):
        total = monthly_counts.get(month, 0)
        covers = monthly_covers.get(month, [])
        monthly_summaries.append(
            {
                "month": month,
                "label": MONTH_NAMES[month],
                "total": total,
                "covers": covers,
                "extra_count": max(total - len(covers), 0),
            }
        )

    return {
        "year": year,
        "available_years": available_years,
        "goal": goal,
        "year_books_count": year_books_count,
        "books_remaining": books_remaining,
        "monthly_goal": monthly_goal,
        "target_by_month": target_by_month,
        "books_needed_this_month": books_needed_this_month,
        "avg_pages_per_day": avg_pages_per_day,
        "recommended_pages": recommended_pages,
        "month_labels": month_labels,
        "month_values": month_values,
        "current_month_label": MONTH_NAMES[reference_date.month],
        "monthly_summaries": monthly_summaries,
    }


def _collect_home_library_summary(user: User):
    shelf = Shelf.objects.filter(user=user, name=DEFAULT_HOME_LIBRARY_SHELF).first()
    summary = {
        "total": 0,
        "disposed_total": 0,
        "classic_count": 0,
        "modern_count": 0,
        "series_counts": [],
        "genre_counts": [],
        "top_locations": [],
        "top_statuses": [],
    }
    if not shelf:
        return summary

    entries_qs = (
        HomeLibraryEntry.objects.filter(shelf_item__shelf=shelf)
        .order_by()
    )
    active_entries = entries_qs.filter(is_disposed=False)
    disposed_total = entries_qs.filter(is_disposed=True).count()

    total_items = active_entries.count()
    summary["total"] = total_items
    summary["disposed_total"] = disposed_total
    classic_count = active_entries.filter(is_classic=True).count()
    summary["classic_count"] = classic_count
    summary["modern_count"] = total_items - classic_count

    summary["series_counts"] = list(
        active_entries
        .exclude(series_name="")
        .values("series_name")
        .annotate(total=Count("id"))
        .values("series_name", "total")
        .order_by("-total", "series_name")[:5]
    )
    summary["genre_counts"] = [
        {
            "name": row["custom_genres__name"],
            "total": row["total"],
        }
        for row in (
            active_entries
            .values("custom_genres__name")
            .annotate(total=Count("custom_genres"))
            .values("custom_genres__name", "total")
            .exclude(custom_genres__name__isnull=True)
            .order_by("-total", "custom_genres__name")[:5]
        )
    ]

    summary["top_locations"] = list(
         active_entries
        .exclude(location="")
        .values("location")
        .annotate(total=Count("id"))
        .values("location", "total")
        .order_by("-total", "location")[:5]
    )
    summary["top_statuses"] = list(
        entries_qs
        .exclude(status="")
        .values("status")
        .annotate(total=Count("id"))
        .values("status", "total")
        .order_by("-total", "status")[:5]
    )

    return summary


def _collect_profile_stats(user: User, params):
    home_summary = _collect_home_library_summary(user)
    read_items = ShelfItem.objects.filter(
        shelf__user=user,
        shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
    )
    reading_logs = ReadingLog.objects.filter(progress__user=user)
    today = timezone.localdate()
    if not read_items.exists() and not reading_logs.exists():
        period_meta = {
            "period": "week",
            "label": "Последние 7 дней",
            "start": today - timedelta(days=6),
            "end": today,
            "available_years": [],
            "available_months": [],
            "selected_year": today.year,
            "selected_month": today.month,
        }
        calendar_payload = _build_reading_calendar(user, params, None, period_meta)
        return {
            "stats": {
                "books": [],
                "genre_labels": [],
                "genre_values": [],
                "format_labels": [],
                "format_values": [],
                "format_palette": [],
                "pages_total": 0,
                "pages_average": None,
                "audio_total_display": None,
                "audio_adjusted_display": None,
                "audio_tracked_display": None,
                "home_library": home_summary,
                "reading_calendar": calendar_payload,
            },
            "stats_period": period_meta,
        }

    period_meta = _resolve_stats_period(params, read_items, reading_logs)
    start = period_meta["start"]
    end = period_meta["end"]

    filtered_items = read_items.filter(
        added_at__date__gte=start,
        added_at__date__lte=end,
    ).select_related("book")
    book_ids = list(filtered_items.values_list("book_id", flat=True))

    books = Book.objects.filter(id__in=book_ids).prefetch_related("genres", "authors", "isbn", "primary_isbn")
    progress_map = {
        bp.book_id: bp
        for bp in BookProgress.objects.filter(
            user=user,
            event__isnull=True,
            book_id__in=book_ids,
        )
    }
    rating_map = {
        rating.book_id: rating
        for rating in Rating.objects.filter(user=user, book_id__in=book_ids)
        if rating.review
    }

    book_entries = []
    total_pages = Decimal("0")
    for item in filtered_items.order_by("-added_at"):
        book = item.book
        progress = progress_map.get(book.id)
        has_review = book.id in rating_map
        review_url = reverse("book_detail", args=[book.pk])
        if has_review:
            review_url = f"{review_url}#reviews"
        else:
            review_url = f"{review_url}#write-review"

        entry = {
            "book": book,
            "cover_url": _resolve_cover(book),
            "has_review": has_review,
            "review_url": review_url,
            "format": progress.get_format_display() if progress else None,
        }
        book_entries.append(entry)

        if progress and progress.is_audiobook:
            continue
        pages = 0
        if progress:
            pages = progress.get_effective_total_pages() or 0
        else:
            pages = book.get_total_pages() or 0
        if pages:
            total_pages += Decimal(str(pages))

    genre_stats = (
        books.values("genres__name")
        .annotate(total=Count("genres__id", distinct=True))
        .values("genres__name", "total")
        .exclude(genres__name__isnull=True)
        .order_by("-total")
    )
    genre_labels = [row["genres__name"] for row in genre_stats]
    genre_values = [row["total"] for row in genre_stats]

    logs_aggregate = (
        ReadingLog.objects.filter(
            progress__user=user,
            log_date__gte=start,
            log_date__lte=end,
        )
        .order_by()
        .values("medium")
        .annotate(
            pages_total=Sum("pages_equivalent"),
            audio_total=Sum("audio_seconds"),
        )
        .values("medium", "pages_total", "audio_total")
    )
    format_totals = {
        code: Decimal("0")
        for code, _ in BookProgress.FORMAT_CHOICES
    }
    audio_tracked_seconds = 0
    logged_pages_total = Decimal("0")
    for entry in logs_aggregate:
        medium = entry.get("medium")
        pages_total = entry.get("pages_total") or Decimal("0")
        if not isinstance(pages_total, Decimal):
            pages_total = Decimal(str(pages_total))

        contribution = pages_total
        if medium == BookProgress.FORMAT_AUDIO:
            audio_total_seconds = entry.get("audio_total")
            if audio_total_seconds:
                audio_tracked_seconds += int(audio_total_seconds)
                if contribution == 0:
                    contribution = Decimal(str(audio_total_seconds)) / Decimal("60")
        else:
            logged_pages_total += pages_total

        if contribution > 0 and medium in format_totals:
            format_totals[medium] += contribution

    if logged_pages_total > 0:
        total_pages = logged_pages_total

    audio_total = timedelta()
    audio_adjusted = timedelta()
    for book_id in book_ids:
        progress = progress_map.get(book_id)
        if not progress or not progress.is_audiobook or not progress.audio_length:
            continue
        audio_total += progress.audio_length
        adjusted = progress.get_audio_adjusted_length()
        audio_adjusted += adjusted or progress.audio_length

    format_display_map = dict(BookProgress.FORMAT_CHOICES)
    format_palette_map = {
        BookProgress.FORMAT_PAPER: "#9b7d61",
        BookProgress.FORMAT_EBOOK: "#daa38f",
        BookProgress.FORMAT_AUDIO: "#92ada4",
    }
    total_equivalent = sum(format_totals.values(), Decimal("0"))
    format_labels: list[str] = []
    format_values: list[float] = []
    format_palette: list[str] = []
    if total_equivalent > 0:
        for medium_code in (
            BookProgress.FORMAT_PAPER,
            BookProgress.FORMAT_EBOOK,
            BookProgress.FORMAT_AUDIO,
        ):
            value = format_totals.get(medium_code) or Decimal("0")
            if value <= 0:
                continue
            percent = (
                value
                / total_equivalent
                * Decimal("100")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            format_labels.append(format_display_map.get(medium_code, medium_code))
            format_values.append(float(percent))
            format_palette.append(
                format_palette_map.get(medium_code, "#4dabf7")
            )

    audio_tracked_display = None
    if audio_tracked_seconds > 0:
        tracked_duration = timedelta(seconds=audio_tracked_seconds)
        audio_tracked_display = _format_duration(tracked_duration)
        if audio_total.total_seconds() == 0:
            audio_total = tracked_duration
        if audio_adjusted.total_seconds() == 0:
            audio_adjusted = tracked_duration

    days_count = max(1, (end - start).days + 1)
    pages_average = None
    if total_pages > 0:
        pages_average = (
            total_pages
            / Decimal(days_count)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    stats = {
        "books": book_entries,
        "genre_labels": genre_labels,
        "genre_values": genre_values,
        "format_labels": format_labels,
        "format_values": format_values,
        "format_palette": format_palette,
        "pages_total": _decimal_to_number(total_pages),
        "pages_average": _decimal_to_number(pages_average),
        "audio_total_display": _format_duration(audio_total),
        "audio_adjusted_display": _format_duration(audio_adjusted),
        "audio_tracked_display": audio_tracked_display,
        "home_library": home_summary,
    }

    stats["reading_calendar"] = _build_reading_calendar(user, params, read_items, period_meta)

    return {
        "stats": stats,
        "stats_period": period_meta,
    }


def _collect_leaderboard_snapshot(user: User) -> dict[str, dict[str, object]]:
    """Return rating leaderboard stats for the user's profile page."""

    snapshot: dict[str, dict[str, object]] = {}

    period_map: dict[str, LeaderboardPeriod] = {
        "day": LeaderboardPeriod.DAY,
        "week": LeaderboardPeriod.WEEK,
        "month": LeaderboardPeriod.MONTH,
        "year": LeaderboardPeriod.YEAR,
    }

    for key, period in period_map.items():
        aggregated = (
            UserPointEvent.objects
            .for_period(period)
            .values("user")
            .annotate(total_points=Sum("points"))
        )

        user_points = (
            aggregated
            .filter(user=user.id)
            .order_by("user")
            .values_list("total_points", flat=True)
            .first()
        )
        total_participants = aggregated.count()
        has_points = bool(user_points)

        position = None
        if has_points:
            better_count = aggregated.filter(total_points__gt=user_points).count()
            equal_before_count = aggregated.filter(total_points=user_points, user__lt=user.id).count()
            position = better_count + equal_before_count + 1

        snapshot[key] = {
            "label": period.label,
            "period": period.value,
            "points": int(user_points or 0),
            "position": position,
            "total_participants": total_participants,
            "has_points": has_points,
        }

    overall_totals = (
        UserPointEvent.objects
        .values("user")
        .annotate(total_points=Sum("points"))
    )
    overall_points = (
        overall_totals
        .filter(user=user.id)
        .order_by("user")
        .values_list("total_points", flat=True)
        .first()
    )
    overall_participants = overall_totals.count()
    overall_has_points = bool(overall_points)
    overall_position = None
    if overall_has_points:
        better_count = overall_totals.filter(total_points__gt=overall_points).count()
        equal_before_count = overall_totals.filter(total_points=overall_points, user__lt=user.id).count()
        overall_position = better_count + equal_before_count + 1

    snapshot["all_time"] = {
        "label": "За всё время",
        "period": "all_time",
        "points": int(overall_points or 0),
        "position": overall_position,
        "total_participants": overall_participants,
        "has_points": overall_has_points,
    }

    snapshot["has_any_points"] = any(
        entry.get("has_points") for entry in snapshot.values() if isinstance(entry, dict)
    )

    return snapshot


def _build_absolute_url(request, url: str | None) -> str | None:
    if not url:
        return None
    url = str(url).strip()
    if not url:
        return None
    if url.startswith("//"):
        return f"{request.scheme}:{url}"
    if url.startswith("/"):
        return request.build_absolute_uri(url)
    return url


@login_required
def statistics_overview(request):
    challenge_year, challenge_years = _resolve_book_challenge_year(request)
    if request.method == "POST" and request.POST.get("form_type") == "book_challenge":
        raw_goal = (request.POST.get("book_challenge_goal") or "").strip()
        challenge = BookChallenge.objects.filter(user=request.user, year=challenge_year).first()
        if raw_goal:
            try:␊
                goal_value = int(raw_goal)
            except (TypeError, ValueError):
                goal_value = None
            if goal_value and goal_value > 0:
                BookChallenge.objects.update_or_create(
                    user=request.user,
                    year=challenge_year,
                    defaults={"goal": goal_value},
                )
            elif challenge:
                challenge.delete()
        elif challenge:
            challenge.delete()

        redirect_url = request.path
        query_params = request.GET.copy()
        query_params["book_challenge_year"] = str(challenge_year)
        if query_params:
            redirect_url = f"{request.path}?{query_params.urlencode()}"
        return redirect(redirect_url)

    stats_payload = _collect_profile_stats(request.user, request.GET)

    stats_data = stats_payload.get("stats", {})

    context = {
        "stats": stats_data,
        "stats_period": stats_payload.get("stats_period", {}),
        "book_challenge": _build_book_challenge_context(
            request.user,
            challenge_year,
            challenge_years,
        ),
        "genre_pairs": list(
            zip(stats_data.get("genre_labels", []), stats_data.get("genre_values", []))
        ),
        "format_pairs": list(
            zip(stats_data.get("format_labels", []), stats_data.get("format_values", []))
        ),
        "page_title": "Статистика чтения",
    }

    return render(request, "accounts/statistics.html", context)


@login_required
def profile_monthly_print(request):
    """
    Генерация PDF версии месячного отчета о чтении
    """
    try:
        user = request.user
        today = timezone.localdate()

        def _safe_int(value, default):
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return default
            return parsed

        def _format_minutes_label(total_minutes: int) -> str | None:
            if total_minutes <= 0:
                return None
            hours, minutes = divmod(int(total_minutes), 60)
            if hours and minutes:
                return f"{hours} ч {minutes} мин"
            if hours:
                return f"{hours} ч"
            return f"{minutes} мин"

        year = _safe_int(request.GET.get("year"), today.year)
        month = _safe_int(request.GET.get("month"), today.month)
        if month < 1 or month > 12:
            month = today.month

        params = QueryDict(mutable=True)
        params.update(
            {
                "period": "month",
                "year": str(year),
                "month": str(month),
                "calendar_year": str(year),
                "calendar_month": str(month),
                "tab": "stats",
            }
        )

        stats_payload = _collect_profile_stats(user, params)
        stats = stats_payload.get("stats", {})
        calendar_payload = stats.get("reading_calendar") or {}
        calendar_year = calendar_payload.get("year") or year
        calendar_month = calendar_payload.get("month") or month
        try:
            _, last_day = calendar.monthrange(calendar_year, calendar_month)
        except ValueError:
            calendar_year, calendar_month = today.year, today.month
            _, last_day = calendar.monthrange(calendar_year, calendar_month)

        month_name = calendar_payload.get("month_name")
        if not month_name and 1 <= calendar_month < len(MONTH_NAMES):
            month_name = MONTH_NAMES[calendar_month]

        day_payloads = calendar_payload.get("day_payloads") or {}
        daily_summary: list[dict[str, object]] = []
        max_pages = 0
        max_audio_minutes = 0
        max_sessions = 0
        total_audio_minutes = 0
        total_sessions = 0
        activity_dates: list[date] = []
        best_streak = 0
        current_streak = 0
        current_break = 0
        longest_break = 0
        top_day = None

        for day_number in range(1, last_day + 1):
            day_date = date(calendar_year, calendar_month, day_number)
            iso = day_date.isoformat()
            payload = day_payloads.get(iso) or {}
            pages = payload.get("pages_total") or 0
            books_count = payload.get("books_count") or 0
            audio_minutes = payload.get("audio_minutes") or 0
            sessions = payload.get("reading_sessions") or 0
            has_completion = bool(payload.get("has_completion"))
            has_activity = bool(pages or books_count or sessions or audio_minutes or has_completion)

            if has_activity:
                activity_dates.append(day_date)
                current_streak += 1
                current_break = 0
                if current_streak > best_streak:
                    best_streak = current_streak
            else:
                current_streak = 0
                current_break += 1
                if current_break > longest_break:
                    longest_break = current_break

            if not top_day or pages > top_day.get("pages", 0):
                top_day = {
                    "date": day_date,
                    "pages": pages,
                    "books": payload.get("books", []),
                    "books_count": books_count,
                    "audio_minutes": audio_minutes or 0,
                }

            max_pages = max(max_pages, pages or 0)
            max_audio_minutes = max(max_audio_minutes, audio_minutes or 0)
            max_sessions = max(max_sessions, sessions or 0)
            total_audio_minutes += audio_minutes or 0
            total_sessions += sessions or 0

            daily_summary.append(
                {
                    "date": day_date,
                    "iso": iso,
                    "display": day_date.strftime("%d.%m.%Y"),
                    "weekday": day_date.strftime("%a"),
                    "pages": pages or 0,
                    "books_count": books_count or 0,
                    "audio_minutes": audio_minutes or 0,
                    "sessions": sessions or 0,
                    "has_completion": has_completion,
                    "has_activity": has_activity,
                    "books": payload.get("books", []),
                    "audio_display": payload.get("audio_display"),
                }
            )

        for entry in daily_summary:
            pages_ratio = (entry["pages"] / max_pages) if max_pages else 0
            audio_ratio = (entry["audio_minutes"] / max_audio_minutes) if max_audio_minutes else 0
            sessions_ratio = (entry["sessions"] / max_sessions) if max_sessions else 0
            entry["pages_ratio"] = pages_ratio
            entry["audio_ratio"] = audio_ratio
            entry["sessions_ratio"] = sessions_ratio
            entry["pages_percent"] = int(round(pages_ratio * 100)) if pages_ratio else 0
            entry["audio_percent"] = int(round(audio_ratio * 100)) if audio_ratio else 0
            entry["sessions_percent"] = int(round(sessions_ratio * 100)) if sessions_ratio else 0

        total_audio_label = _format_minutes_label(total_audio_minutes)

        top_activity_days = sorted(
            (entry for entry in daily_summary if entry["has_activity"]),
            key=lambda value: (
                value["pages"],
                value["books_count"],
                value["audio_minutes"],
            ),
            reverse=True,
        )[:3]

        stats_period = stats_payload.get("stats_period") or {}
        month_totals = calendar_payload.get("month_totals") or {}
        month_overview = {
            "pages_total": month_totals.get("pages_total") or stats.get("pages_total") or 0,
            "books_count": month_totals.get("books_count") or len(stats.get("books", [])),
            "reading_days": month_totals.get("reading_days") or len(activity_dates),
            "avg_pages": month_totals.get("avg_pages") or stats.get("pages_average"),
        }

        format_breakdown = []
        for label, percent, color in zip(
            stats.get("format_labels", []),
            stats.get("format_values", []),
            stats.get("format_palette", []),
        ):
            format_breakdown.append(
                {
                    "label": label,
                    "percent": round(percent, 1),
                    "color": color,
                }
            )

        genre_values = stats.get("genre_values", [])
        genre_total = sum(genre_values)
        genre_breakdown = []
        for label, value in zip(stats.get("genre_labels", []), genre_values):
            percent = (value / genre_total * 100) if genre_total else 0
            genre_breakdown.append(
                {
                    "label": label,
                    "value": value,
                    "percent": round(percent, 1),
                }
            )

        stats_books = stats.get("books", [])
        book_ids = [entry.get("book").id for entry in stats_books if entry.get("book")]
        authors_map: dict[int, list[str]] = {}
        genres_map: dict[int, list[str]] = {}
        if book_ids:
            related_books = (
                Book.objects.filter(id__in=book_ids)
                .prefetch_related("authors", "genres")
            )
            for related in related_books:
                authors_map[related.id] = [author.name for author in related.authors.all()]
                genres_map[related.id] = [genre.name for genre in related.genres.all()]

        completed_books = []
        for entry in stats_books:
            book = entry.get("book")
            if not book:
                continue
            book_authors = authors_map.get(book.id, [])
            completed_books.append(
                {
                    "id": book.id,
                    "title": book.title,
                    "authors": book_authors,
                    "cover_url": _build_absolute_url(request, entry.get("cover_url")),
                    "format": entry.get("format"),
                    "has_review": entry.get("has_review"),
                    "review_url": entry.get("review_url"),
                    "genres": genres_map.get(book.id, []),
                }
            )

        author_counter = Counter()
        for entry in completed_books:
            for author in entry.get("authors", []):
                author_counter[author] += 1
        top_authors = author_counter.most_common(5)

        profile = getattr(user, "profile", None)
        avatar_url = None
        if profile and profile.avatar:
            avatar_url = _build_absolute_url(request, profile.avatar.url)

        highlights = {
            "best_streak": best_streak,
            "longest_break": longest_break,
            "activity_start": activity_dates[0] if activity_dates else None,
            "activity_end": activity_dates[-1] if activity_dates else None,
            "top_day": top_day,
        }

        def _render_chart_image(template_name: str, chart_context: dict[str, object]) -> str | None:
            """Render a higher-resolution chart into a base64 PNG for PDF embedding."""

            items = chart_context.get("items") or []
            if not items:
                return None

            scale = 3
            width, height = 720 * scale, 280 * scale
            padding = 20 * scale
            label_width = 170 * scale
            value_width = 120 * scale
            bar_gap = 12 * scale
            bar_height = 20 * scale
            title_offset = 28 * scale
            font_title_size = 20 * scale
            font_label_size = 14 * scale
            font_value_size = 14 * scale

            try:
                font_title = ImageFont.truetype("DejaVuSans.ttf", font_title_size)
                font_label = ImageFont.truetype("DejaVuSans.ttf", font_label_size)
                font_value = ImageFont.truetype("DejaVuSans-Bold.ttf", font_value_size)
            except Exception:  # pragma: no cover - fallback to default font
                font_title = font_label = font_value = ImageFont.load_default()

            img = Image.new("RGB", (width, height), color="#fff9f5")
            draw = ImageDraw.Draw(img)

            draw.text((padding, padding), chart_context.get("title", ""), fill="#8c4f42", font=font_title)

            available_height = height - padding * 2 - title_offset
            row_height = max(bar_height + bar_gap, int(available_height / max(len(items), 1)))
            bar_area_width = width - padding * 2 - label_width - value_width - (20 * scale)

            for index, item in enumerate(items):
                top = padding + title_offset + index * row_height
                label = str(item.get("label") or "")
                percent = max(0, min(float(item.get("percent") or 0), 100))
                value = str(item.get("display_value") or "")

                draw.text((padding, top), label[:40], fill="#6f6a72", font=font_label)

                bar_x = padding + label_width
                bar_y = top + (row_height - bar_height) / 2
                bar_width = bar_area_width

                draw.rounded_rectangle(
                    (bar_x, bar_y, bar_x + bar_width, bar_y + bar_height),
                    radius=bar_height / 2,
                    fill="#f4e0d8",
                )

                fill_width = max(bar_height / 2, bar_width * (percent / 100))
                draw.rounded_rectangle(
                    (bar_x, bar_y, bar_x + fill_width, bar_y + bar_height),
                    radius=bar_height / 2,
                    fill="#b57464",
                )

                value_x = bar_x + bar_width + (10 * scale)
                draw.text((value_x, top), value, fill="#8c4f42", font=font_value)

            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            return base64.b64encode(buffer.getvalue()).decode("ascii")

        def _render_daily_activity_chart(
            *,
            title: str,
            values: list[int],
            bar_color: str = "#b57464",
            background_color: str = "#fff9f5",
        ) -> str | None:
            """Render vertical daily bars into a compact PNG for PDF embedding."""

            if not values:
                return None

            max_value = max(values)
            if max_value <= 0:
                return None

            scale = 6
            padding = 18 * scale
            bar_width = 6 * scale
            gap = 2 * scale
            min_width = 320 * scale
            height = 220 * scale
            title_height = 22 * scale

            chart_width = len(values) * (bar_width + gap)
            width = max(min_width, padding * 2 + chart_width)

            try:
                font_title = ImageFont.truetype("DejaVuSans.ttf", 16 * scale)
                font_axis = ImageFont.truetype("DejaVuSans.ttf", 12 * scale)
            except Exception:  # pragma: no cover - fallback to default font
                font_title = font_axis = ImageFont.load_default()

            img = Image.new("RGB", (width, height), color=background_color)
            draw = ImageDraw.Draw(img)

            title_y = padding
            draw.text((padding, title_y), title, fill="#8c4f42", font=font_title)

            chart_top = title_y + title_height + (6 * scale)
            chart_bottom = height - padding
            chart_height = max(bar_width, chart_bottom - chart_top)

            for index, value in enumerate(values):
                normalized = value / max_value if max_value else 0
                bar_height = max(bar_width, int(chart_height * normalized))
                left = padding + index * (bar_width + gap)
                right = left + bar_width
                bottom = chart_bottom
                top = bottom - bar_height
                draw.rounded_rectangle((left, top, right, bottom), radius=3 * scale, fill=bar_color)

            draw.line(
                (padding, chart_bottom, width - padding, chart_bottom),
                fill="#e7d7cf",
                width=2 * scale,
            )

            draw.text(
                (padding, chart_top - (10 * scale)),
                "Дни месяца",
                fill="#6f6a72",
                font=font_axis,
            )

            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            return base64.b64encode(buffer.getvalue()).decode("ascii")

        format_chart_items = [
            {
                "label": item.get("label"),
                "percent": item.get("percent") or 0,
                "display_value": f"{item.get('percent') or 0}%",
            }
            for item in format_breakdown
        ]

        genre_chart_items = [
            {
                "label": item.get("label"),
                "percent": item.get("percent") or 0,
                "display_value": f"{item.get('value') or 0} ({item.get('percent') or 0}%)",
            }
            for item in genre_breakdown[:7]
        ]

        chart_images = {
            "formats": _render_chart_image(
                "accounts/charts/bar_chart.html",
                {"title": "Любимые форматы", "items": format_chart_items},
            ),
            "genres": _render_chart_image(
                "accounts/charts/bar_chart.html",
                {"title": "Настроение по жанрам", "items": genre_chart_items},
            ),
            "pages_daily": _render_daily_activity_chart(
                title="Прочитанные страницы по дням",
                values=[entry.get("pages", 0) for entry in daily_summary],
                bar_color="#b57464",
            ),
            "audio_daily": _render_daily_activity_chart(
                title="Аудио ритуалы по дням",
                values=[entry.get("audio_minutes", 0) for entry in daily_summary],
                bar_color="#8262a0",
            ),
        }

        context = {
            "user": user,
            "profile": profile,
            "avatar_url": avatar_url,
            "calendar": calendar_payload,
            "weekday_labels": calendar_payload.get("weekday_labels") or WEEKDAY_LABELS,
            "calendar_year": calendar_year,
            "calendar_month": calendar_month,
            "month_name": month_name or str(calendar_month),
            "month_overview": month_overview,
            "stats": stats,
            "stats_period": stats_period,
            "format_breakdown": format_breakdown,
            "genre_breakdown": genre_breakdown[:7],
            "completed_books": completed_books,
            "daily_summary": daily_summary,
            "top_activity_days": top_activity_days,
            "highlights": highlights,
            "top_authors": top_authors,
            "total_audio_minutes": total_audio_minutes,
            "total_sessions": total_sessions,
            "total_audio_label": total_audio_label,
            "chart_images": chart_images,
        }

        html_string = render_to_string("accounts/monthly_print.html", context)
        html = HTML(
            string=html_string,
            base_url=request.build_absolute_uri("/"),
            encoding="utf-8",
        )
        pdf_file = html.write_pdf()

        response = HttpResponse(pdf_file, content_type="application/pdf")
        filename = f"{slugify(user.username)}-{calendar_year}-{calendar_month}-reading-journal.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error(
            "PDF generation error for monthly report %s-%s: %s",
            year,
            month,
            exc,
        )
        messages.error(request, "Не удалось сгенерировать PDF отчет. Попробуйте позже.")
        return redirect("profile_stats")


def signup(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            backend = (
                settings.AUTHENTICATION_BACKENDS[0]
                if settings.AUTHENTICATION_BACKENDS
                else "django.contrib.auth.backends.ModelBackend"
            )
            login(request, user, backend=backend)
            return redirect("book_list")
    else:
        form = SignUpForm()
    return render(request, "accounts/signup.html", {"form": form})


def _build_premium_overview_context(
    request,
    *,
    profile=None,
    active_subscription=None,
    purchase_form=None,
) -> dict[str, object]:
    profile = profile or request.user.profile
    if active_subscription is None:
        active_subscription = profile.active_premium
    recent_payments = (
        request.user.premium_payments.select_related("subscription").order_by("-created_at")[:10]
    )
    recent_subscriptions = (
        request.user.premium_subscriptions
        .select_related("payment", "granted_by")
        .order_by("-start_at")[:5]
    )
    return {
        "profile": profile,
        "active_subscription": active_subscription,
        "recent_payments": recent_payments,
        "recent_subscriptions": recent_subscriptions,
        "purchase_form": purchase_form or PremiumPurchaseForm(user=request.user),
    }


@login_required
def premium_overview(request):
    profile = request.user.profile
    active_subscription = profile.active_premium

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "disable_auto_renew":
            if profile.premium_auto_renew:
                profile.premium_auto_renew = False
                profile.save(update_fields=["premium_auto_renew"])
                messages.success(
                    request,
                    "Автопродление отключено. При необходимости отмените регулярные списания в YooKassa.",
                )
            else:
                messages.info(request, "Автопродление уже отключено.")
            return redirect("premium_overview")
        if action == "enable_auto_renew":
            if not profile.premium_auto_renew:
                profile.premium_auto_renew = True
                profile.save(update_fields=["premium_auto_renew"])
                messages.success(
                    request,
                    "Автопродление включено. После успешных списаний в YooKassa премиум будет продлеваться автоматически.",
                )
            else:
                messages.info(request, "Автопродление уже включено.")
            return redirect("premium_overview")
    purchase_form = PremiumPurchaseForm(user=request.user)
    context = _build_premium_overview_context(
        request,
        profile=profile,
        active_subscription=active_subscription,
        purchase_form=purchase_form,
    )
    return render(request, "accounts/premium.html", context)


@login_required
@require_POST
def premium_create_payment(request):
    """Упрощенная функция создания платежа"""
    print("🎯 ДЕБАГ: premium_create_payment вызвана")
    
    try:
        profile = request.user.profile
        form = PremiumPurchaseForm(request.POST, user=request.user)

        if not form.is_valid():
            print("❌ ДЕБАГ: Форма невалидна")
            context = _build_premium_overview_context(
                request,
                profile=profile,
                active_subscription=profile.active_premium,
                purchase_form=form,
            )
            return render(request, "accounts/premium.html", context, status=400)

        if not request.user.email:
            messages.error(
                request,
                "Добавьте email в настройках профиля — он нужен для отправки чека от YooKassa.",
            )
            return redirect("premium_overview")

        payment = form.save()
        print(f"✅ ДЕБАГ: Платеж создан в БД, ID: {payment.id}")

        plan = PremiumPayment.get_plan(payment.plan)

        # Создаем платеж в YooKassa
        print("🔍 ДЕБАГ: Пробуем создать платеж в YooKassa...")

        result: YooKassaPaymentResult = yookassa_create_payment(
            amount=payment.amount,
            currency=payment.currency,
            description=f"Подписка Калейдоскоп книг (#{payment.reference})",
            return_url=request.build_absolute_uri(reverse("premium_overview")),
            metadata={"premium_payment_id": payment.id, "plan": payment.plan},
            customer_email=request.user.email,
            receipt_items=[
                {
                    "description": f"{plan.label} — премиум-доступ",  # noqa: ISC003 - hyphen separator
                    "quantity": "1.0",
                    "amount": {
                        "value": f"{payment.amount.quantize(Decimal('0.01'))}",
                        "currency": payment.currency,
                    },
                    "vat_code": 1,
                    "payment_subject": "service",
                    "payment_mode": "full_payment",
                }
            ],
        )

        print(f"✅ ДЕБАГ: YooKassa ответил! ID: {result.payment_id}")

        # Сохраняем результат
        payment.provider_payment_id = result.payment_id
        payment.confirmation_url = result.confirmation_url
        payment.idempotence_key = result.idempotence_key
        payment.provider_payload = result.payload
        payment.save(update_fields=[
            "provider_payment_id",
            "confirmation_url",
            "idempotence_key",
            "provider_payload",
            "updated_at",
        ])

        return redirect(result.confirmation_url)

    except Exception as e:
        print(f"❌ ДЕБАГ: ОШИБКА: {e}")
        messages.error(request, f"Ошибка: {str(e)}")
        return redirect("premium_overview")


def _parse_provider_datetime(value):
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        try:
            return timezone.make_aware(parsed, timezone=timezone.utc)
        except Exception:  # pragma: no cover - fallback
            return timezone.make_aware(parsed)
    return parsed


def _resolve_premium_payment(payment_id, metadata):
    metadata = metadata or {}
    queryset = PremiumPayment.objects.select_related("user")

    if payment_id:
        try:
            return queryset.get(provider_payment_id=payment_id)
        except PremiumPayment.DoesNotExist:
            pass

    payment_pk = metadata.get("premium_payment_id")
    if payment_pk not in (None, ""):
        try:
            return queryset.get(pk=int(payment_pk))
        except (ValueError, PremiumPayment.DoesNotExist):
            pass

    reference = metadata.get("reference")
    if reference:
        try:
            return queryset.get(reference=reference)
        except PremiumPayment.DoesNotExist:
            pass

    return None


def _normalize_metadata_flag(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return None


def _apply_auto_renew_from_metadata(payment, metadata):
    auto_renew_flag = _normalize_metadata_flag(metadata.get("auto_renew"))
    if auto_renew_flag is None:
        return
    try:
        profile = payment.user.profile
    except ObjectDoesNotExist:
        return
    if profile.premium_auto_renew != auto_renew_flag:
        profile.premium_auto_renew = auto_renew_flag
        profile.save(update_fields=["premium_auto_renew"])


@csrf_exempt
@require_POST
def yookassa_webhook(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "invalid_json"}, status=400)

    event = payload.get("event") or ""
    data = payload.get("object") or {}
    payment_id = data.get("id")
    if not payment_id:
        return JsonResponse({"error": "missing_payment_id"}, status=400)

    metadata = data.get("metadata") or {}
    payment = _resolve_premium_payment(payment_id, metadata)
    if payment is None:
        return JsonResponse({"status": "not_found"}, status=404)

    payment.provider_payload = payload
    update_fields = {"provider_payload", "updated_at"}
    if payment.provider_payment_id != payment_id:
        payment.provider_payment_id = payment_id
        update_fields.add("provider_payment_id")

    payment_status = (data.get("status") or "").lower()

    succeeded_event = event == "payment.succeeded" or payment_status == "succeeded"
    cancelled_event = event in {"payment.canceled", "payment.expired"} or payment_status in {
        "canceled",
        "cancelled",
        "expired",
    }

    if succeeded_event:
        paid_at = (
            _parse_provider_datetime(data.get("captured_at"))
            or _parse_provider_datetime(data.get("paid_at"))
            or _parse_provider_datetime(data.get("succeeded_at"))
        )
        if paid_at:
            payment.paid_at = paid_at
            update_fields.add("paid_at")
        payment.status = PremiumPayment.Status.PAID
        update_fields.add("status")
        payment.save(update_fields=list(update_fields))
        _apply_auto_renew_from_metadata(payment, metadata)
    elif cancelled_event:
        cancellation_details = data.get("cancellation_details") or {}
        reason = cancellation_details.get("reason")
        if reason:
            payment.notes = reason
            update_fields.add("notes")
        payment.status = PremiumPayment.Status.CANCELLED
        update_fields.add("status")
        payment.save(update_fields=list(update_fields))
    else:
        payment.save(update_fields=list(update_fields))

    return JsonResponse({"status": "ok"})


@login_required
def profile(request, username=None):
    user_obj = get_object_or_404(
        User.objects.select_related("profile").prefetch_related("groups"),
        username=username or request.user.username
    )
    profile_obj = user_obj.profile
    is_owner = request.user.is_authenticated and request.user == user_obj
    if is_owner:
        ensure_default_shelves(user_obj)
    if profile_obj.is_private and not is_owner:
        return render(
            request,
            "accounts/profile_private.html",
            {"u": user_obj},
        )
    stats_payload = _collect_profile_stats(user_obj, request.GET)
    active_tab = request.GET.get("tab", "overview")
    if active_tab == "shelves":
        active_tab = "overview"
    if active_tab not in {"overview", "stats", "books", "reviews", "activities"}:
        active_tab = "overview"

    shelf_items_prefetch = Prefetch(
        "items",
        queryset=(
            ShelfItem.objects
            .select_related("book", "home_entry")
            .prefetch_related("book__authors")
            .order_by("-added_at")
        ),
    )

    user_shelves = list(
        user_obj.shelves
        .filter(is_managed=False)
        .select_related("user")
        .prefetch_related(shelf_items_prefetch)
        .order_by("-is_default", "name")
    )

    if user_shelves:
        normalized_order = {}
        for label in (READING_PROGRESS_LABEL, DEFAULT_READING_SHELF):
            if label:
                normalized_order[label.lower()] = 0
        if DEFAULT_WANT_SHELF:
            normalized_order[DEFAULT_WANT_SHELF.lower()] = 1
        if DEFAULT_HOME_LIBRARY_SHELF:
            normalized_order[DEFAULT_HOME_LIBRARY_SHELF.lower()] = 2
        if DEFAULT_READ_SHELF:
            normalized_order[DEFAULT_READ_SHELF.lower()] = 3
        if DEFAULT_UNFINISHED_SHELF:
            normalized_order[DEFAULT_UNFINISHED_SHELF.lower()] = 4
        for alias in DEFAULT_READ_SHELF_ALIASES:
            normalized_order.setdefault(alias.lower(), normalized_order.get(DEFAULT_READ_SHELF.lower(), 3))
        indexed_shelves = list(enumerate(user_shelves))
        indexed_shelves.sort(
            key=lambda pair: (
                normalized_order.get(pair[1].name.lower(), len(normalized_order)),
                pair[0],
            )
        )
        user_shelves = [shelf for _, shelf in indexed_shelves]

    if user_shelves:
        book_ids = set()
        home_entries = []
        for shelf in user_shelves:
            for item in shelf.items.all():
                if item.book_id:
                    book_ids.add(item.book_id)
                home_entry = getattr(item, "home_entry", None)
                if home_entry:
                    home_entries.append(home_entry)

        read_dates_map = {}
        if book_ids:
            read_items = (
                ShelfItem.objects
                .filter(
                    shelf__user=user_obj,
                    shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
                    book_id__in=book_ids,
                )
                .values("book_id", "added_at")
            )
            for ri in read_items:
                added_at = ri["added_at"]
                if not added_at:
                    continue
                added_date = (
                    timezone.localtime(added_at).date()
                    if timezone.is_aware(added_at)
                    else added_at.date()
                )
                book_id = ri["book_id"]
                previous = read_dates_map.get(book_id)
                read_dates_map[book_id] = min(previous, added_date) if previous else added_date

        for entry in home_entries:
            shelf_item = getattr(entry, "shelf_item", None)
            book_id = shelf_item.book_id if shelf_item else None
            read_date = entry.read_at or (read_dates_map.get(book_id) if book_id else None)
            entry.date_read = read_date
            entry.is_read = bool(read_date)

    is_author = user_obj.groups.filter(name="author").exists()

    author_books_qs = (
        Book.objects.filter(contributors=user_obj)
        .select_related("primary_isbn")
        .prefetch_related("authors")
        .order_by("-created_at", "title")
    )
    author_books = list(author_books_qs)
    can_manage_author_books = request.user == user_obj and is_author

    user_reviews = (
        Rating.objects.filter(user=user_obj)
        .exclude(review__isnull=True)
        .exclude(review__exact="")
        .select_related("book")
        .prefetch_related("book__authors")
        .order_by("-created_at")
    )

    total_pages_read = (
        ReadingLog.objects.filter(progress__user=user_obj)
        .aggregate(total=Sum("pages_equivalent"))
        .get("total")
        or Decimal("0")
    )

    active_premium = getattr(profile_obj, "active_premium", None)
    premium_payments = (
        user_obj.premium_payments.select_related("subscription").order_by("-created_at")[:5]
        if request.user == user_obj
        else []
    )

    # --- Активности пользователя ---
    journey_assignments = list(
        BookJourneyAssignment.objects.filter(user=user_obj)
        .select_related("book")
        .order_by("stage_number")
    )
    journey_active = next(
        (
            assignment
            for assignment in journey_assignments
            if assignment.status == BookJourneyAssignment.Status.IN_PROGRESS
        ),
        None,
    )
    journey_completed_count = sum(
        1
        for assignment in journey_assignments
        if assignment.status == BookJourneyAssignment.Status.COMPLETED
    )
    journey_active_stage = (
        BookJourneyMap.get_stage_by_number(journey_active.stage_number)
        if journey_active
        else None
    )

    forgotten_entries = list(
        ForgottenBookEntry.objects.filter(user=user_obj)
        .select_related("book")
        .order_by("added_at")
    )
    forgotten_current_selection = (
        ForgottenBooksGame.get_current_selection(user_obj)
        if forgotten_entries
        else None
    )

    book_exchange_challenges = list(
        BookExchangeChallenge.objects.filter(user=user_obj)
        .select_related("shelf", "game")
        .order_by("-started_at")
    )
    book_exchange_active = sum(
        1
        for challenge in book_exchange_challenges
        if challenge.status == BookExchangeChallenge.Status.ACTIVE
    )
    book_exchange_completed = sum(
        1
        for challenge in book_exchange_challenges
        if challenge.status == BookExchangeChallenge.Status.COMPLETED
    )

    game_states = list(
        GameShelfState.objects.filter(user=user_obj)
        .select_related("game", "shelf")
        .order_by("-updated_at")
    )

    nobel_assignments = list(
        NobelLaureateAssignment.objects.filter(user=user_obj)
        .select_related("book")
        .order_by("stage_number")
    )
    nobel_stage_lookup = {
        stage.number: stage for stage in NobelLaureatesChallenge.get_stages()
    }
    nobel_entries = []
    nobel_completed = 0
    nobel_in_progress = 0

    for assignment in nobel_assignments:
        if assignment.status == NobelLaureateAssignment.Status.COMPLETED:
            nobel_completed += 1
        else:
            nobel_in_progress += 1

        stage = nobel_stage_lookup.get(assignment.stage_number)
        nobel_entries.append(
            {
                "stage_number": assignment.stage_number,
                "stage_title": stage.title if stage else "",
                "status": assignment.status,
                "status_label": assignment.get_status_display(),
                "is_completed": assignment.is_completed,
                "completed_at": assignment.completed_at,
                "book_title": assignment.book.title,
                "book_url": reverse("book_detail", args=[assignment.book_id]),
            }
        )

    nobel_total_stages = NobelLaureatesChallenge.get_stage_count()
    nobel_stats = {
        "entries": nobel_entries,
        "completed_count": nobel_completed,
        "in_progress_count": nobel_in_progress,
        "total_stages": nobel_total_stages,
        "extra_count": max(len(nobel_entries) - 3, 0),
        "has_data": bool(nobel_entries),
    }

    def serialize_marathon(marathon, role):
        return {
            "id": marathon.id,
            "title": marathon.title,
            "url": marathon.get_absolute_url(),
            "status": marathon.status,
            "status_label": MARATHON_STATUS_LABELS.get(
                marathon.status, "Активность"
            ),
            "start_date": marathon.start_date,
            "end_date": marathon.end_date,
            "role": role,
        }

    marathons_owned = [
        serialize_marathon(marathon, "creator")
        for marathon in ReadingMarathon.objects.filter(creator=user_obj)
        .order_by("-start_date", "-created_at")
    ]
    marathons_participating = [
        serialize_marathon(marathon, "participant")
        for marathon in ReadingMarathon.objects.filter(
            participants__user=user_obj,
            participants__status=MarathonParticipant.Status.APPROVED,
        )
        .exclude(creator=user_obj)
        .order_by("-start_date", "-created_at")
        .distinct()
    ]
    marathons_pending = [
        serialize_marathon(marathon, "pending")
        for marathon in ReadingMarathon.objects.filter(
            participants__user=user_obj,
            participants__status=MarathonParticipant.Status.PENDING,
        )
        .order_by("-start_date", "-created_at")
        .distinct()
    ]

    def serialize_club(club, role):
        return {
            "id": club.id,
            "title": club.title,
            "url": club.get_absolute_url(),
            "status": club.status,
            "status_label": READING_CLUB_STATUS_LABELS.get(
                club.status, "Активность"
            ),
            "start_date": club.start_date,
            "end_date": club.end_date,
            "role": role,
            "book_title": club.book.title,
            "book_id": club.book_id,
        }

    clubs_owned = [
        serialize_club(club, "creator")
        for club in ReadingClub.objects.filter(creator=user_obj)
        .select_related("book")
        .order_by("-start_date", "-created_at")
    ]
    clubs_participating = [
        serialize_club(club, "participant")
        for club in ReadingClub.objects.filter(
            participants__user=user_obj,
            participants__status=ReadingParticipant.Status.APPROVED,
        )
        .exclude(creator=user_obj)
        .select_related("book")
        .order_by("-start_date", "-created_at")
        .distinct()
    ]
    clubs_pending = [
        serialize_club(club, "pending")
        for club in ReadingClub.objects.filter(
            participants__user=user_obj,
            participants__status=ReadingParticipant.Status.PENDING,
        )
        .select_related("book")
        .order_by("-start_date", "-created_at")
        .distinct()
    ]

    games_has_data = any(
        (
            journey_assignments,
            forgotten_entries,
            book_exchange_challenges,
            game_states,
            nobel_entries,
        )
    )
    marathons_has_data = any(
        (marathons_owned, marathons_participating, marathons_pending)
    )
    clubs_has_data = any((clubs_owned, clubs_participating, clubs_pending))

    profile_activities = {
        "games": {
            "assignments": journey_assignments,
            "active_assignment": journey_active,
            "active_stage": journey_active_stage,
            "completed_count": journey_completed_count,
            "total_stages": BookJourneyMap.get_stage_count(),
            "forgotten": {
                "entries": forgotten_entries,
                "current_selection": forgotten_current_selection,
                "total": len(forgotten_entries),
                "selected": sum(
                    1 for entry in forgotten_entries if entry.selected_month
                ),
                "completed": sum(
                    1 for entry in forgotten_entries if entry.completed_at
                ),
            },
            "book_exchange": {
                "items": book_exchange_challenges,
                "active": book_exchange_active,
                "completed": book_exchange_completed,
                "extra_count": max(len(book_exchange_challenges) - 3, 0),
            },
            "shelf_states": game_states,
            "shelf_states_extra": max(len(game_states) - 4, 0),
            "nobel": nobel_stats,
            "has_data": games_has_data,
        },
        "marathons": {
            "owned": marathons_owned,
            "participating": marathons_participating,
            "pending": marathons_pending,
            "has_data": marathons_has_data,
        },
        "clubs": {
            "owned": clubs_owned,
            "participating": clubs_participating,
            "pending": clubs_pending,
            "has_data": clubs_has_data,
        },
    }
    profile_activities["has_any"] = (
        games_has_data or marathons_has_data or clubs_has_data
    )

    leaderboard_snapshot = _collect_leaderboard_snapshot(user_obj)

    default_read_adj = next(
        (
            alias
            for alias in DEFAULT_READ_SHELF_ALIASES
            if alias
            and alias.strip()
            and alias.strip().lower() != DEFAULT_READ_SHELF.lower()
        ),
        DEFAULT_READ_SHELF,
    )

    shelf_word_forms = {
        "read": {
            "label": DEFAULT_READ_SHELF,
            "adjective": default_read_adj,
        },
        "reading": {
            "label": DEFAULT_READING_SHELF,
            "adjective": READING_PROGRESS_LABEL or DEFAULT_READING_SHELF,
        },
        "want": {
            "label": DEFAULT_WANT_SHELF,
            "adjective": DEFAULT_WANT_SHELF,
        },
        "home": {
            "label": DEFAULT_HOME_LIBRARY_SHELF,
            "adjective": DEFAULT_HOME_LIBRARY_SHELF,
        },
    }

    context = {
        "u": user_obj,
        "profile_obj": profile_obj,
        "is_blogger": user_obj.groups.filter(name="blogger").exists(),
        "is_author": is_author,
        "is_reader": user_obj.groups.filter(name="reader").exists(),
        "stats": stats_payload["stats"],
        "stats_period": stats_payload["stats_period"],
        "active_tab": active_tab,
        "user_shelves": user_shelves,
        "allow_shelf_management": request.user == user_obj,
        "default_reading_shelf_name": DEFAULT_READING_SHELF,
        "default_home_library_shelf_name": DEFAULT_HOME_LIBRARY_SHELF,
        "default_read_shelf_name": DEFAULT_READ_SHELF,
        "default_want_shelf_name": DEFAULT_WANT_SHELF,
        "read_adj": default_read_adj,
        "reading_adj": READING_PROGRESS_LABEL or DEFAULT_READING_SHELF,
        "want_adj": DEFAULT_WANT_SHELF,
        "home_adj": DEFAULT_HOME_LIBRARY_SHELF,
        "shelf_word_forms": shelf_word_forms,
        "reading_progress_label": READING_PROGRESS_LABEL,
        "author_books": author_books,
        "can_manage_author_books": can_manage_author_books,
        "user_reviews": user_reviews,
        "reading_pages_total": total_pages_read,
        "rating_points_total": UserPointEvent.objects.filter(user=user_obj).aggregate(
            total=Sum("points")
        )["total"]
        or 0,
        "active_premium": active_premium,
        "premium_payments": premium_payments,
        "premium_is_self": request.user == user_obj,
        "show_coin_balance": request.user == user_obj,
        "coin_balance": profile_obj.coin_balance,
        "has_unlimited_coins": profile_obj.has_unlimited_coins,
        "profile_activities": profile_activities,
        "leaderboard_snapshot": leaderboard_snapshot,
        "lead_all": leaderboard_snapshot.get("all_time"),
        "lead_al": leaderboard_snapshot.get("all_time"),
    }
    return render(request, "accounts/profile.html", context)


@login_required
def profile_edit(request):
    p = request.user.profile
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=p)
        role_form = RoleForm(request.POST, user=request.user)
        if form.is_valid() and role_form.is_valid():
            form.save()
            role_form.save()
            return redirect("profile", username=request.user.username)
    else:
        form = ProfileForm(instance=p)
        role_form = RoleForm(user=request.user)

    return render(request, "accounts/profile_edit.html", {
        "form": form,
        "role_form": role_form,
    })


@require_GET
def reward_ad_config(request):
    """Expose reward-ad settings for the mobile application."""

    _ensure_mobile_app_request(request)

    placement_id = getattr(settings, "YANDEX_REWARDED_AD_UNIT_ID", "")
    payload = {
        "provider": "yandex",
        "placement_id": placement_id,
        "reward_amount": YANDEX_AD_REWARD_COINS,
        "currency": "coins",
        "enabled": bool(placement_id),
        "requires_authentication": True,
    }
    return JsonResponse(payload)


@csrf_exempt
@login_required
@require_POST
def claim_reward_ad_api(request):
    """Allow authenticated app users to claim a rewarded-ad bonus."""

    _ensure_mobile_app_request(request)

    placement_id = getattr(settings, "YANDEX_REWARDED_AD_UNIT_ID", "")
    if not placement_id:
        return JsonResponse({"error": "reward_unavailable"}, status=503)

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_payload"}, status=400)

    ad_unit_id = (payload.get("ad_unit_id") or "").strip()
    if ad_unit_id and ad_unit_id != placement_id:
        return JsonResponse({"error": "ad_unit_mismatch"}, status=400)

    reward_id = (payload.get("reward_id") or "").strip()
    description = "Вознаграждение от Яндекс за просмотр рекламы через приложение"
    if reward_id:
        description = f"{description} (reward_id={reward_id})"

    profile = request.user.profile
    tx = profile.reward_ad_view(
        YANDEX_AD_REWARD_COINS,
        description=description,
    )

    response_payload = {
        "coins_awarded": YANDEX_AD_REWARD_COINS,
        "transaction_id": tx.pk,
        "balance_after": tx.balance_after,
        "reward_id": reward_id or None,
        "unlimited_balance": profile.has_unlimited_coins,
    }

    status_code = 201
    return JsonResponse(response_payload, status=status_code)