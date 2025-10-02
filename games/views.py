from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from books.models import Rating
from shelves.models import BookProgress
from shelves.services import move_book_to_reading_shelf

from .catalog import get_game_cards
from .forms import (
    BookJourneyAssignForm,
    ForgottenBooksAddForm,
    ForgottenBooksRemoveForm,
    BookJourneyReleaseForm,
    ReadBeforeBuyEnrollForm,
)
from .models import BookJourneyAssignment
from .services.forgotten_books import ForgottenBooksGame
from .services.book_journey import BookJourneyMap
from .services.read_before_buy import ReadBeforeBuyGame


@require_GET
def game_list(request):
    """Display the catalogue of active and upcoming games."""

    cards = get_game_cards()
    available_games = [card for card in cards if card.is_available]
    upcoming_games = [card for card in cards if not card.is_available]

    context = {
        "available_games": available_games,
        "upcoming_games": upcoming_games,
    }
    return render(request, "games/index.html", context)


@login_required
def read_before_buy_dashboard(request):
    game = ReadBeforeBuyGame.get_game()
    states_qs = (
        ReadBeforeBuyGame.iter_participating_shelves(request.user)
        .prefetch_related("shelf__items__book", "books__book", "purchases__book")
        .annotate(total_books=Count("shelf__items", distinct=True))
        .order_by("-points_balance", "shelf__name")
    )
    states = list(states_qs)
    cost = ReadBeforeBuyGame.PURCHASE_COST
    state_details = []
    total_books_counter = 0
    for state in states:
        total_books = getattr(state, "total_books", None)
        if total_books is None:
            total_books = state.shelf.items.count()
        total_books_counter += total_books
        progress_percent = 0
        if cost:
            progress_percent = min(
                100,
                round((state.points_balance / cost) * 100),
            )
        state_details.append(
            {
                "state": state,
                "total_books": total_books,
                "points_needed": max(0, cost - state.points_balance),
                "available_purchases": state.points_balance // cost if cost else 0,
                "progress_percent": progress_percent,
            }
        )

    overall = {
        "points_balance": sum(state.points_balance for state in states),
        "books_reviewed": sum(state.books_reviewed for state in states),
        "books_purchased": sum(state.books_purchased for state in states),
        "total_books": total_books_counter,
    }
    overall_available_purchases = sum(item["available_purchases"] for item in state_details)
    overall["available_purchases"] = overall_available_purchases
    if cost:
        overall["next_purchase_points"] = max(0, cost - overall["points_balance"])
        overall["progress_percent"] = min(
            100,
            round((overall["points_balance"] / cost) * 100),
        )
    else:
        overall["next_purchase_points"] = 0
        overall["progress_percent"] = 0

    enroll_form = ReadBeforeBuyEnrollForm(user=request.user)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "enroll":
            enroll_form = ReadBeforeBuyEnrollForm(request.POST, user=request.user)
            if enroll_form.is_valid():
                shelf = enroll_form.cleaned_data["shelf"]
                ReadBeforeBuyGame.enable_for_shelf(request.user, shelf)
                messages.success(
                    request,
                    f"Полка «{shelf.name}» подключена к игре «{game.title}».",
                )
                return redirect("games:read_before_buy")
            messages.error(request, "Не удалось подключить полку. Проверьте форму.")
        elif action == "bulk_purchase":
            try:
                state_id = int(request.POST.get("state_id", "0"))
            except (TypeError, ValueError):
                messages.error(request, "Не удалось определить полку для списания баллов.")
                return redirect("games:read_before_buy")
            state = ReadBeforeBuyGame.get_state_by_id(request.user, state_id)
            if not state:
                messages.error(request, "Полка не найдена или не подключена к игре.")
                return redirect("games:read_before_buy")
            try:
                count = int(request.POST.get("count", "0"))
            except (TypeError, ValueError):
                messages.error(request, "Укажите количество купленных книг.")
                return redirect("games:read_before_buy")
            success, message_text, level = ReadBeforeBuyGame.spend_points_for_bulk_purchase(
                state, count
            )
            message_handler = getattr(messages, level, messages.info)
            message_handler(request, message_text)
            return redirect("games:read_before_buy")

    context = {
        "game": game,
        "states": state_details,
        "overall": overall,
        "purchase_cost": ReadBeforeBuyGame.PURCHASE_COST,
        "enroll_form": enroll_form,
        "shelf_count": len(state_details),
    }
    return render(request, "games/read_before_buy.html", context)


