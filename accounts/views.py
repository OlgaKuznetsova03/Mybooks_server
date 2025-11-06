from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import calendar
import json

from django.shortcuts import render, redirect, get_object_or_404

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .models import PremiumPayment
from django.db.models import Count, Sum
from django.http import JsonResponse, Http404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET


from shelves.models import Shelf, ShelfItem, BookProgress, HomeLibraryEntry, ReadingLog
from shelves.services import (
    DEFAULT_HOME_LIBRARY_SHELF,
    DEFAULT_READ_SHELF,
    DEFAULT_READING_SHELF,
    ALL_DEFAULT_READ_SHELF_NAMES,
    READING_PROGRESS_LABEL,
)
from books.models import Rating, Book
from user_ratings.models import UserPointEvent

from .forms import SignUpForm, ProfileForm, RoleForm, PremiumPurchaseForm
from .models import YANDEX_AD_REWARD_COINS

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


WEEKDAY_LABELS = [
    "Пн",
    "Вт",
    "Ср",
    "Чт",
    "Пт",
    "Сб",
    "Вс",
]


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
    selected_year = period_meta.get("selected_year") or today.year
    selected_month = period_meta.get("selected_month") or today.month

    calendar_year = _parse_int(params.get("calendar_year"), selected_year)
    calendar_month = _parse_int(params.get("calendar_month"), selected_month)
    if calendar_month < 1 or calendar_month > 12:
        calendar_month = selected_month

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
            },
        )

    logs = (
        ReadingLog.objects.filter(
            progress__user=user,
            log_date__gte=first_day,
            log_date__lte=last_day,
        )
        .select_related("progress__book")
        .order_by("log_date", "progress__book__title")
    )
    for log in logs:
        book = log.progress.book
        record = ensure_day(log.log_date)
        books_map = record["books"]
        if book.id not in books_map:
            books_map[book.id] = {
                "id": book.id,
                "title": book.title,
                "cover_url": _resolve_cover(book),
            }

    if read_items_qs is not None:
        completed_items = (
            read_items_qs.filter(
                added_at__date__gte=first_day,
                added_at__date__lte=last_day,
            )
            .select_related("book")
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
                }
            record["completed_ids"].add(book.id)

    cal = calendar.Calendar(firstweekday=0)
    weeks = []
    has_activity = False
    for week in cal.monthdatescalendar(calendar_year, calendar_month):
        week_days = []
        for day in week:
            record = day_records.get(day)
            books = []
            is_completion_day = False
            if record and day.month == calendar_month:
                completion_ids = record["completed_ids"]
                books = sorted(
                    (
                        {
                            "id": book_id,
                            "title": info["title"],
                            "cover_url": info["cover_url"],
                            "is_completion": book_id in completion_ids,
                        }
                        for book_id, info in record["books"].items()
                    ),
                    key=lambda entry: entry["title"].lower(),
                )
                is_completion_day = bool(completion_ids)
                has_activity = True
            week_days.append(
                {
                    "date": day,
                    "in_month": day.month == calendar_month,
                    "books": books,
                    "is_completion_day": is_completion_day,
                }
            )
        weeks.append(week_days)

    prev_month_anchor = first_day - timedelta(days=1)
    next_month_anchor = last_day + timedelta(days=1)
    prev_month_start = date(prev_month_anchor.year, prev_month_anchor.month, 1)
    next_month_start = date(next_month_anchor.year, next_month_anchor.month, 1)

    month_name = MONTH_NAMES[calendar_month] if 1 <= calendar_month < len(MONTH_NAMES) else str(calendar_month)

    return {
        "year": calendar_year,
        "month": calendar_month,
        "month_name": month_name,
        "weeks": weeks,
        "weekday_labels": WEEKDAY_LABELS,
        "has_activity": has_activity,
        "prev_url": _build_calendar_url(params, prev_month_start.year, prev_month_start.month),
        "next_url": _build_calendar_url(params, next_month_start.year, next_month_start.month),
    }


