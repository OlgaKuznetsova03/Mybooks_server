# shelves/views.py
from decimal import Decimal, ROUND_HALF_UP
from datetime import date

from django.db.models import Count
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from books.models import Book, Genre
from .models import Shelf, ShelfItem, BookProgress, Event, EventParticipant, HomeLibraryEntry
from .services import (
    move_book_to_read_shelf,
    remove_book_from_want_shelf,
    DEFAULT_WANT_SHELF,
    DEFAULT_READING_SHELF,
    DEFAULT_READ_SHELF,
    get_home_library_shelf,
)
from .forms import (
    ShelfCreateForm,
    AddToShelfForm,
    AddToEventForm,
    BookProgressNotesForm,
    CharacterNoteForm,
    BookProgressFormatForm,
    HomeLibraryEntryForm,
    HomeLibraryFilterForm,
)
from games.services.read_before_buy import ReadBeforeBuyGame


def event_list(request):
    events = Event.objects.all()
    return render(request, "shelves/event_list.html", {"events": events})

def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)
    return render(request, "shelves/event_detail.html", {"event": event})

def event_join(request, pk):
    event = get_object_or_404(Event, pk=pk)
    event.participants.add(request.user)
    return redirect("event_detail", pk=pk)

def event_leave(request, pk):
    event = get_object_or_404(Event, pk=pk)
    event.participants.remove(request.user)
    return redirect("event_detail", pk=pk)


# ---------- ПОЛКИ ----------

