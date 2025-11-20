# shelves/views.py
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from collections import OrderedDict, defaultdict
from datetime import date, timedelta
from typing import Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST
from books.models import Book, Genre, Rating
from books.forms import RatingCommentForm
from .models import (
    Shelf,
    ShelfItem,
    BookProgress,
    CharacterNote,
    Event,
    EventParticipant,
    HomeLibraryEntry,
    ReadingFeedEntry,
    ReadingLog,
    ProgressAnnotation,
)

from .services import (
    move_book_to_read_shelf,
    move_book_to_reading_shelf,
    remove_book_from_want_shelf,
    DEFAULT_WANT_SHELF,
    DEFAULT_READING_SHELF,
    DEFAULT_READ_SHELF,
    ALL_DEFAULT_READ_SHELF_NAMES,
    READING_PROGRESS_LABEL,
    DEFAULT_HOME_LIBRARY_SHELF,
    get_home_library_shelf,
)
from .forms import (
    ShelfCreateForm,
    AddToShelfForm,
    AddToEventForm,
    BookProgressNotesForm,
    CharacterNoteForm,
    BookProgressFormatForm,
    ReadingFeedCommentForm,
    ProgressQuoteForm,
    ProgressNoteEntryForm,
    HomeLibraryEntryForm,
    HomeLibraryFilterForm,
)
from games.services.read_before_buy import ReadBeforeBuyGame
from user_ratings.models import LeaderboardPeriod, UserPointEvent
from user_ratings.services import BOOK_COMPLETION, award_for_book_completion


def event_list(request):
    events = Event.objects.all()
    return render(request, "shelves/event_list.html", {"events": events})

def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)
    return render(request, "shelves/event_detail.html", {"event": event})

def event_join(request, pk):
    event = get_object_or_404(Event, pk=pk)
    event.participants.add(request.user)
    return redirect("shelves:event_detail", pk=pk)

def event_leave(request, pk):
    event = get_object_or_404(Event, pk=pk)
    event.participants.remove(request.user)
    return redirect("shelves:event_detail", pk=pk)


# ---------- ПОЛКИ ----------

@login_required
def my_shelves(request):
    """Список полок текущего пользователя с книгами."""
    shelves = (
        Shelf.objects
        .filter(user=request.user, is_managed=False)
        .select_related("user")
        .prefetch_related("items__book")
        .order_by("-is_default", "name")
    )
    return render(
        request,
        "shelves/my_shelves.html",
        {
            "shelves": shelves,
            "default_reading_shelf_name": DEFAULT_READING_SHELF,
            "default_home_library_shelf_name": DEFAULT_HOME_LIBRARY_SHELF,
            "default_read_shelf_name": DEFAULT_READ_SHELF,
            "reading_progress_label": READING_PROGRESS_LABEL,
        },
    )