@login_required
def forgotten_books_dashboard(request):
    """Управление челленджем «12 забытых книг»."""

    game = ForgottenBooksGame.get_game()
    add_form = ForgottenBooksAddForm(user=request.user)
    remove_form = ForgottenBooksRemoveForm(user=request.user)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add":
            add_form = ForgottenBooksAddForm(request.POST, user=request.user)
            if add_form.is_valid():
                book = add_form.cleaned_data["book"]
                success, message_text, level = ForgottenBooksGame.add_book(
                    request.user, book
                )
                message_handler = getattr(messages, level, messages.info)
                message_handler(request, message_text)
                if success:
                    ForgottenBooksGame.ensure_monthly_selection(request.user)
                return redirect("games:forgotten_books")
            messages.error(request, "Не удалось добавить книгу. Проверьте форму.")
        elif action == "remove":
            remove_form = ForgottenBooksRemoveForm(request.POST, user=request.user)
            if remove_form.is_valid():
                entry = remove_form.cleaned_data["entry"]
                success, message_text, level = ForgottenBooksGame.remove_entry(entry)
                message_handler = getattr(messages, level, messages.info)
                message_handler(request, message_text)
                return redirect("games:forgotten_books")
            messages.error(request, "Не удалось удалить книгу из списка.")

    selection = ForgottenBooksGame.ensure_monthly_selection(request.user)
    if not selection:
        selection = ForgottenBooksGame.get_current_selection(request.user)

    entries_qs = ForgottenBooksGame.get_entries(request.user)
    entries = list(
        entries_qs.order_by("selected_month", "added_at", "book__title")
    )
    selected_entries = [entry for entry in entries if entry.selected_month]
    pending_entries = [entry for entry in entries if not entry.selected_month]
    remaining_slots = max(0, ForgottenBooksGame.MAX_BOOKS - len(entries))
    added_books_count = ForgottenBooksGame.MAX_BOOKS - remaining_slots

    context = {
        "game": game,
        "add_form": add_form,
        "remove_form": remove_form,
        "selection": selection,
        "selected_entries": selected_entries,
        "pending_entries": pending_entries,
        "remaining_slots": remaining_slots,
        "added_books_count": added_books_count,
        "max_books": ForgottenBooksGame.MAX_BOOKS,
    }

    return render(request, "games/forgotten_books.html", context)