@login_required
def my_shelves(request):
    """Список полок текущего пользователя с книгами."""
    shelves = (
        Shelf.objects
        .filter(user=request.user)
        .prefetch_related("items__book")
        .order_by("-is_default", "name")
    )
    return render(request, "shelves/my_shelves.html", {"shelves": shelves})


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
        for entry in HomeLibraryEntry.objects
        .filter(shelf_item_id__in=item_ids)
        .select_related("shelf_item__book")
    }
    entries = []
    for item in items:
        entry = entry_map.get(item.id)
        if entry is None:
            entry = HomeLibraryEntry.objects.create(
                shelf_item=item,
                series_name=item.book.series or "",
            )
            if item.book.genres.exists():
                entry.custom_genres.set(item.book.genres.all())
        elif not entry.series_name and item.book.series:
            entry.series_name = item.book.series
            entry.save(update_fields=["series_name"])
        entry_map[item.id] = entry

    entries_qs = (
        HomeLibraryEntry.objects
        .filter(shelf_item__shelf=shelf)
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
        .order_by("-total", "location")[:5]
    )
    status_counts = list(
        entries_qs
        .exclude(status="")
        .values("status")
        .annotate(total=Count("id"))
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
            .exclude(custom_genres__name__isnull=True)
            .order_by("-total", "custom_genres__name")[:5]
        )
    ]

    def _sort_key(entry: HomeLibraryEntry):
        acquired = entry.acquired_at or date.min
        added = entry.shelf_item.added_at.date() if entry.shelf_item.added_at else date.min
        return (acquired, added, entry.shelf_item_id)

    recent_entries = sorted(active_entries_qs, key=_sort_key, reverse=True)[:5]

    series_values = list(
        active_entries_qs
        .exclude(series_name="")
        .values_list("series_name", flat=True)
        .distinct()
    )
    genre_queryset = (
        Genre.objects
        .filter(home_library_entries__shelf_item__shelf=shelf, home_library_entries__is_disposed=False)
        .distinct()
        .order_by("name")
    )
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

    entries = list(
        filtered_entries_qs
        .order_by("shelf_item__book__title", "shelf_item__id")
    )
    disposed_entries = list(
        disposed_entries_qs
        .order_by("shelf_item__book__title", "shelf_item__id")
    )

    summary = {
        "total": total_active,
        "disposed_total": disposed_total,
        "classic_count": classic_count,
        "modern_count": total_active - classic_count,
        "series_counts": series_counts,
        "genre_counts": genre_counts,
        "locations": location_counts,
        "statuses": status_counts,
        "recent_entries": recent_entries,
    }

    context = {
        "shelf": shelf,
        "entries": entries,
        "disposed_entries": disposed_entries,
        "summary": summary,
        "disposed_entries": disposed_entries,
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
            next_url = request.POST.get("next") or reverse("home_library")
            return redirect(next_url)
    else:
        form = HomeLibraryEntryForm(instance=entry)

    next_url = request.GET.get("next") or reverse("home_library")
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
    if code not in DEFAULT_SHELF_MAP:
        messages.error(request, "Неизвестная полка.")
        return redirect("book_detail", pk=book.pk)
    shelf_name = DEFAULT_SHELF_MAP[code]
    shelf, _ = Shelf.objects.get_or_create(
        user=request.user,
        name=shelf_name,
        defaults={"is_default": True, "is_public": True},
    )
    if code == "read":
        move_book_to_read_shelf(request.user, book)
        messages.success(request, f"«{book.title}» добавлена в «{shelf.name}».")
        return redirect("book_detail", pk=book.pk)

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
            return redirect("reading_track", book_id=book.pk)
        return redirect("book_detail", pk=book.pk)

    ShelfItem.objects.get_or_create(shelf=shelf, book=book)
    if code == "reading":
        remove_book_from_want_shelf(request.user, book)
        messages.success(request, f"«{book.title}» добавлена в «{shelf.name}».")
        messages.info(request, "Уточните формат чтения и данные книги на странице прогресса.")
        return redirect("reading_track", book_id=book.pk)
    messages.success(request, f"«{book.title}» добавлена в «{shelf.name}».")
    return redirect("book_detail", pk=book.pk)


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
            return redirect("reading_track", book_id=book.pk)
    else:
        form = AddToEventForm(user=request.user)

    return render(request, "shelves/add_to_event.html", {"form": form, "book": book})


# ---------- ЧТЕНИЕ / ПРОГРЕСС ----------

@login_required
def reading_now(request):
    """Страница «Читаю сейчас»: берём книги из полки 'Читаю'."""
    shelf = Shelf.objects.filter(user=request.user, name="Читаю").first()
    items = ShelfItem.objects.filter(shelf=shelf).select_related("book") if shelf else []
    return render(request, "reading/reading_now.html", {"shelf": shelf, "items": items})


def _build_reading_track_context(progress, book, *, character_form=None, format_form=None):
    total_pages = progress.get_effective_total_pages()
    calculated_percent = None
    if total_pages and progress.current_page is not None:
        total_decimal = Decimal(total_pages)
        current_decimal = Decimal(progress.current_page)
        percent = current_decimal / (total_decimal / Decimal(100))
        calculated_percent = float(percent.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    daily_logs = progress.logs.order_by("-log_date")
    notes_form = BookProgressNotesForm(instance=progress)
    chart_logs = list(progress.logs.order_by("log_date"))
    chart_labels = [log.log_date.strftime("%d.%m.%Y") for log in chart_logs]
    chart_pages = [(log.pages_read or 0) for log in chart_logs]
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
    audio_length_display = None
    if progress.audio_length:
        total_seconds = int(progress.audio_length.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        audio_length_display = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    characters = progress.character_entries.all()
    return {
        "book": book,
        "progress": progress,
        "total_pages": total_pages,
        "calculated_percent": calculated_percent,
        "daily_logs": daily_logs,
        "notes_form": notes_form,
        "character_form": character_form,
        "characters": characters,
        "average_pages_per_day": average_pages_per_day,
        "estimated_days_remaining": estimated_days_remaining,
        "chart_labels": chart_labels,
        "chart_pages": chart_pages,
        "chart_scale": chart_scale,
        "format_form": format_form,
        "audio_length_display": audio_length_display,
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
        return redirect("reading_track", book_id=progress.book_id)

    book = progress.book
    context = _build_reading_track_context(progress, book, character_form=form)
    messages.error(request, "Не удалось добавить героя. Исправьте ошибки и попробуйте снова.")
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
    return redirect("reading_track", book_id=progress.book_id)


@login_required
@require_POST
def reading_set_page(request, progress_id):
    """Ручное выставление текущей страницы."""
    progress = get_object_or_404(BookProgress, pk=progress_id, user=request.user)
    if progress.is_audiobook:
        messages.error(request, "Для аудиокниги не нужно указывать страницы.")
        return redirect("reading_track", book_id=progress.book_id)
    previous_page = progress.current_page or 0
    try:
        page = int(request.POST.get("page", 0))
    except (TypeError, ValueError):
        messages.error(request, "Неверное значение страницы.")
        return redirect("reading_track", book_id=progress.book_id)

    total = progress.book.get_total_pages()
    if total:
        page = max(0, min(page, total))
    progress.current_page = page
    progress.save(update_fields=["current_page"])
    progress.recalc_percent()
    delta = max(0, (progress.current_page or 0) - previous_page)
    if delta > 0:
        progress.record_pages(delta)
    messages.success(request, "Текущая страница обновлена.")
    return redirect("reading_track", book_id=progress.book_id)


@login_required
@require_POST
def reading_increment(request, progress_id, delta):
    """Быстрые кнопки +N страниц."""
    progress = get_object_or_404(BookProgress, pk=progress_id, user=request.user)
    if progress.is_audiobook:
        messages.error(request, "Для аудиокниги не нужно указывать страницы.")
        return redirect("reading_track", book_id=progress.book_id)
    cur = progress.current_page or 0
    total = progress.book.get_total_pages()
    new_page = cur + int(delta)
    if total:
        new_page = max(0, min(new_page, total))
    progress.current_page = new_page
    progress.save(update_fields=["current_page"])
    progress.recalc_percent()
    diff = max(0, new_page - cur)
    if diff > 0:
        progress.record_pages(diff)
    return redirect("reading_track", book_id=progress.book_id)


@login_required
@require_POST
def reading_mark_finished(request, progress_id):
    """Отметить книгу как прочитанную."""
    progress = get_object_or_404(BookProgress, pk=progress_id, user=request.user)
    if progress.is_audiobook:
        progress.percent = Decimal("100")
        progress.save(update_fields=["percent", "updated_at"])
    else:
        previous_page = progress.current_page or 0
        total = progress.get_effective_total_pages()
        if total:
            progress.current_page = total
            progress.save(update_fields=["current_page"])
            progress.recalc_percent()
            delta = max(0, (progress.current_page or 0) - previous_page)
            if delta > 0:
                progress.record_pages(delta)
        else:
            progress.percent = Decimal("100")
            progress.save(update_fields=["percent", "updated_at"])
    move_book_to_read_shelf(request.user, progress.book)
    messages.success(request, "Книга отмечена как прочитанная.")
    review_link = reverse("book_detail", args=[progress.book_id]) + "#write-review"
    messages.info(
        request,
        format_html(
            "Готовы поделиться впечатлениями? <a class=\"alert-link\" href=\"{}\">Напишите отзыв о книге</a>.",
            review_link,
        ),
    )
    return redirect("reading_track", book_id=progress.book_id)


@login_required
@require_POST
def reading_update_format(request, progress_id):
    progress = get_object_or_404(BookProgress, pk=progress_id, user=request.user)
    book = progress.book
    form = BookProgressFormatForm(request.POST, instance=progress, book=book)
    if form.is_valid():
        form.save()
        messages.success(request, "Формат чтения обновлён.")
        return redirect("reading_track", book_id=book.pk)

    context = _build_reading_track_context(progress, book, format_form=form)
    messages.error(request, "Не удалось сохранить формат чтения. Проверьте данные и попробуйте снова.")
    return render(request, "reading/track.html", context)
