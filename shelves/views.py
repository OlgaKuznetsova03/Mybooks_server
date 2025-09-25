# shelves/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from books.models import Book
from .models import Shelf, ShelfItem, BookProgress, Event, EventParticipant
from .forms import ShelfCreateForm, AddToShelfForm, AddToEventForm


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


@login_required
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
    total_pages = book.get_total_pages()  # из primary_isbn.pages (см. метод в модели Book)
    return render(request, "reading/track.html", {
        "book": book,
        "progress": progress,
        "total_pages": total_pages
    })


@login_required
@require_POST
def reading_set_page(request, progress_id):
    """Ручное выставление текущей страницы."""
    progress = get_object_or_404(BookProgress, pk=progress_id, user=request.user)
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
    return redirect("reading_track", book_id=progress.book_id)


@login_required
@require_POST
def reading_mark_finished(request, progress_id):
    """Отметить книгу как прочитанную."""
    progress = get_object_or_404(BookProgress, pk=progress_id, user=request.user)
    total = progress.book.get_total_pages()
    if total:
        progress.current_page = total
        progress.save(update_fields=["current_page"])
        progress.recalc_percent()
    else:
        # если не знаем total_pages — ставим 100%, страницу не меняем
        progress.percent = 100
        progress.save(update_fields=["percent", "updated_at"])
    messages.success(request, "Книга отмечена как прочитанная.")
    return redirect("reading_track", book_id=progress.book_id)