@login_required
@login_required
def home_library(request):
    """Подробный учёт книг из полки «Моя домашняя библиотека» пользователя."""

    shelf = get_home_library_shelf(request.user)
    items = list(
        shelf.items
        .select_related("book")
        .prefetch_related("book__authors", "book__genres")
        .order_by("book__title")
    )
    item_ids = [item.id for item in items]
    entry_map = {
        entry.shelf_item_id: entry
        for entry in (
            HomeLibraryEntry.objects
            .filter(shelf_item_id__in=item_ids)
            .select_related("shelf_item__book")
            .prefetch_related("custom_genres")
        )
    }
    entries = []
    for item in items:
        entry = entry_map.get(item.id)
        book_genres = list(item.book.genres.all())
        if entry is None:
            entry = HomeLibraryEntry.objects.create(
                shelf_item=item,
                series_name=item.book.series or "",
            )
            if book_genres:
                entry.custom_genres.set(book_genres)
        else:
            if not entry.series_name and item.book.series:
                entry.series_name = item.book.series
                entry.save(update_fields=["series_name"])
            existing_custom_genres = list(entry.custom_genres.all())
            if not existing_custom_genres and book_genres:
                entry.custom_genres.set(book_genres)
        entry_map[item.id] = entry

    entries_qs = (
        HomeLibraryEntry.objects
        .filter(shelf_item__shelf=shelf)
        .order_by()
        .select_related("shelf_item__book")
        .prefetch_related("shelf_item__book__authors", "custom_genres")
    )

    active_entries_qs = entries_qs.filter(is_disposed=False)
    disposed_entries_qs = entries_qs.filter(is_disposed=True)

    location_counts = list(
        active_entries_qs
        .exclude(location="")
        .values("location")
        .annotate(total=Count("id"))
        .values("location", "total")
        .order_by("-total", "location")[:5]
    )
    status_counts = list(
        entries_qs
        .exclude(status="")
        .values("status")
        .annotate(total=Count("id"))
        .values("status", "total")
        .order_by("-total", "status")[:5]
    )

    total_active = active_entries_qs.count()
    disposed_total = disposed_entries_qs.count()
    classic_count = active_entries_qs.filter(is_classic=True).count()

    series_counts = list(
        active_entries_qs
        .exclude(series_name="")
        .values("series_name")
        .annotate(total=Count("id"))
        .values("series_name", "total")
        .order_by("-total", "series_name")[:5]
    )
    genre_counts = [
        {
            "name": row["custom_genres__name"],
            "total": row["total"],
        }
        for row in (
            active_entries_qs
            .values("custom_genres__name")
            .annotate(total=Count("custom_genres"))
            .values("custom_genres__name", "total")
            .exclude(custom_genres__name__isnull=True)
            .order_by("-total", "custom_genres__name")[:5]
        )
    ]

    active_entries_list = list(active_entries_qs)
    disposed_entries_list = list(disposed_entries_qs)
    all_entries_list = [*active_entries_list, *disposed_entries_list]

    def _sort_key(entry: HomeLibraryEntry):
        acquired = entry.acquired_at or date.min
        added = entry.shelf_item.added_at.date() if entry.shelf_item.added_at else date.min
        return (acquired, added, entry.shelf_item_id)

    recent_entries = sorted(active_entries_list, key=_sort_key, reverse=True)[:5]

    series_values = list(
        active_entries_qs
        .exclude(series_name="")
        .values_list("series_name", flat=True)
        .distinct()
    )
    series_total = len(series_values)
    genre_queryset = (
        Genre.objects
        .filter(home_library_entries__shelf_item__shelf=shelf, home_library_entries__is_disposed=False)
        .distinct()
        .order_by("name")
    )
    genre_total = genre_queryset.count()
    filter_form = HomeLibraryFilterForm(
        request.GET or None,
        series_choices=series_values,
        genre_queryset=genre_queryset,
    )

    filtered_entries_qs = active_entries_qs
    filters_applied = False
    if filter_form.is_valid():
        is_classic = filter_form.cleaned_data.get("is_classic")
        series = filter_form.cleaned_data.get("series")
        genres = filter_form.cleaned_data.get("genres")

        if is_classic == "true":
            filtered_entries_qs = filtered_entries_qs.filter(is_classic=True)
            filters_applied = True
        elif is_classic == "false":
            filtered_entries_qs = filtered_entries_qs.filter(is_classic=False)
            filters_applied = True

        if series:
            filtered_entries_qs = filtered_entries_qs.filter(series_name=series)
            filters_applied = True

        if genres:
            filtered_entries_qs = filtered_entries_qs.filter(custom_genres__in=genres).distinct()
            filters_applied = True

    # === ДОБАВЛЕНО: карта дат прочтения из полки «Прочитано» ===
    read_dates_map = {}
    try:
        filtered_book_ids = list(
            entries_qs.values_list("shelf_item__book_id", flat=True).distinct()
        )
        if filtered_book_ids:
            read_items = (
                ShelfItem.objects
                .filter(
                    shelf__user=request.user,
                    shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
                    book_id__in=filtered_book_ids,
                )
                .values("book_id", "added_at")
            )
            for ri in read_items:
                added_at = ri["added_at"]
                if added_at is None:
                    continue
                # приводим к локальной дате при необходимости
                added_date = timezone.localtime(added_at).date() if timezone.is_aware(added_at) else added_at.date()
                book_id = ri["book_id"]
                prev = read_dates_map.get(book_id)
                # если книга добавлялась несколько раз в «Прочитано», берём самую раннюю дату завершения
                read_dates_map[book_id] = min(prev, added_date) if prev else added_date
    except Exception:
        # на случай редких ошибок — просто не показываем дату
        read_dates_map = {}

    def _apply_read_metadata(entry: HomeLibraryEntry) -> bool:
        """Annotate entry with derived read flags and return read status."""

        if not entry:
            return False

        book_id = entry.shelf_item.book_id if entry.shelf_item else None
        read_date = entry.read_at or (read_dates_map.get(book_id) if book_id else None)
        entry.date_read = read_date
        entry.is_read = bool(read_date)
        return entry.is_read

    read_count = sum(1 for entry in active_entries_list if _apply_read_metadata(entry))
    for entry in disposed_entries_list:
        _apply_read_metadata(entry)

    # Итоговые списки
    entries = list(
        filtered_entries_qs
        .order_by("shelf_item__book__title", "shelf_item__id")
    )
    disposed_entries = list(
        disposed_entries_qs
        .order_by("shelf_item__book__title", "shelf_item__id")
    )

    # === ДОБАВЛЕНО: прокидываем виртуальное поле date_read в объекты для шаблона ===
    for entry in entries:
        if not hasattr(entry, "date_read"):
            _apply_read_metadata(entry)

    for entry in disposed_entries:
        if not hasattr(entry, "date_read"):
            _apply_read_metadata(entry)

    def _entry_book_data(entry: HomeLibraryEntry):
        if not entry.shelf_item or not entry.shelf_item.book:
            return None
        book = entry.shelf_item.book
        authors = ", ".join(author.name for author in book.authors.all())
        return {
            "id": book.pk,
            "title": book.title,
            "authors": authors or "Автор неизвестен",
            "url": reverse("book_detail", args=[book.pk]),
        }

    def _prepare_books(items):
        unique = OrderedDict()
        for book in items:
            if not book:
                continue
            unique[book["id"]] = book
        return sorted(unique.values(), key=lambda b: (b.get("title") or "").lower())

    classic_books = _prepare_books([
        _entry_book_data(entry)
        for entry in active_entries_list
        if entry.is_classic
    ])

    modern_books = _prepare_books([
        _entry_book_data(entry)
        for entry in active_entries_list
        if not entry.is_classic
    ])

    series_books_map = {}
    for series in series_counts:
        name = series["series_name"]
        series_books_map[name] = _prepare_books([
            _entry_book_data(entry)
            for entry in active_entries_list
            if entry.series_name == name
        ])

    genre_books_map = {}
    for genre in genre_counts:
        genre_name = genre["name"]
        genre_books_map[genre_name] = _prepare_books([
            _entry_book_data(entry)
            for entry in active_entries_list
            if any(g.name == genre_name for g in entry.custom_genres.all())
        ])

    active_books = _prepare_books([
        _entry_book_data(entry)
        for entry in active_entries_list
    ])

    disposed_books = _prepare_books([
        _entry_book_data(entry)
        for entry in disposed_entries_list
    ])

    status_buckets = defaultdict(list)
    for entry in all_entries_list:
        status_name = (entry.status or "").strip()
        if not status_name:
            continue
        book_data = _entry_book_data(entry)
        if book_data:
            status_buckets[status_name].append(book_data)
    status_books_map = {
        name: _prepare_books(items)
        for name, items in status_buckets.items()
    }

    location_buckets = defaultdict(list)
    for entry in active_entries_list:
        location_name = (entry.location or "").strip()
        if not location_name:
            continue
        book_data = _entry_book_data(entry)
        if book_data:
            location_buckets[location_name].append(book_data)
    location_books_map = {
        name: _prepare_books(items)
        for name, items in location_buckets.items()
    }

    def _period_bucket():
        return {
            "bought_count": 0,
            "read_count": 0,
            "bought_books": [],
            "read_books": [],
        }

    year_period_data = defaultdict(_period_bucket)
    month_period_data = defaultdict(_period_bucket)

    for entry in all_entries_list:
        book_data = _entry_book_data(entry)
        if not book_data:
            continue

        if entry.acquired_at:
            acquired = entry.acquired_at
            year_key = str(acquired.year)
            month_key = f"{acquired.year:04d}-{acquired.month:02d}"
            year_bucket = year_period_data[year_key]
            month_bucket = month_period_data[month_key]
            year_bucket["bought_count"] += 1
            month_bucket["bought_count"] += 1
            year_bucket["bought_books"].append(book_data)
            month_bucket["bought_books"].append(book_data)

        book_id = entry.shelf_item.book_id if entry.shelf_item else None
        read_date = entry.read_at or (read_dates_map.get(book_id) if book_id else None)
        if read_date:
            year_key = str(read_date.year)
            month_key = f"{read_date.year:04d}-{read_date.month:02d}"
            year_bucket = year_period_data[year_key]
            month_bucket = month_period_data[month_key]
            year_bucket["read_count"] += 1
            month_bucket["read_count"] += 1
            year_bucket["read_books"].append(book_data)
            month_bucket["read_books"].append(book_data)

    def _finalise_periods(source):
        final = {}
        for key, bucket in source.items():
            final[key] = {
                "bought_count": bucket["bought_count"],
                "read_count": bucket["read_count"],
                "bought_books": _prepare_books(bucket["bought_books"]),
                "read_books": _prepare_books(bucket["read_books"]),
            }
        return final

    year_periods = _finalise_periods(year_period_data)
    month_periods = _finalise_periods(month_period_data)

    MONTH_NAMES_RU = [
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

    def _month_label(key: str) -> str:
        try:
            year_str, month_str = key.split("-")
            month_index = int(month_str) - 1
        except (ValueError, TypeError):
            return key
        month_name = MONTH_NAMES_RU[month_index] if 0 <= month_index < 12 else month_str
        return f"{month_name} {year_str}"

    year_options = sorted(year_periods.keys(), reverse=True)
    month_options = sorted(month_periods.keys(), reverse=True)

    period_options = {
        "year": [
            {"value": value, "label": value}
            for value in year_options
        ],
        "month": [
            {"value": value, "label": _month_label(value)}
            for value in month_options
        ],
    }

    default_period_type = "year" if year_options else "month"
    default_period_value = ""
    if default_period_type == "year" and year_options:
        default_period_value = year_options[0]
    elif default_period_type == "month" and month_options:
        default_period_value = month_options[0]

    if default_period_type == "year":
        default_period_stats = year_periods.get(default_period_value)
    else:
        default_period_stats = month_periods.get(default_period_value)
    if not default_period_stats:
        default_period_stats = _period_bucket()

    summary_data = {
        "active": active_books,
        "disposed": disposed_books,
        "classic": classic_books,
        "modern": modern_books,
        "series": series_books_map,
        "genres": genre_books_map,
        "statuses": status_books_map,
        "locations": location_books_map,
        "periods": {
            "year": year_periods,
            "month": month_periods,
        },
        "periodOptions": period_options,
        "defaultPeriod": {
            "type": default_period_type,
            "value": default_period_value,
        },
    }

    summary = {
        "total": total_active,
        "disposed_total": disposed_total,
        "classic_count": classic_count,
        "modern_count": total_active - classic_count,
        "read_count": read_count,
        "series_counts": series_counts,
        "genre_counts": genre_counts,
        "series_total": series_total,
        "genre_total": genre_total,
        "locations": location_counts,
        "statuses": status_counts,
        "recent_entries": recent_entries,
    }

    context = {
        "shelf": shelf,
        "entries": entries,
        "disposed_entries": disposed_entries,
        "summary": summary,
        "summary_data": summary_data,
        "filter_form": filter_form,
        "filters_applied": filters_applied,
        "default_reading_shelf_name": DEFAULT_READING_SHELF,
        "default_read_shelf_name": DEFAULT_READ_SHELF,
        "default_period_type": default_period_type,
        "default_period_value": default_period_value,
        "default_period_stats": default_period_stats,
        "period_options": period_options,
        "initial_period_options": period_options.get(default_period_type, []),
    }
    return render(request, "shelves/home_library.html", context)



@login_required
def home_library_edit(request, item_id):
    """Редактирование сведений о конкретном экземпляре книги."""

    shelf = get_home_library_shelf(request.user)
    item = get_object_or_404(
        ShelfItem.objects.select_related("book", "shelf"),
        pk=item_id,
        shelf=shelf,
    )
    entry, _ = HomeLibraryEntry.objects.get_or_create(shelf_item=item)

    if request.method == "POST":
        form = HomeLibraryEntryForm(request.POST, instance=entry)
        if form.is_valid():
            form.save()
            messages.success(request, "Данные обновлены.")
            next_url = request.POST.get("next") or reverse("shelves:home_library")
            return redirect(next_url)
    else:
        form = HomeLibraryEntryForm(instance=entry)

    next_url = request.GET.get("next") or reverse("shelves:home_library")
    return render(
        request,
        "shelves/home_library_edit.html",
        {
            "form": form,
            "item": item,
            "entry": entry,
            "next_url": next_url,
        },
    )

@login_required
def shelf_create(request):
    """Создание пользовательской полки."""
    if request.method == "POST":
        form = ShelfCreateForm(request.POST)
        if form.is_valid():
            shelf = form.save(commit=False)
            shelf.user = request.user
            if Shelf.objects.filter(user=request.user, name=shelf.name).exists():
                form.add_error("name", "У вас уже есть полка с таким названием.")
            else:
                shelf.save()
                messages.success(request, "Полка создана.")
                return redirect("my_shelves")
    else:
        form = ShelfCreateForm()
    return render(request, "shelves/shelf_create.html", {"form": form})


@login_required
def add_book_to_shelf(request, book_id):
    """Добавить книгу в выбранную полку пользователя (форма-страница)."""
    book = get_object_or_404(Book, pk=book_id)
    if request.method == "POST":
        form = AddToShelfForm(request.POST, user=request.user)
        if form.is_valid():
            shelf = form.cleaned_data["shelf"]
            if shelf.user_id != request.user.id:
                messages.error(request, "Нельзя добавлять книги в чужую полку.")
                return redirect("book_detail", pk=book.pk)
            if getattr(shelf, "is_managed", False):
                messages.error(
                    request,
                    "Книги на эту полку можно добавлять только в рамках игровой механики.",
                )
                return redirect("book_detail", pk=book.pk)
            if shelf.name == DEFAULT_READ_SHELF:
                move_book_to_read_shelf(request.user, book)
                messages.success(request, f"«{book.title}» добавлена в «{shelf.name}».")
                return redirect("book_detail", pk=book.pk)

            if ReadBeforeBuyGame.is_game_shelf(shelf):
                success, message_text, level = ReadBeforeBuyGame.add_book_to_shelf(
                    request.user, shelf, book
                )
                message_handler = getattr(messages, level, messages.info)
                message_handler(request, message_text)
                if success and shelf.name == DEFAULT_READING_SHELF:
                    remove_book_from_want_shelf(request.user, book)
                return redirect("book_detail", pk=book.pk)

            ShelfItem.objects.get_or_create(shelf=shelf, book=book)
            if shelf.name == DEFAULT_READING_SHELF:
                remove_book_from_want_shelf(request.user, book)
            messages.success(request, f"«{book.title}» добавлена в «{shelf.name}».")
            return redirect("book_detail", pk=book.pk)
    else:
        form = AddToShelfForm(user=request.user)
    return render(request, "shelves/add_to_shelf.html", {"form": form, "book": book})


@login_required
def remove_book_from_shelf(request, shelf_id, book_id):
    """Удалить книгу из указанной полки текущего пользователя."""
    shelf = get_object_or_404(Shelf, pk=shelf_id, user=request.user)
    item = ShelfItem.objects.filter(shelf=shelf, book_id=book_id).first()
    if item:
        item.delete()
        messages.info(request, "Книга удалена с полки.")
    next_url = request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    if request.user.is_authenticated:
        return redirect("profile", username=request.user.username)
    return redirect("my_shelves")


# Быстрое добавление в дефолтные полки
DEFAULT_SHELF_MAP = {
    "want": DEFAULT_WANT_SHELF,
    "reading": DEFAULT_READING_SHELF,
    "read": DEFAULT_READ_SHELF,
}

@login_required
@require_POST
def quick_add_default_shelf(request, book_id, code):
    """Быстрое добавление в одну из трёх стандартных полок."""
    book = get_object_or_404(Book, pk=book_id)
    next_url = request.POST.get("next")
    if code not in DEFAULT_SHELF_MAP:
        messages.error(request, "Неизвестная полка.")
        return redirect("book_detail", pk=book.pk)
    shelf_name = DEFAULT_SHELF_MAP[code]
    shelf, _ = Shelf.objects.get_or_create(
        user=request.user,
        name=shelf_name,
        defaults={"is_default": True, "is_public": True},
    )

    def _redirect_default():
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("book_detail", pk=book.pk)
    
    if getattr(shelf, "is_managed", False):
        messages.error(
            request,
            "Книги на эту полку можно добавлять только в рамках игровой механики.",
        )
        return _redirect_default()
    if code == "read":
        move_book_to_read_shelf(request.user, book)
        messages.success(request, f"«{book.title}» добавлена в «{shelf.name}».")
        return _redirect_default()

    if ReadBeforeBuyGame.is_game_shelf(shelf):
        success, message_text, level = ReadBeforeBuyGame.add_book_to_shelf(
            request.user, shelf, book
        )
        message_handler = getattr(messages, level, messages.info)
        message_handler(request, message_text)
        if success and code == "reading":
            remove_book_from_want_shelf(request.user, book)
            messages.info(
                request,
                "Уточните формат чтения и данные книги на странице прогресса.",
            )
            return redirect("shelves:reading_track", book_id=book.pk)
        return _redirect_default()

    ShelfItem.objects.get_or_create(shelf=shelf, book=book)
    if code == "reading":
        remove_book_from_want_shelf(request.user, book)
        messages.success(request, f"«{book.title}» добавлена в «{shelf.name}».")
        messages.info(
            request,
            "Уточните формат чтения и данные книги на странице прогресса.",
        )
        return redirect("shelves:reading_track", book_id=book.pk)
    messages.success(request, f"«{book.title}» добавлена в «{shelf.name}».")
    return _redirect_default()


@login_required
@require_POST
def move_book_to_reading(request, book_id):
    """Переместить книгу в стандартную полку «Читаю» текущего пользователя."""

    book = get_object_or_404(Book, pk=book_id)
    next_url = request.POST.get("next")

    move_book_to_reading_shelf(request.user, book)
    messages.success(
        request,
        f"«{book.title}» теперь на полке «{DEFAULT_READING_SHELF}».",
    )

    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)

    messages.info(
        request,
        "Уточните формат чтения и данные книги на странице прогресса.",
    )
    return redirect("shelves:reading_track", book_id=book.pk)