def book_journey_map(request):
    """Render the interactive 15-step literary journey map."""

    user = request.user
    assignment_form = None
    release_form = BookJourneyReleaseForm()

    if request.method == "POST":
        if not user.is_authenticated:
            messages.error(request, "Авторизуйтесь, чтобы прикреплять книги к заданиям.")
            return redirect("login")
        action = request.POST.get("action")
        if action == "assign":
            assignment_form = BookJourneyAssignForm(request.POST, user=user)
            if assignment_form.is_valid():
                stage_number = assignment_form.cleaned_data["stage_number"]
                book = assignment_form.cleaned_data["book"]
                stage = BookJourneyMap.get_stage_by_number(stage_number)
                active_other = (
                    BookJourneyAssignment.objects.filter(
                        user=user,
                        status=BookJourneyAssignment.Status.IN_PROGRESS,
                    )
                    .exclude(stage_number=stage_number)
                    .first()
                )
                if active_other:
                    other_stage = BookJourneyMap.get_stage_by_number(active_other.stage_number)
                    messages.error(
                        request,
                        (
                            "У вас уже есть активное задание: "
                            f"#{active_other.stage_number} «{other_stage.title if other_stage else 'Без названия'}»."
                            " Завершите его или снимите книгу, чтобы продолжить."
                        ),
                    )
                else:
                    assignment, created = BookJourneyAssignment.objects.get_or_create(
                        user=user,
                        stage_number=stage_number,
                        defaults={"book": book},
                    )
                    if created:
                        assignment.reset_progress(book=book)
                    else:
                        if assignment.is_completed:
                            messages.error(
                                request,
                                "Завершённое задание нельзя перепроходить повторно.",
                            )
                            return redirect("games:book_journey_map")
                        assignment.reset_progress(book=book)
                    move_book_to_reading_shelf(user, book)

                    BookProgress.objects.get_or_create(
                        event=None,
                        user=user,
                        book=book,
                        defaults={"percent": Decimal("0"), "current_page": 0},
                    )
                    BookJourneyAssignment.sync_for_user_book(user, book)
                    messages.success(
                        request,
                        f"Книга «{book.title}» прикреплена к этапу #{stage_number} «{stage.title}».",
                    )
                    return redirect("games:book_journey_map")
        elif action == "release":
            release_form = BookJourneyReleaseForm(request.POST)
            if release_form.is_valid():
                stage_number = release_form.cleaned_data["stage_number"]
                assignment = BookJourneyAssignment.objects.filter(
                    user=user, stage_number=stage_number
                ).first()
                stage = BookJourneyMap.get_stage_by_number(stage_number)
                if not assignment:
                    messages.error(request, "Для этого этапа пока не выбрана книга.")
                elif assignment.is_completed:
                    messages.error(request, "Завершённое задание нельзя отменить.")
                else:
                    assignment.delete()
                    title = stage.title if stage else f"#{stage_number}"
                    messages.success(request, f"Этап «{title}» снова свободен.")
                return redirect("games:book_journey_map")
        else:
            assignment_form = BookJourneyAssignForm(user=user)

    if assignment_form is None and user.is_authenticated:
        assignment_form = BookJourneyAssignForm(user=user)

    assignment_lookup = {}
    progress_lookup = {}
    review_lookup = {}
    active_stage_number = None
    if user.is_authenticated:
        assignments = (
            BookJourneyAssignment.objects.filter(user=user)
            .select_related("book")
            .order_by("stage_number")
        )
        assignment_lookup = {item.stage_number: item for item in assignments}
        book_ids = [assignment.book_id for assignment in assignments]
        if book_ids:
            progress_lookup = {
                progress.book_id: progress
                for progress in BookProgress.objects.filter(user=user, book_id__in=book_ids)
            }
            review_lookup = {
                rating.book_id: rating
                for rating in Rating.objects.filter(user=user, book_id__in=book_ids)
            }
        for assignment in assignments:
            if assignment.status == BookJourneyAssignment.Status.IN_PROGRESS:
                active_stage_number = assignment.stage_number
                break

    stages = []
    completed_count = 0
    in_progress_count = 0
    assigned_count = 0
    next_available_stage = None
    for stage in BookJourneyMap.get_stages():
        assignment = assignment_lookup.get(stage.number)
        status = "available"
        assignment_payload = None
        if assignment:
            if assignment.status == BookJourneyAssignment.Status.COMPLETED:
                status = "completed"
            else:
                status = "in_progress"
            progress = progress_lookup.get(assignment.book_id)
            rating = review_lookup.get(assignment.book_id)
            percent = None
            if progress and progress.percent is not None:
                try:
                    percent = float(progress.percent)
                except (TypeError, ValueError):  # pragma: no cover - defensive
                    percent = None
            assignment_payload = {
                "id": assignment.id,
                "book_id": assignment.book_id,
                "book_title": assignment.book.title,
                "status": assignment.status,
                "is_completed": assignment.is_completed,
                "progress_percent": percent,
                "has_review": bool(
                    rating and str(getattr(rating, "review", "") or "").strip()
                ),
                "detail_url": reverse("book_detail", args=[assignment.book_id]),
                "reading_url": reverse("reading_track", args=[assignment.book_id]),
                "review_url": reverse("book_detail", args=[assignment.book_id]) + "#write-review",
                "started_at": assignment.started_at,
                "completed_at": assignment.completed_at,
            }
            assigned_count += 1
        stages.append(
            {
                "number": stage.number,
                "title": stage.title,
                "requirement": stage.requirement,
                "description": stage.description,
                "terrain": stage.terrain,
                "terrain_label": BookJourneyMap.TERRAIN.get(stage.terrain, {}).get(
                    "label", stage.terrain.capitalize()
                ),
                "top": stage.top,
                "left": stage.left,
                "status": status,
                "assignment": assignment_payload,
            }
        )

        if status == "completed":
            completed_count += 1
        elif status == "in_progress":
            in_progress_count += 1
        if status == "available" and next_available_stage is None:
            next_available_stage = stage.number

    assignment_stage_value = None
    if assignment_form is not None and assignment_form.is_bound:
        try:
            assignment_stage_value = assignment_form["stage_number"].value()
        except KeyError:  # pragma: no cover - defensive
            assignment_stage_value = None

    stage_count = len(stages)
    available_count = stage_count - completed_count - in_progress_count
    available_count = max(available_count, 0)
    progress_percent = 0
    if stage_count:
        progress_percent = round((completed_count / stage_count) * 100)

    context = {
        "map_title": BookJourneyMap.TITLE,
        "map_description": BookJourneyMap.SUBTITLE,
        "checklist": BookJourneyMap.CHECKLIST,
        "stages": stages,
        "stage_count": BookJourneyMap.get_stage_count(),
        "terrain_legend": BookJourneyMap.get_terrain_legend(),
        "assignment_form": assignment_form,
        "release_form": release_form,
        "active_stage_number": active_stage_number,
        "is_authenticated": user.is_authenticated,
        "status_labels": {
            "available": "Свободно",
            "in_progress": "В процессе",
            "completed": "Выполнено",
        },
        "assignment_stage_value": assignment_stage_value,
        "stage_summary": {
            "total": stage_count,
            "completed": completed_count,
            "in_progress": in_progress_count,
            "available": available_count,
            "assigned": assigned_count,
            "progress_percent": progress_percent,
        },
        "next_available_stage": next_available_stage,
    }
    return render(request, "games/book_journey_map.html", context)