def _format_duration(value):
    if not value:
        return None
    total_seconds = int(value.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _resolve_cover(book: Book) -> str:
    return book.get_cover_url()


def _resolve_stats_period(params, read_items):
    today = timezone.localdate()
    period = params.get("period", "week")

    available_years = [d.year for d in read_items.dates("added_at", "year", order="DESC")]
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
        month_dates = read_items.filter(added_at__year=selected_year).dates("added_at", "month", order="DESC")
        available_months = [d.month for d in month_dates]

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

    available_days_all = list(read_items.dates("added_at", "day", order="DESC"))
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

    return {
        "period": period,
        "start": start,
        "end": end,
        "label": label,
        "available_years": available_years,
        "available_months": [(m, MONTH_NAMES[m]) for m in available_months],
        "available_days": available_days_meta,
        "selected_year": selected_year,
        "selected_month": selected_month,
        "selected_day": selected_day if period == "day" else None,
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
    today = timezone.localdate()
    if not read_items.exists():
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

    period_meta = _resolve_stats_period(params, read_items)
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
    total_pages = 0
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
        total_pages += pages

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
    for entry in logs_aggregate:
        medium = entry.get("medium")
        pages_total = entry.get("pages_total") or Decimal("0")
        if not isinstance(pages_total, Decimal):
            pages_total = Decimal(str(pages_total))
        if medium in format_totals:
            format_totals[medium] += pages_total
        if (
            medium == BookProgress.FORMAT_AUDIO
            and entry.get("audio_total")
        ):
            audio_tracked_seconds += int(entry["audio_total"] or 0)

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
        BookProgress.FORMAT_PAPER: "#f59f00",
        BookProgress.FORMAT_EBOOK: "#4c6ef5",
        BookProgress.FORMAT_AUDIO: "#be4bdb",
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
        audio_tracked_display = _format_duration(
            timedelta(seconds=audio_tracked_seconds)
        )

    days_count = max(1, (end - start).days + 1)
    pages_average = None
    if total_pages:
        pages_average = round(total_pages / days_count, 2)

    stats = {
        "books": book_entries,
        "genre_labels": genre_labels,
        "genre_values": genre_values,
        "format_labels": format_labels,
        "format_values": format_values,
        "format_palette": format_palette,
        "pages_total": total_pages,
        "pages_average": pages_average,
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


@login_required
def premium_overview(request):
    profile = request.user.profile
    active_subscription = profile.active_premium
    
    form = PremiumPurchaseForm(user=request.user)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "disable_auto_renew":
            if profile.premium_auto_renew:
                profile.premium_auto_renew = False
                profile.save(update_fields=["premium_auto_renew"])
                messages.success(
                    request,
                    "Автопродление отключено. Вы можете включить его в любой момент на этой странице.",
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
                    "Автопродление включено. Подписка будет продлеваться каждый месяц автоматически.",
                )
            else:
                messages.info(request, "Автопродление уже включено.")
            return redirect("premium_overview")

        form = PremiumPurchaseForm(request.POST, user=request.user)
        if form.is_valid():
            payment = form.save()
            method_label = dict(PremiumPayment.PaymentMethod.choices)[payment.method]
            messages.success(
                request,
                (
                    f"Счёт №{payment.reference} создан. Оплатите {payment.amount} ₽ через «{method_label}» "
                    "и сообщите нам об оплате — премиум активируется сразу после подтверждения."
                ),
            )
            return redirect("premium_overview")

    recent_payments = (
        request.user.premium_payments.select_related("subscription").order_by("-created_at")[:10]
    )
    recent_subscriptions = (
        request.user.premium_subscriptions.select_related("payment", "granted_by").order_by("-start_at")[:5]
    )

    payment_instructions = {
        PremiumPayment.PaymentMethod.YOOMONEY: (
            "Оплатите счёт из приложения или веб-версии ЮMoney. Сохраните чек и отправьте его в поддержку, чтобы мы "
            "активировали подписку."
        ),
    }

    method_labels = dict(PremiumPayment.PaymentMethod.choices)
    payment_instruction_items = [
        {
            "code": code,
            "label": method_labels.get(code, code),
            "text": payment_instructions[code],
        }
        for code, _ in PremiumPayment.PaymentMethod.choices
        if code in payment_instructions
    ]

    context = {
        "profile": profile,
        "active_subscription": active_subscription,
        "premium_form": form,
        "recent_payments": recent_payments,
        "recent_subscriptions": recent_subscriptions,
        "payment_instruction_items": payment_instruction_items,
    }
    return render(request, "accounts/premium.html", context)


@login_required
def profile(request, username=None):
    user_obj = get_object_or_404(
        User.objects.select_related("profile").prefetch_related("groups"),
        username=username or request.user.username
    )
    profile_obj = user_obj.profile
    stats_payload = _collect_profile_stats(user_obj, request.GET)
    active_tab = request.GET.get("tab", "overview")
    if active_tab == "shelves":
        active_tab = "overview"
    if active_tab not in {"overview", "stats", "books", "reviews"}:
        active_tab = "overview"

    user_shelves = (
        user_obj.shelves
        .filter(is_managed=False)
        .select_related("user")
        .prefetch_related("items__book__authors")
        .order_by("-is_default", "name")
    )

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