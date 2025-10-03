from datetime import date, timedelta
import calendar

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .forms import SignUpForm, ProfileForm, RoleForm
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone


from shelves.models import Shelf, BookProgress, HomeLibraryEntry
from shelves.services import DEFAULT_HOME_LIBRARY_SHELF
from books.models import Rating, Book

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
    else:
        end = today
        start = today - timedelta(days=6)
        label = "Последние 7 дней"
        period = "week"

    return {
        "period": period,
        "start": start,
        "end": end,
        "label": label,
        "available_years": available_years,
        "available_months": [(m, MONTH_NAMES[m]) for m in available_months],
        "selected_year": selected_year,
        "selected_month": selected_month,
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

    entries_qs = HomeLibraryEntry.objects.filter(shelf_item__shelf=shelf)
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
            .exclude(custom_genres__name__isnull=True)
            .order_by("-total", "custom_genres__name")[:5]
        )
    ]

    summary["top_locations"] = list(
         active_entries
        .exclude(location="")
        .values("location")
        .annotate(total=Count("id"))
        .order_by("-total", "location")[:5]
    )
    summary["top_statuses"] = list(
        entries_qs
        .exclude(status="")
        .values("status")
        .annotate(total=Count("id"))
        .order_by("-total", "status")[:5]
    )

    return summary


def _collect_profile_stats(user: User, params):
    home_summary = _collect_home_library_summary(user)
    read_shelf = Shelf.objects.filter(user=user, name="Прочитал").first()
    today = timezone.localdate()
    if not read_shelf:
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
        return {
            "stats": {
                "books": [],
                "genre_labels": [],
                "genre_values": [],
                "pages_total": 0,
                "pages_average": None,
                "audio_total_display": None,
                "audio_adjusted_display": None,
                "home_library": home_summary,
            },
            "stats_period": period_meta,
        }

    read_items = read_shelf.items.all()
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
        .exclude(genres__name__isnull=True)
        .order_by("-total")
    )
    genre_labels = [row["genres__name"] for row in genre_stats]
    genre_values = [row["total"] for row in genre_stats]

    audio_total = timedelta()
    audio_adjusted = timedelta()
    for book_id in book_ids:
        progress = progress_map.get(book_id)
        if not progress or not progress.is_audiobook or not progress.audio_length:
            continue
        audio_total += progress.audio_length
        adjusted = progress.get_audio_adjusted_length()
        audio_adjusted += adjusted or progress.audio_length

    days_count = max(1, (end - start).days + 1)
    pages_average = None
    if total_pages:
        pages_average = round(total_pages / days_count, 2)

    stats = {
        "books": book_entries,
        "genre_labels": genre_labels,
        "genre_values": genre_values,
        "pages_total": total_pages,
        "pages_average": pages_average,
        "audio_total_display": _format_duration(audio_total),
        "audio_adjusted_display": _format_duration(audio_adjusted),
        "home_library": home_summary,
    }

    return {
        "stats": stats,
        "stats_period": period_meta,
    }


def signup(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("book_list")
    else:
        form = SignUpForm()
    return render(request, "accounts/signup.html", {"form": form})


@login_required
def profile(request, username=None):
    user_obj = get_object_or_404(
        User.objects.select_related("profile").prefetch_related("groups"),
        username=username or request.user.username
    )
    stats_payload = _collect_profile_stats(user_obj, request.GET)
    active_tab = request.GET.get("tab", "overview")
    if active_tab == "shelves":
        active_tab = "overview"
    if active_tab not in {"overview", "stats", "books", "reviews"}:
        active_tab = "overview"

    user_shelves = (
        user_obj.shelves
        .prefetch_related("items__book__authors")
        .order_by("-is_default", "name")
    )

    user_reviews = (
        Rating.objects.filter(user=user_obj)
        .exclude(review__isnull=True)
        .exclude(review__exact="")
        .select_related("book")
        .prefetch_related("book__authors")
        .order_by("-created_at")
    )

    context = {
        "u": user_obj,
        "is_blogger": user_obj.groups.filter(name="blogger").exists(),
        "is_author":  user_obj.groups.filter(name="author").exists(),
        "is_reader":  user_obj.groups.filter(name="reader").exists(),
        "stats": stats_payload["stats"],
        "stats_period": stats_payload["stats_period"],
        "active_tab": active_tab,
        "user_shelves": user_shelves,
        "allow_shelf_management": request.user == user_obj,
        "user_reviews": user_reviews,
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