@login_required
def add_book_to_event(request, book_id):
    """
    Добавить книгу в выбранный марафон/событие (требуется участие пользователя).
    После добавления редиректим в трекер чтения этой книги.
    """
    book = get_object_or_404(Book, pk=book_id)
    if request.method == "POST":
        form = AddToEventForm(request.POST, user=request.user)
        if form.is_valid():
            event = form.cleaned_data["event"]
            if not EventParticipant.objects.filter(event=event, user=request.user).exists():
                messages.error(request, "Вы не участвуете в этом событии.")
                return redirect("book_detail", pk=book.pk)

            bp, created = BookProgress.objects.get_or_create(
                event=event, user=request.user, book=book, defaults={"percent": 0}
            )
            if created:
                messages.success(request, f"Книга «{book.title}» добавлена в событие «{event.title}».")
            else:
                messages.info(request, f"Книга уже есть в событии «{event.title}».")
            return redirect("shelves:reading_track", book_id=book.pk)
    else:
        form = AddToEventForm(user=request.user)

    return render(request, "shelves/add_to_event.html", {"form": form, "book": book})


# ---------- ЧТЕНИЕ / ПРОГРЕСС ----------

@login_required
def reading_now(request):
    """Страница «Читаю сейчас»: берём книги из полки 'Читаю'."""
    shelf = Shelf.objects.filter(user=request.user, name="Читаю").first()
    if not shelf:
        items = []
    else:
        items = list(
            ShelfItem.objects.filter(shelf=shelf)
            .select_related("book")
            .prefetch_related("book__authors")
        )

        book_ids = [item.book_id for item in items]
        if book_ids:
            progress_map = {
                progress.book_id: progress
                for progress in BookProgress.objects.filter(
                    user=request.user,
                    event__isnull=True,
                    book_id__in=book_ids,
                )
            }
        else:
            progress_map = {}

        for item in items:
            progress = progress_map.get(item.book_id)
            item.progress = None
            item.progress_percent = None
            item.progress_label = None
            item.progress_total_pages = None
            item.progress_current_page = None
            item.progress_updated_at = None

            if not progress:
                continue

            item.progress = progress
            item.progress_percent = float(progress.percent or Decimal("0"))
            item.progress_label = progress.get_format_display()
            item.progress_total_pages = progress.get_effective_total_pages()
            item.progress_current_page = progress.current_page
            item.progress_updated_at = progress.updated_at

    return render(
        request,
        "reading/reading_now.html",
        {"shelf": shelf, "items": items},
    )


