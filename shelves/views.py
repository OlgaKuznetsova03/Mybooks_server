# shelves/views.py
from decimal import Decimal, ROUND_HALF_UP
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from books.models import Book
from .models import Shelf, ShelfItem, BookProgress, Event, EventParticipant
from .forms import (
    ShelfCreateForm,
    AddToShelfForm,
    AddToEventForm,
    BookProgressNotesForm,
    CharacterNoteForm,
)


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
            ShelfItem.objects.get_or_create(shelf=shelf, book=book)
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
    return redirect("my_shelves")


# Быстрое добавление в дефолтные полки
DEFAULT_SHELF_MAP = {
    "want": "Хочу прочитать",
    "reading": "Читаю",
    "read": "Прочитал",
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
    ShelfItem.objects.get_or_create(shelf=shelf, book=book)
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


def _build_reading_track_context(progress, book, *, character_form=None):
    total_pages = book.get_total_pages()  # из primary_isbn.pages (см. метод в модели Book)
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
    context = _build_reading_track_context(progress, book)
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
    previous_page = progress.current_page or 0
    total = progress.book.get_total_pages()
    if total:
        progress.current_page = total
        progress.save(update_fields=["current_page"])
        progress.recalc_percent()
        delta = max(0, (progress.current_page or 0) - previous_page)
        if delta > 0:
            progress.record_pages(delta)
    else:
        # если не знаем total_pages — ставим 100%, страницу не меняем
        progress.percent = 100
        progress.save(update_fields=["percent", "updated_at"])
    messages.success(request, "Книга отмечена как прочитанная.")
    return redirect("reading_track", book_id=progress.book_id)


