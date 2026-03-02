from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Count, IntegerField, Max, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import render
from django.utils import timezone

from reading_clubs.models import ReadingClub
from reading_marathons.models import (
    MarathonParticipant,
    MarathonTheme,
    ReadingMarathon,
)
from shelves.models import BookProgress, Shelf, ShelfItem


def home(request):
    today = timezone.localdate()
    clubs_qs = (
        ReadingClub.objects.select_related("book", "book__primary_isbn", "creator")
        .with_message_count()
        .prefetch_related("participants", "book__isbn")
        .filter(start_date__lte=today)
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
        .order_by("start_date", "title")[:8]
    )

    active_clubs: list[ReadingClub] = []
    for club in clubs_qs:
        club.set_prefetched_message_count(club.message_count)
        annotated_participants = club.__dict__.get("approved_participant_count")
        if annotated_participants is not None:
            club.approved_participant_count = annotated_participants
        active_clubs.append(club)

    approved_participants = (
        MarathonParticipant.objects.filter(
            marathon=OuterRef("pk"), status=MarathonParticipant.Status.APPROVED
        )
        .values("marathon")
        .annotate(total=Count("id"))
        .values("total")
    )

    theme_counts = (
        MarathonTheme.objects.filter(marathon=OuterRef("pk"))
        .values("marathon")
        .annotate(total=Count("id"))
        .values("total")
    )

    active_marathons = (
        ReadingMarathon.objects.prefetch_related("themes")
        .annotate(
            participant_count=Coalesce(
                Subquery(approved_participants, output_field=IntegerField()), Value(0)
            )
        )
        .annotate(
            theme_count=Coalesce(
                Subquery(theme_counts, output_field=IntegerField()), Value(0)
            )
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=today), start_date__lte=today)
        .order_by("start_date", "title", "id")
        [:8]
    )

    reading_items: list[ShelfItem] = []
    latest_tracker_updates: list[BookProgress] = []
    if request.user.is_authenticated:
        reading_shelf = Shelf.objects.filter(user=request.user, name="Читаю").first()
        if reading_shelf:
            reading_items = list(
                ShelfItem.objects.filter(shelf=reading_shelf)
                .select_related("book")
                .prefetch_related("book__authors")[:4]
            )

            book_ids = [item.book_id for item in reading_items]
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

            for item in reading_items:
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

        latest_user_updates = (
            BookProgress.objects.filter(event__isnull=True)
            .values("user_id")
            .annotate(
                latest_updated_at=Max("updated_at"),
                latest_progress_id=Subquery(
                    BookProgress.objects.filter(
                        event__isnull=True,
                        user_id=OuterRef("user_id"),
                    )
                    .order_by("-updated_at", "-id")
                    .values("id")[:1]
                ),
            )
            .order_by("-latest_updated_at")[:10]
        )

        latest_progress_ids = [
            row["latest_progress_id"]
            for row in latest_user_updates
            if row.get("latest_progress_id")
        ]
        if latest_progress_ids:
            updates_map = {
                progress.id: progress
                for progress in BookProgress.objects.filter(id__in=latest_progress_ids)
                .select_related("user", "user__profile", "book", "book__primary_isbn")
            }
            latest_tracker_updates = [
                updates_map[progress_id]
                for progress_id in latest_progress_ids
                if progress_id in updates_map
            ]


    context = {
        "active_clubs": active_clubs,
        "active_marathons": active_marathons,
        "reading_items": reading_items,
        "latest_tracker_updates": latest_tracker_updates,
    }
    return render(request, "config/home.html", context)


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
        "items": items,
        "total": total,
        "extra": max(total - len(preview), 0),
        "anchor": anchor,
    }
    
def rules(request):
    """
    Отображает страницу с правилами пользования сайтом kalejdoskopknig.ru.
    """
    context = {
        "page_title": "Правила пользования сайтом",
        "last_updated": "12.11.2025",
    }
    return render(request, "config/terms.html", context)