def _format_duration(duration):
    if not duration:
        return None
    total_seconds = int(duration.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _build_reading_track_context(
    progress,
    book,
    *,
    character_form=None,
    format_form=None,
    character_forms=None,
    quote_form=None,
    note_entry_form=None,
    quote_forms=None,
    note_forms=None,
):
    total_pages = progress.get_effective_total_pages()
    combined_pages = progress.get_combined_current_pages()
    calculated_percent = float(progress.percent or Decimal("0"))
    media_objects = list(progress.media.all())
    if not media_objects:
        media_objects = progress._iter_active_media()  # fallback for старых записей

    media_details = []
    choices = dict(BookProgress.FORMAT_CHOICES)
    for medium in media_objects:
        detail = {
            "code": medium.medium,
            "label": choices.get(medium.medium, medium.medium),
            "current_page": None,
            "audio_position": None,
            "audio_length": None,
            "audio_speed": None,
            "equivalent_pages": None,
            "total_pages": medium.total_pages_override or total_pages,
        }
        if total_pages:
            equivalent = progress._medium_equivalent_pages(medium, total_pages)
            if equivalent is not None:
                detail["equivalent_pages"] = equivalent
        if medium.medium == BookProgress.FORMAT_AUDIO:
            position = medium.audio_position or progress.audio_position
            length = medium.audio_length or progress.audio_length
            speed = medium.playback_speed or progress.audio_playback_speed
            detail["audio_position"] = _format_duration(position)
            detail["audio_length"] = _format_duration(length)
            detail["audio_speed"] = speed
        else:
            detail["current_page"] = medium.current_page
        media_details.append(detail)

    daily_logs = progress.logs.order_by("-log_date", "-medium")
    audio_logs = daily_logs.filter(medium=BookProgress.FORMAT_AUDIO)
    notes_form = BookProgressNotesForm(instance=progress)
    chart_logs = progress.logs.order_by("log_date")
    tracked_mediums = [
        BookProgress.FORMAT_PAPER,
        BookProgress.FORMAT_EBOOK,
    ]
    aggregated = OrderedDict()
    for log in chart_logs:
        if log.medium not in tracked_mediums:
            continue
        entry = aggregated.setdefault(
            log.log_date,
            {
                "total": Decimal("0"),
                "mediums": {code: Decimal("0") for code in tracked_mediums},
            },
        )
        pages_value = log.pages_equivalent or Decimal("0")
        entry["total"] += pages_value
        entry["mediums"][log.medium] += pages_value
    chart_labels = [date.strftime("%d.%m.%Y") for date in aggregated.keys()]
    chart_pages = [float(data["total"]) for data in aggregated.values()]
    chart_medium_pages = {
        code: [float(data["mediums"][code]) for data in aggregated.values()]
        for code in tracked_mediums
    }
    format_totals = {
        code: Decimal("0")
        for code, _ in BookProgress.FORMAT_CHOICES
    }
    for entry in (
        progress.logs
        .order_by()
        .values("medium")
        .annotate(total_pages=Sum("pages_equivalent"))
        .values("medium", "total_pages")
    ):
        medium_code = entry.get("medium")
        if medium_code not in format_totals:
            continue
        total_value = entry.get("total_pages") or Decimal("0")
        if not isinstance(total_value, Decimal):
            total_value = Decimal(str(total_value))
        format_totals[medium_code] += total_value
    total_equivalent = sum(format_totals.values(), Decimal("0"))
    format_palette_map = {
        BookProgress.FORMAT_PAPER: "#f59f00",
        BookProgress.FORMAT_EBOOK: "#4c6ef5",
        BookProgress.FORMAT_AUDIO: "#be4bdb",
    }
    format_chart_labels = []
    format_chart_values = []
    format_chart_palette = []
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
            format_chart_labels.append(choices.get(medium_code, medium_code))
            format_chart_values.append(float(percent))
            format_chart_palette.append(
                format_palette_map.get(medium_code, "#4dabf7")
            )
    max_pages_for_chart = max(chart_pages) if chart_pages else 0
    if max_pages_for_chart:
        max_chart_height = 160  # px
        min_scale = 1.0
        max_scale = 4.0
        calculated_scale = max_chart_height / max_pages_for_chart
        chart_scale = max(min_scale, min(max_scale, calculated_scale))
    else:
        chart_scale = 1.5
    average_pages_per_day = progress.average_pages_per_day
    estimated_days_remaining = progress.estimated_days_remaining
    character_form = character_form or CharacterNoteForm()
    format_form = format_form or BookProgressFormatForm(instance=progress, book=book)
    characters = list(progress.character_entries.all())
    character_forms = character_forms or {}
    character_edit_forms = {
        character.pk: character_forms.get(character.pk)
        or CharacterNoteForm(instance=character, prefix=f"character-{character.pk}")
        for character in characters
    }
    character_rows = [
        (character, character_edit_forms[character.pk])
        for character in characters
    ]

    quote_form = quote_form or ProgressQuoteForm()
    note_entry_form = note_entry_form or ProgressNoteEntryForm()
    quote_forms = quote_forms or {}
    note_forms = note_forms or {}
    quote_entries = list(
        progress.annotations.filter(kind=ProgressAnnotation.KIND_QUOTE)
    )
    note_entries = list(
        progress.annotations.filter(kind=ProgressAnnotation.KIND_NOTE)
    )
    quote_edit_forms = {
        entry.pk: quote_forms.get(entry.pk)
        or ProgressQuoteForm(instance=entry, prefix=f"quote-{entry.pk}")
        for entry in quote_entries
    }
    quote_rows = [
        (entry, quote_edit_forms[entry.pk])
        for entry in quote_entries
    ]
    note_edit_forms = {
        entry.pk: note_forms.get(entry.pk)
        or ProgressNoteEntryForm(instance=entry, prefix=f"note-{entry.pk}")
        for entry in note_entries
    }
    note_rows = [
        (entry, note_edit_forms[entry.pk])
        for entry in note_entries
    ]
    finish_celebration_api_url = None
    if progress.percent and progress.percent >= Decimal("100"):
        finish_celebration_api_url = reverse(
            "shelves:reading_finish_celebration_api", args=[progress.pk]
        )
    return {
        "book": book,
        "progress": progress,
        "total_pages": total_pages,
        "calculated_percent": calculated_percent,
        "daily_logs": daily_logs,
        "notes_form": notes_form,
        "character_form": character_form,
        "characters": characters,
        "character_edit_forms": character_edit_forms,
        "character_rows": character_rows,
        "average_pages_per_day": average_pages_per_day,
        "estimated_days_remaining": estimated_days_remaining,
        "chart_labels": chart_labels,
        "chart_pages": chart_pages,
        "chart_mediums": [
            {"code": code, "label": choices.get(code, code)}
            for code in tracked_mediums
        ],
        "chart_medium_pages": chart_medium_pages,
        "format_chart_labels": format_chart_labels,
        "format_chart_values": format_chart_values,
        "format_chart_palette": format_chart_palette,
        "chart_scale": chart_scale,
        "format_form": format_form,
        "media_details": media_details,
        "combined_pages": combined_pages,
        "audio_logs": audio_logs,
        "quote_form": quote_form,
        "quote_entries": quote_entries,
        "quote_edit_forms": quote_edit_forms,
        "quote_rows": quote_rows,
        "note_entry_form": note_entry_form,
        "note_entries": note_entries,
        "note_edit_forms": note_edit_forms,
        "note_rows": note_rows,
        "finish_celebration_api_url": finish_celebration_api_url,
        "finish_reward_points": BOOK_COMPLETION.points,
    }

def reading_track(request, book_id):
    """
    Трекер чтения одной книги (личный прогресс без привязки к событию).
    ETA/таймер не используем — только ручное обновление и быстрые кнопки.
    """
    book = get_object_or_404(Book, pk=book_id)
    progress, _ = BookProgress.objects.get_or_create(
        event=None, user=request.user, book=book,
        defaults={"percent": 0, "current_page": 0}
    )
    format_form = BookProgressFormatForm(instance=progress, book=book)
    context = _build_reading_track_context(progress, book, format_form=format_form)
    return render(request, "reading/track.html", context)


@login_required
@require_POST
def reading_add_character(request, progress_id):
    progress = get_object_or_404(BookProgress, pk=progress_id, user=request.user)
    form = CharacterNoteForm(request.POST)
    if form.is_valid():
        character = form.save(commit=False)
        character.progress = progress
        character.save()
        messages.success(request, "Герой добавлен.")
        return redirect("shelves:reading_track", book_id=progress.book_id)

    context = _build_reading_track_context(progress, progress.book, character_form=form)
    messages.error(request, "Не удалось добавить героя. Исправьте ошибки и попробуйте снова.")
    return render(request, "reading/track.html", context)


@login_required
@require_POST
def reading_update_character(request, progress_id, character_id):
    progress = get_object_or_404(BookProgress, pk=progress_id, user=request.user)
    character = get_object_or_404(CharacterNote, pk=character_id, progress=progress)
    form = CharacterNoteForm(
        request.POST,
        instance=character,
        prefix=f"character-{character.pk}",
    )
    if form.is_valid():
        form.save()
        messages.success(request, "Герой обновлён.")
        return redirect("shelves:reading_track", book_id=progress.book_id)

    context = _build_reading_track_context(
        progress,
        progress.book,
        character_forms={character.pk: form},
    )
    messages.error(request, "Не удалось обновить героя. Проверьте данные и попробуйте снова.")
    return render(request, "reading/track.html", context)


@login_required
@require_POST
def reading_add_quote(request, progress_id):
    progress = get_object_or_404(BookProgress, pk=progress_id, user=request.user)
    form = ProgressQuoteForm(request.POST)
    if form.is_valid():
        quote = form.save(commit=False)
        quote.progress = progress
        quote.kind = ProgressAnnotation.KIND_QUOTE
        quote.save()
        messages.success(request, "Цитата сохранена.")
        return redirect("shelves:reading_track", book_id=progress.book_id)

    context = _build_reading_track_context(
        progress,
        progress.book,
        quote_form=form,
    )
    messages.error(request, "Не удалось сохранить цитату. Исправьте ошибки и попробуйте снова.")
    return render(request, "reading/track.html", context)


@login_required
@require_POST
def reading_update_quote(request, progress_id, quote_id):
    progress = get_object_or_404(BookProgress, pk=progress_id, user=request.user)
    quote = get_object_or_404(
        ProgressAnnotation,
        pk=quote_id,
        progress=progress,
        kind=ProgressAnnotation.KIND_QUOTE,
    )
    form = ProgressQuoteForm(
        request.POST,
        instance=quote,
        prefix=f"quote-{quote.pk}",
    )
    if form.is_valid():
        form.save()
        messages.success(request, "Цитата обновлена.")
        return redirect("shelves:reading_track", book_id=progress.book_id)

    context = _build_reading_track_context(
        progress,
        progress.book,
        quote_forms={quote.pk: form},
    )
    messages.error(request, "Не удалось обновить цитату. Проверьте данные и попробуйте снова.")
    return render(request, "reading/track.html", context)


@login_required
@require_POST
def reading_add_note_entry(request, progress_id):
    progress = get_object_or_404(BookProgress, pk=progress_id, user=request.user)
    form = ProgressNoteEntryForm(request.POST)
    if form.is_valid():
        note = form.save(commit=False)
        note.progress = progress
        note.kind = ProgressAnnotation.KIND_NOTE
        note.save()
        messages.success(request, "Заметка сохранена.")
        return redirect("shelves:reading_track", book_id=progress.book_id)

    context = _build_reading_track_context(
        progress,
        progress.book,
        note_entry_form=form,
    )
    messages.error(request, "Не удалось сохранить заметку. Исправьте ошибки и попробуйте снова.")
    return render(request, "reading/track.html", context)


@login_required
@require_POST
def reading_update_note_entry(request, progress_id, note_id):
    progress = get_object_or_404(BookProgress, pk=progress_id, user=request.user)
    note = get_object_or_404(
        ProgressAnnotation,
        pk=note_id,
        progress=progress,
        kind=ProgressAnnotation.KIND_NOTE,
    )
    form = ProgressNoteEntryForm(
        request.POST,
        instance=note,
        prefix=f"note-{note.pk}",
    )
    if form.is_valid():
        form.save()
        messages.success(request, "Заметка обновлена.")
        return redirect("shelves:reading_track", book_id=progress.book_id)

    context = _build_reading_track_context(
        progress,
        progress.book,
        note_forms={note.pk: form},
    )
    messages.error(request, "Не удалось обновить заметку. Проверьте данные и попробуйте снова.")
    return render(request, "reading/track.html", context)

@login_required
@require_POST
def reading_update_notes(request, progress_id):
    """Сохранение заметок по ходу чтения."""
    progress = get_object_or_404(BookProgress, pk=progress_id, user=request.user)
    form = BookProgressNotesForm(request.POST, instance=progress)
    if form.is_valid():
        form.save()
        messages.success(request, "Заметки сохранены.")
    else:
        messages.error(request, "Не удалось сохранить заметки. Проверьте введённые данные.")
    return redirect("shelves:reading_track", book_id=progress.book_id)


@login_required
@require_POST
def reading_set_page(request, progress_id):
    """Ручное выставление текущей страницы."""
    progress = get_object_or_404(BookProgress, pk=progress_id, user=request.user)
    medium_code = request.POST.get("medium") or BookProgress.FORMAT_PAPER
    reaction_text = (request.POST.get("reaction") or "").strip()
    is_public = _parse_public_flag(request)
    if medium_code == BookProgress.FORMAT_AUDIO:
        messages.error(request, "Для аудиоформата используйте форму фиксации прослушивания.")
        return redirect("shelves:reading_track", book_id=progress.book_id)
    medium = progress.get_medium(medium_code)
    if not medium:
        messages.error(request, "Сначала активируйте выбранный формат в настройках прогресса.")
        return redirect("shelves:reading_track", book_id=progress.book_id)
    previous_page = medium.current_page or 0
    raw_percent = (request.POST.get("percent") or "").strip()
    page: Optional[int]
    percent_decimal: Optional[Decimal] = None
    medium_total_override = (
        medium.total_pages_override
        or progress.custom_total_pages
        or (progress.book.get_total_pages() if progress.book else None)
    )
    if raw_percent:
        try:
            percent_decimal = Decimal(raw_percent.replace(",", "."))
        except (InvalidOperation, ValueError):
            messages.error(request, "Укажите корректное значение процента.")
            return redirect("shelves:reading_track", book_id=progress.book_id)
        if percent_decimal < 0 or percent_decimal > Decimal("100"):
            messages.error(request, "Процент прогресса должен быть от 0 до 100.")
            return redirect("shelves:reading_track", book_id=progress.book_id)
        if not medium_total_override:
            messages.error(
                request,
                "Сначала укажите количество страниц для этого формата в настройках.",
            )
            return redirect("shelves:reading_track", book_id=progress.book_id)
        page_decimal = (
            Decimal(medium_total_override)
            * percent_decimal
            / Decimal("100")
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        page = int(page_decimal)
    else:
        try:
            page = int(request.POST.get("page", 0))
        except (TypeError, ValueError):
            messages.error(request, "Неверное значение страницы.")
            return redirect("shelves:reading_track", book_id=progress.book_id)

    clamp_total = medium.total_pages_override or medium_total_override
    if clamp_total:
        clamp_int = int(clamp_total)
        page = max(0, min(page, clamp_int))
    else:
        page = max(0, page)

    medium.current_page = page
    update_fields = ["current_page"]
    if medium.total_pages_override is None and progress.custom_total_pages:
        medium.total_pages_override = progress.custom_total_pages
        update_fields.append("total_pages_override")
    medium.save(update_fields=update_fields)

    total_base = progress.get_effective_total_pages()

    def _percent_from_page(page_value: int) -> Decimal:
        denominator = medium.total_pages_override or clamp_total or total_base
        if denominator and denominator > 0:
            percent_value = (
                Decimal(page_value)
                / Decimal(denominator)
                * Decimal("100")
            )
            return percent_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return Decimal("0")

    def _equivalent_from_percent(percent_value: Decimal) -> Decimal:
        if total_base:
            return (
                Decimal(total_base)
                * percent_value
                / Decimal("100")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        denominator = medium.total_pages_override or clamp_total
        if denominator:
            return (
                Decimal(denominator)
                * percent_value
                / Decimal("100")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return Decimal("0")

    previous_percent = _percent_from_page(previous_page)
    new_percent = (
        percent_decimal
        if percent_decimal is not None
        else _percent_from_page(page)
    )
    previous_equivalent = _equivalent_from_percent(previous_percent)
    new_equivalent = _equivalent_from_percent(new_percent)
    delta_equivalent = max(Decimal("0"), new_equivalent - previous_equivalent)
    progress_changed = delta_equivalent > 0
    if delta_equivalent > 0:
        progress.record_pages(delta_equivalent, medium=medium_code)
        progress.sync_media_equivalents(
            source_medium=medium_code,
            percent_complete=new_percent,
        )
    progress.refresh_current_page()
    progress.recalc_percent()
    if progress_changed:
        _maybe_publish_feed_entry(
            progress,
            medium_code=medium_code,
            reaction=reaction_text,
            is_public=is_public,
        )
    messages.success(request, "Текущая страница обновлена.")
    return redirect("shelves:reading_track", book_id=progress.book_id)


def _parse_audio_seconds(request):
    raw_duration = request.POST.get("duration")
    if raw_duration:
        parts = raw_duration.split(":")
        if len(parts) == 3:
            try:
                hours, minutes, seconds = (int(part) for part in parts)
            except ValueError:
                return None
            if hours < 0 or minutes < 0 or minutes >= 60 or seconds < 0 or seconds >= 60:
                return None
            return hours * 3600 + minutes * 60 + seconds
    raw_minutes = request.POST.get("minutes")
    if raw_minutes:
        try:
            minutes = Decimal(raw_minutes)
        except (InvalidOperation, ValueError):
            return None
        if minutes < 0:
            return None
        seconds = (minutes * Decimal(60)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return int(seconds)
    raw_seconds = request.POST.get("seconds")
    if raw_seconds:
        try:
            seconds = int(Decimal(raw_seconds))
        except (InvalidOperation, ValueError):
            return None
        if seconds < 0:
            return None
        return seconds
    return None


def _parse_public_flag(request):
    raw_flag = str(request.POST.get("is_public", "")).strip().lower()
    return raw_flag in {"1", "true", "on", "yes"}


def _maybe_publish_feed_entry(progress, *, medium_code, reaction, is_public):
    if not is_public:
        return
    combined = progress.get_combined_current_pages()
    current_page = None
    if combined is not None:
        current_page = combined.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    percent_value = progress.percent if progress.percent is not None else None
    ReadingFeedEntry.objects.create(
        progress=progress,
        user=progress.user,
        book=progress.book,
        medium=medium_code,
        current_page=current_page,
        percent=percent_value,
        reaction=(reaction or "").strip(),
        is_public=True,
    )


@login_required
@require_POST
def reading_increment(request, progress_id, delta):
    """Быстрые кнопки +N страниц или учёт прослушанного аудио."""
    progress = get_object_or_404(BookProgress, pk=progress_id, user=request.user)
    medium_code = request.POST.get("medium") or BookProgress.FORMAT_PAPER
    reaction_text = (request.POST.get("reaction") or "").strip()
    is_public = _parse_public_flag(request)
    progress_changed = False
    if medium_code == BookProgress.FORMAT_AUDIO:
        seconds = _parse_audio_seconds(request)
        if not seconds:
            messages.error(request, "Укажите, сколько времени вы прослушали.")
            return redirect("shelves:reading_track", book_id=progress.book_id)
        medium = progress.get_medium(BookProgress.FORMAT_AUDIO)
        if not medium:
            messages.error(request, "Сначала активируйте аудиоформат в настройках.")
            return redirect("shelves:reading_track", book_id=progress.book_id)
        previous_position = medium.audio_position or progress.audio_position or timedelta()
        previous_seconds = int(previous_position.total_seconds())
        playback_speed = progress.get_effective_playback_speed(medium)
        adjusted_seconds = (
            Decimal(seconds) * playback_speed
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        new_seconds = previous_seconds + int(adjusted_seconds)
        audio_length = medium.audio_length or progress.audio_length
        if audio_length:
            max_seconds = int(audio_length.total_seconds())
            new_seconds = min(new_seconds, max_seconds)
        medium.audio_position = timedelta(seconds=new_seconds)
        medium.audio_length = audio_length
        update_fields = ["audio_position", "audio_length"]
        if not medium.playback_speed and progress.audio_playback_speed:
            medium.playback_speed = progress.audio_playback_speed
            update_fields.append("playback_speed")
        medium.save(update_fields=update_fields)
        progress.audio_position = medium.audio_position
        progress.save(update_fields=["audio_position"])
        total_base = progress.get_effective_total_pages()

        def _percent_from_seconds(value_seconds: int) -> Decimal:
            if not audio_length:
                return Decimal("0")
            length_decimal = Decimal(str(audio_length.total_seconds()))
            if length_decimal <= 0:
                return Decimal("0")
            percent_value = (
                Decimal(value_seconds)
                / length_decimal
                * Decimal("100")
            )
            return percent_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        def _equivalent_from_percent(percent_value: Decimal) -> Decimal:
            if total_base:
                return (
                    Decimal(total_base)
                    * percent_value
                    / Decimal("100")
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return Decimal("0")

        previous_percent = _percent_from_seconds(previous_seconds)
        new_percent = _percent_from_seconds(new_seconds)
        new_equivalent = _equivalent_from_percent(new_percent)
        previous_equivalent = _equivalent_from_percent(previous_percent)
        delta_pages = max(Decimal("0"), new_equivalent - previous_equivalent)
        delta_seconds = max(0, new_seconds - previous_seconds)
        if delta_pages > 0 and delta_seconds > 0:
            progress.record_pages(delta_pages, medium=BookProgress.FORMAT_AUDIO, audio_seconds=delta_seconds)
        if new_percent > previous_percent:
            progress.sync_media_equivalents(
                source_medium=BookProgress.FORMAT_AUDIO,
                percent_complete=new_percent,
            )
            progress_changed = True
        progress.refresh_current_page()
        progress.recalc_percent()
        if progress_changed:
            _maybe_publish_feed_entry(
                progress,
                medium_code=BookProgress.FORMAT_AUDIO,
                reaction=reaction_text,
                is_public=is_public,
            )
        messages.success(request, "Аудиопрогресс обновлён.")
        return redirect("shelves:reading_track", book_id=progress.book_id)
    
    try:
        step = int(delta)
    except (TypeError, ValueError):
        messages.error(request, "Неверное значение шага.")
        return redirect("shelves:reading_track", book_id=progress.book_id)
    medium = progress.get_medium(medium_code)
    if not medium:
        messages.error(request, "Сначала активируйте выбранный формат в настройках прогресса.")
        return redirect("shelves:reading_track", book_id=progress.book_id)
    cur = medium.current_page or 0
    medium_total_override = (
        medium.total_pages_override
        or progress.custom_total_pages
        or (progress.book.get_total_pages() if progress.book else None)
    )
    new_page = cur + step
    if medium_total_override:
        new_page = max(0, min(new_page, int(medium_total_override)))
    else:
        new_page = max(0, new_page)
    medium.current_page = new_page
    update_fields = ["current_page"]
    if medium.total_pages_override is None and progress.custom_total_pages:
        medium.total_pages_override = progress.custom_total_pages
        update_fields.append("total_pages_override")
    medium.save(update_fields=update_fields)

    total_base = progress.get_effective_total_pages()

    def _percent_from_page(page_value: int) -> Decimal:
        denominator = medium.total_pages_override or medium_total_override or total_base
        if denominator and denominator > 0:
            percent_value = (
                Decimal(page_value)
                / Decimal(denominator)
                * Decimal("100")
            )
            return percent_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return Decimal("0")

    def _equivalent_from_percent(percent_value: Decimal) -> Decimal:
        if total_base:
            return (
                Decimal(total_base)
                * percent_value
                / Decimal("100")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        denominator = medium.total_pages_override or medium_total_override
        if denominator:
            return (
                Decimal(denominator)
                * percent_value
                / Decimal("100")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return Decimal("0")

    previous_percent = _percent_from_page(cur)
    new_percent = _percent_from_page(new_page)
    previous_equivalent = _equivalent_from_percent(previous_percent)
    new_equivalent = _equivalent_from_percent(new_percent)
    diff_equivalent = max(Decimal("0"), new_equivalent - previous_equivalent)
    if diff_equivalent > 0:
        progress.record_pages(diff_equivalent, medium=medium_code)
        progress_changed = True
    if new_percent > previous_percent:
        progress.sync_media_equivalents(
            source_medium=medium_code,
            percent_complete=new_percent,
        )
        progress_changed = True
    progress.refresh_current_page()
    progress.recalc_percent()
    if progress_changed:
        _maybe_publish_feed_entry(
            progress,
            medium_code=medium_code,
            reaction=reaction_text,
            is_public=is_public,
        )
        messages.success(request, "Прогресс обновлён.")
    return redirect("shelves:reading_track", book_id=progress.book_id)


@login_required
@require_POST
def reading_mark_finished(request, progress_id):
    """Отметить книгу как прочитанную."""
    progress = get_object_or_404(BookProgress, pk=progress_id, user=request.user)
    total_pages = progress.get_effective_total_pages()
    media_objects = list(progress.media.all())
    if not media_objects and progress.format:
        fallback_medium = progress.get_medium(progress.format)
        if fallback_medium:
            media_objects = [fallback_medium]

    for medium in media_objects:
        if medium.medium == BookProgress.FORMAT_AUDIO:
            previous_position = medium.audio_position or progress.audio_position or timedelta()
            previous_seconds = int(previous_position.total_seconds())
            audio_length = medium.audio_length or progress.audio_length
            if audio_length:
                length_seconds = int(audio_length.total_seconds())
                medium.audio_length = audio_length
                medium.audio_position = audio_length
                if not medium.playback_speed and progress.audio_playback_speed:
                    medium.playback_speed = progress.audio_playback_speed
                medium.save(update_fields=["audio_position", "audio_length", "playback_speed"])
                progress.audio_position = audio_length
                progress.save(update_fields=["audio_position"])
                total_base = progress.get_effective_total_pages()

                def _percent_from_seconds(value_seconds: int) -> Decimal:
                    if length_seconds <= 0:
                        return Decimal("0")
                    percent_value = (
                        Decimal(value_seconds)
                        / Decimal(length_seconds)
                        * Decimal("100")
                    )
                    return percent_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                def _equivalent_from_percent(percent_value: Decimal) -> Decimal:
                    if total_base:
                        return (
                            Decimal(total_base)
                            * percent_value
                            / Decimal("100")
                        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    return Decimal("0")

                previous_percent = _percent_from_seconds(previous_seconds)
                new_percent = Decimal("100")
                new_equivalent = _equivalent_from_percent(new_percent)
                previous_equivalent = _equivalent_from_percent(previous_percent)
                delta_pages = max(Decimal("0"), new_equivalent - previous_equivalent)
                delta_seconds = max(0, length_seconds - previous_seconds)
                if delta_pages > 0 and delta_seconds > 0:
                    progress.record_pages(delta_pages, medium=BookProgress.FORMAT_AUDIO, audio_seconds=delta_seconds)
        else:
            previous_page = medium.current_page or 0
            target_total = (
                medium.total_pages_override
                or progress.custom_total_pages
                or total_pages
            )
            update_fields = []
            if target_total:
                medium.current_page = int(target_total)
                update_fields.append("current_page")
            if medium.total_pages_override is None and progress.custom_total_pages:
                medium.total_pages_override = progress.custom_total_pages
                update_fields.append("total_pages_override")
            if update_fields:
                medium.save(update_fields=update_fields)

            denominator = medium.total_pages_override or target_total or total_pages
            if denominator and denominator > 0:
                previous_percent = (
                    Decimal(previous_page)
                    / Decimal(denominator)
                    * Decimal("100")
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                new_percent = (
                    Decimal(medium.current_page or 0)
                    / Decimal(denominator)
                    * Decimal("100")
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if total_pages:
                    previous_equivalent = (
                        Decimal(total_pages)
                        * previous_percent
                        / Decimal("100")
                    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    new_equivalent = (
                        Decimal(total_pages)
                        * new_percent
                        / Decimal("100")
                    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    delta_pages = max(Decimal("0"), new_equivalent - previous_equivalent)
                    if delta_pages > 0:
                        progress.record_pages(delta_pages, medium=medium.medium)
                if new_percent > previous_percent:
                    progress.sync_media_equivalents(
                        source_medium=medium.medium,
                        percent_complete=new_percent,
                    )


    combined = progress.get_combined_current_pages()
    if combined is not None:
        progress.current_page = int(combined.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        progress.save(update_fields=["current_page"])
    progress.recalc_percent()
    if progress.percent < Decimal("100"):
        progress.percent = Decimal("100")
        progress.save(update_fields=["percent", "updated_at"])
    move_book_to_read_shelf(request.user, progress.book)
    award_for_book_completion(request.user, progress.book)
    messages.success(request, "Книга отмечена как прочитанная.")
    review_link = reverse("book_detail", args=[progress.book_id]) + "#write-review"
    messages.info(
        request,
        format_html(
            "Готовы поделиться впечатлениями? <a class=\"alert-link\" href=\"{}\">Напишите отзыв о книге</a>.",
            review_link,
        ),
    )
    return redirect("shelves:reading_track", book_id=progress.book_id)


@login_required
@require_GET
def reading_finish_celebration_api(request, progress_id):
    """Данные для анимации завершения книги в мобильном приложении."""

    progress = get_object_or_404(BookProgress, pk=progress_id, user=request.user)
    book = progress.book

    cover_url = book.get_cover_url() or ""
    if cover_url.startswith("/"):
        cover_url = request.build_absolute_uri(cover_url)

    content_type = ContentType.objects.get_for_model(book.__class__)
    event = (
        UserPointEvent.objects.filter(
            user=request.user,
            event_type=UserPointEvent.EventType.BOOK_COMPLETED,
            content_type=content_type,
            object_id=book.pk,
        )
        .order_by("-created_at", "-id")
        .first()
    )
    points = event.points if event is not None else BOOK_COMPLETION.points
    reward_text = "+1 к прочитанным книгам" if points == 1 else f"+{points} к книжному пути"

    return JsonResponse(
        {
            "title": book.title,
            "name": book.title,
            "cover": cover_url or None,
            "cover_url": cover_url or None,
            "image": cover_url or None,
            "points": points,
            "reward": points,
            "coins": points,
            "rewardText": reward_text,
        }
    )


@login_required
@require_POST
def reading_update_format(request, progress_id):
    progress = get_object_or_404(BookProgress, pk=progress_id, user=request.user)
    book = progress.book
    form = BookProgressFormatForm(request.POST, instance=progress, book=book)
    if form.is_valid():
        form.save()
        messages.success(request, "Формат чтения обновлён.")
        return redirect("shelves:reading_track", book_id=book.pk)

    context = _build_reading_track_context(progress, book, format_form=form)
    messages.error(request, "Не удалось сохранить формат чтения. Проверьте данные и попробуйте снова.")
    return render(request, "reading/track.html", context)


def reading_feed(request):
    entries = (
        ReadingFeedEntry.objects.filter(is_public=True)
        .select_related(
            "user",
            "user__profile",
            "book",
            "book__primary_isbn",
            "progress",
        )
        .prefetch_related("comments__user", "comments__user__profile", "book__isbn")
    )
    reactions = entries.exclude(reaction__isnull=True).exclude(reaction__exact="")
    reviews = (
        Rating.objects.exclude(review__isnull=True)
        .exclude(review__exact="")
        .select_related(
            "user",
            "user__profile",
            "book",
            "book__primary_isbn",
        )
        .prefetch_related("book__isbn", "comments__user", "comments__user__profile")
        .order_by("-created_at")
    )
    return render(
        request,
        "reading/feed.html",
        {
            "reactions": reactions,
            "reviews": reviews,
            "has_reactions": reactions.exists(),
            "has_reviews": reviews.exists(),
        },
    )


def reading_leaderboard(request):
    today = timezone.localdate()
    timeframes = {
        "today": {
            "label": "Сегодня",
            "start": today,
        },
        "week": {
            "label": "Текущая неделя",
            "start": today - timedelta(days=today.weekday()),
        },
        "month": {
            "label": "Этот месяц",
            "start": today.replace(day=1),
        },
        "year": {
            "label": "За год",
            "start": date(today.year, 1, 1),
        },
    }

    selected_period = request.GET.get("period", "week")
    if selected_period not in timeframes:
        selected_period = "week"

    selected_metric = request.GET.get("metric", "pages")
    if selected_metric not in {"pages", "points"}:
        selected_metric = "pages"

    timeframe = timeframes[selected_period]
    start_date = timeframe["start"]
    end_date = today
    label = timeframe["label"]

    entries = []
    if selected_metric == "pages":
        if start_date <= today:
            user_model = get_user_model()
            aggregates = (
                ReadingLog.objects.filter(
                    log_date__gte=start_date,
                    log_date__lte=today,
                    pages_equivalent__gt=0,
                )
                .order_by()
                .values("progress__user")
                .annotate(total_pages=Sum("pages_equivalent"))
                .values("progress__user", "total_pages")
                .order_by("-total_pages", "progress__user")
            )
            top_rows = list(aggregates[:10])
            user_ids = [row["progress__user"] for row in top_rows]
            users = user_model.objects.filter(id__in=user_ids).select_related("profile")
            user_map = {user.id: user for user in users}
            entries = [
                {
                    "position": index,
                    "user": user_map.get(row["progress__user"]),
                    "total_pages": row["total_pages"],
                }
                for index, row in enumerate(top_rows, start=1)
                if user_map.get(row["progress__user"])
            ]
    else:
        period_map = {
            "today": LeaderboardPeriod.DAY,
            "week": LeaderboardPeriod.WEEK,
            "month": LeaderboardPeriod.MONTH,
            "year": LeaderboardPeriod.YEAR,
        }
        period = period_map[selected_period]
        leaderboard_rows = UserPointEvent.get_leaderboard(period, limit=10)
        entries = [
            {
                "position": index,
                "user": row.get("user"),
                "total_points": row.get("points", 0),
            }
            for index, row in enumerate(leaderboard_rows, start=1)
            if row.get("user")
        ]
        start_date = timezone.localdate(period.period_start())

    board = {
        "key": f"{selected_metric}-{selected_period}",
        "label": label,
        "start": start_date,
        "end": end_date,
        "entries": entries,
    }
    return render(
        request,
        "reading/leaderboard.html",
        {
            "board": board,
            "selected_metric": selected_metric,
            "selected_period": selected_period,
            "view_url_name": "shelves:reading_leaderboard",
        },
    )


@login_required
@require_POST
def reading_feed_comment(request, entry_id):
    entry = get_object_or_404(ReadingFeedEntry, pk=entry_id, is_public=True)
    form = ReadingFeedCommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.entry = entry
        comment.user = request.user
        comment.save()
        messages.success(request, "Комментарий опубликован.")
    else:
        messages.error(request, "Не удалось сохранить комментарий. Проверьте текст и попробуйте снова.")
    return redirect("shelves:reading_feed")


@login_required
@require_POST
def reading_feed_review_comment(request, review_id):
    rating = get_object_or_404(
        Rating.objects.exclude(review__isnull=True).exclude(review__exact=""),
        pk=review_id,
    )
    form = RatingCommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.rating = rating
        comment.user = request.user
        comment.save()
        messages.success(request, "Комментарий опубликован.")
    else:
        messages.error(request, "Не удалось сохранить комментарий. Проверьте текст и попробуйте снова.")
    return redirect(f"{reverse('shelves:reading_feed')}#review-{rating.pk}")