from __future__ import annotations

from typing import Any

from django.shortcuts import render
from django.utils import timezone

from reading_clubs.models import ReadingClub
from reading_marathons.models import ReadingMarathon


def home(request):
    return render(request, "config/home.html")


def reading_communities_overview(request):
    today = timezone.localdate()
    clubs_qs = (
        ReadingClub.objects.select_related("book", "book__primary_isbn", "creator")
        .with_message_count()
        .prefetch_related("participants", "book__isbn")
        .order_by("start_date", "title")
    )
    active_clubs: list[ReadingClub] = []
    upcoming_clubs: list[ReadingClub] = []
    past_clubs: list[ReadingClub] = []

    for club in clubs_qs:
        club.set_prefetched_message_count(club.message_count)
        if club.start_date > today:
            upcoming_clubs.append(club)
        elif club.end_date and club.end_date < today:
            past_clubs.append(club)
        else:
            active_clubs.append(club)

    club_groups = [
        _build_group(
            title="Актуальные совместные чтения",
            slug="clubs-active",
            anchor="active",
            description="Участники уже обсуждают книгу и ждут новых идей.",
            items=active_clubs,
        ),
        _build_group(
            title="Предстоящие совместные чтения",
            slug="clubs-upcoming",
            anchor="upcoming",
            description="Запланируйте участие заранее и присоединяйтесь в день старта.",
            items=upcoming_clubs,
        ),
        _build_group(
            title="Завершённые совместные чтения",
            slug="clubs-past",
            anchor="past",
            description="Вернитесь к обсуждениям и идеям, которые уже прозвучали.",
            items=past_clubs,
        ),
    ]

    marathons_qs = ReadingMarathon.objects.prefetch_related("themes").order_by(
        "start_date", "title"
    )
    active_marathons: list[ReadingMarathon] = []
    upcoming_marathons: list[ReadingMarathon] = []
    past_marathons: list[ReadingMarathon] = []

    for marathon in marathons_qs:
        status = marathon.status
        if status == "upcoming":
            upcoming_marathons.append(marathon)
        elif status == "past":
            past_marathons.append(marathon)
        else:
            active_marathons.append(marathon)

    marathon_groups = [
        _build_group(
            title="Идущие марафоны",
            slug="marathons-active",
            description="Участники делятся прогрессом и закрывают читательские этапы.",
            items=active_marathons,
        ),
        _build_group(
            title="Предстоящие марафоны",
            slug="marathons-upcoming",
            description="Присоединяйтесь заранее и подготовьте список книг.",
            items=upcoming_marathons,
        ),
        _build_group(
            title="Завершённые марафоны",
            slug="marathons-past",
            description="Архив читательских побед и идей для новых забегов.",
            items=past_marathons,
        ),
    ]

    context = {
        "club_groups": club_groups,
        "marathon_groups": marathon_groups,
    }
    return render(request, "config/reading_communities.html", context)


def _build_group(
    *,
    title: str,
    slug: str,
    description: str,
    items: list[Any],
    anchor: str | None = None,
    preview_limit: int = 3,
) -> dict[str, Any]:
    preview = items[:preview_limit]
    total = len(items)
    return {
        "title": title,
        "slug": slug,
        "description": description,
        "preview": preview,
        "total": total,
        "extra": max(total - len(preview), 0),
        "anchor": anchor,
    }
