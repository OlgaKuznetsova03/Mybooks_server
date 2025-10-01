from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import redirect, render

from .forms import ReadBeforeBuyEnrollForm
from .services.book_journey import BookJourneyMap
from .services.read_before_buy import ReadBeforeBuyGame


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
        state_details.append(
            {
                "state": state,
                "total_books": total_books,
                "points_needed": max(0, cost - state.points_balance),
                "available_purchases": state.points_balance // cost if cost else 0,
            }
        )

    overall = {
        "points_balance": sum(state.points_balance for state in states),
        "books_reviewed": sum(state.books_reviewed for state in states),
        "books_purchased": sum(state.books_purchased for state in states),
        "total_books": total_books_counter,
    }

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
    }
    return render(request, "games/read_before_buy.html", context)


def book_journey_map(request):
    """Render the 30-step literary journey map."""

    stages = [
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
        }
        for stage in BookJourneyMap.get_stages()
    ]
    context = {
        "map_title": BookJourneyMap.TITLE,
        "map_description": BookJourneyMap.SUBTITLE,
        "checklist": BookJourneyMap.CHECKLIST,
        "stages": stages,
        "stage_count": BookJourneyMap.get_stage_count(),
        "terrain_legend": BookJourneyMap.get_terrain_legend(),
    }
    return render(request, "games/book_journey_map.html", context)