from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.urls import reverse
from django.utils import timezone

from games.models import BookExchangeOffer, ForgottenBookEntry, MonthlyChallenge
from games.services.monthly_awards import build_monthly_challenge_award_url
from games.services.monthly_challenges import MONTHLY_CHALLENGE_TITLES, month_display
from reading_clubs.models import ReadingParticipant
from reading_clubs.services import get_unread_discussion_topics

from .models import AuthorOfferResponse, BloggerRequestResponse, Collaboration


def _date_payload(value) -> tuple[str | None, str | None]:
    if not value:
        return None, None

    if hasattr(value, "date") and hasattr(value, "strftime"):
        local_value = timezone.localtime(value) if timezone.is_aware(value) else value
        return local_value.isoformat(), local_value.strftime("%d.%m.%Y, %H:%M")

    if hasattr(value, "isoformat"):
        return value.isoformat(), value.strftime("%d.%m.%Y")

    return str(value), str(value)


def _display_name(user) -> str:
    if user is None:
        return ""
    full_name = user.get_full_name() if hasattr(user, "get_full_name") else ""
    return full_name or getattr(user, "username", "") or str(user)


def _item(
    *,
    key: str,
    kind: str,
    section: str,
    title: str,
    text: str = "",
    badge: str = "",
    count: int | None = None,
    created_at=None,
    app_path: str = "",
    site_path: str = "",
    action_label: str = "Открыть",
    unread: bool = True,
    image_url: str | None = None,
    accent: str = "green",
) -> dict[str, Any]:
    created_iso, created_label = _date_payload(created_at)
    return {
        "id": key,
        "kind": kind,
        "section": section,
        "title": title,
        "text": text,
        "badge": badge,
        "count": count,
        "created_at": created_iso,
        "created_label": created_label,
        "app_path": app_path,
        "site_path": site_path,
        "action_label": action_label,
        "unread": unread,
        "image_url": image_url,
        "accent": accent,
    }


def collect_notification_items(user, *, include_informational: bool = True) -> dict[str, Any]:
    if user is None or not getattr(user, "is_authenticated", False):
        return {
            "unread_count": 0,
            "items": [],
            "groups": {},
        }

    now = timezone.now()
    recent_awards_since = now - timedelta(days=14)
    items: list[dict[str, Any]] = []
    groups = {
        "reading_clubs": 0,
        "cooperation": 0,
        "games": 0,
        "awards": 0,
    }

    unread_topics, unread_reading_total = get_unread_discussion_topics(user)
    for topic in unread_topics[:20]:
        count = int(getattr(topic, "unread_count", 0) or 0)
        reading = getattr(topic, "reading", None)
        items.append(
            _item(
                key=f"reading-topic-{topic.pk}",
                kind="reading_club_message",
                section="Совместные чтения",
                title=getattr(topic, "title", "Новые сообщения"),
                text=f"{getattr(reading, 'title', 'Совместное чтение')}: {count} новых сообщений",
                badge=f"{count} новых",
                count=count,
                created_at=getattr(topic, "last_post_at", None),
                app_path=f"/community/reading-clubs/{reading.slug}/topics/{topic.pk}" if reading else "/community",
                site_path=topic.get_absolute_url() if hasattr(topic, "get_absolute_url") else "",
                action_label="К обсуждению",
                accent="green",
            )
        )
    groups["reading_clubs"] += int(unread_reading_total or 0)

    pending_game_offers = (
        BookExchangeOffer.objects.filter(
            challenge__user=user,
            status=BookExchangeOffer.Status.PENDING,
        )
        .select_related("challenge", "challenge__game", "offered_by", "book")
        .order_by("-created_at")[:20]
    )
    for offer in pending_game_offers:
        offered_by = _display_name(offer.offered_by)
        book = getattr(offer, "book", None)
        items.append(
            _item(
                key=f"book-exchange-offer-{offer.pk}",
                kind="book_exchange_offer",
                section="Игры",
                title="Вам предложили книгу",
                text=f"{getattr(book, 'title', 'Книга')} от {offered_by}",
                badge="Обмен вызовами",
                count=1,
                created_at=offer.created_at,
                app_path="/games/book-exchange-challenge",
                site_path="/games/book-exchange/",
                action_label="Открыть игру",
                accent="orange",
            )
        )
    groups["games"] += len(pending_game_offers)

    pending_offer_responses = (
        AuthorOfferResponse.objects.filter(
            offer__author=user,
            status=AuthorOfferResponse.Status.PENDING,
        )
        .select_related("offer", "respondent")
        .order_by("-created_at")[:20]
    )
    for response in pending_offer_responses:
        items.append(
            _item(
                key=f"author-offer-response-{response.pk}",
                kind="cooperation_response",
                section="Сотрудничество",
                title="Новый отклик на предложение",
                text=f"{_display_name(response.respondent)}: {response.offer.title}",
                badge="Отклик",
                created_at=response.created_at,
                app_path="/cooperation",
                site_path=reverse("collaborations:offer_response_detail", args=[response.pk]),
                action_label="К отклику",
                accent="red",
            )
        )
    groups["cooperation"] += len(pending_offer_responses)

    pending_blogger_request_responses = (
        BloggerRequestResponse.objects.filter(
            request__blogger=user,
            status=BloggerRequestResponse.Status.PENDING,
        )
        .select_related("request", "responder", "book")
        .order_by("-created_at")[:20]
    )
    for response in pending_blogger_request_responses:
        items.append(
            _item(
                key=f"blogger-request-response-{response.pk}",
                kind="cooperation_response",
                section="Сотрудничество",
                title="Новый отклик на заявку",
                text=f"{_display_name(response.responder)}: {response.request.title}",
                badge="Отклик",
                created_at=response.created_at,
                app_path="/cooperation",
                site_path=reverse("collaborations:blogger_request_response_detail", args=[response.pk]),
                action_label="К отклику",
                accent="red",
            )
        )
    groups["cooperation"] += len(pending_blogger_request_responses)

    pending_partner_collaborations = Collaboration.objects.filter(
        partner=user,
        author_approved=True,
        partner_approved=False,
        status__in=[Collaboration.Status.NEGOTIATION, Collaboration.Status.ACTIVE],
    ).select_related("author", "offer", "request")[:20]
    for collaboration in pending_partner_collaborations:
        title = collaboration.offer.title if collaboration.offer else collaboration.request.title
        items.append(
            _item(
                key=f"partner-confirmation-{collaboration.pk}",
                kind="cooperation_confirmation",
                section="Сотрудничество",
                title="Автор ждет подтверждения",
                text=title,
                badge="Подтвердить",
                created_at=collaboration.updated_at,
                app_path="/cooperation",
                site_path=reverse("collaborations:collaboration_approval", args=[collaboration.pk]),
                action_label="Проверить",
                accent="red",
            )
        )
    groups["cooperation"] += len(pending_partner_collaborations)

    pending_author_collaborations = Collaboration.objects.filter(
        author=user,
        partner_approved=True,
        author_approved=False,
        status__in=[Collaboration.Status.NEGOTIATION, Collaboration.Status.ACTIVE],
    ).select_related("partner", "offer", "request")[:20]
    for collaboration in pending_author_collaborations:
        title = collaboration.offer.title if collaboration.offer else collaboration.request.title
        items.append(
            _item(
                key=f"author-confirmation-{collaboration.pk}",
                kind="cooperation_confirmation",
                section="Сотрудничество",
                title="Партнер ждет подтверждения",
                text=title,
                badge="Подтвердить",
                created_at=collaboration.updated_at,
                app_path="/cooperation",
                site_path=reverse("collaborations:collaboration_approval", args=[collaboration.pk]),
                action_label="Проверить",
                accent="red",
            )
        )
    groups["cooperation"] += len(pending_author_collaborations)

    pending_reading_participants = (
        ReadingParticipant.objects.filter(
            reading__creator=user,
            status=ReadingParticipant.Status.PENDING,
        )
        .select_related("reading", "user")
        .order_by("-joined_at")[:20]
    )
    for participant in pending_reading_participants:
        items.append(
            _item(
                key=f"reading-participant-{participant.pk}",
                kind="reading_participant",
                section="Совместные чтения",
                title="Новая заявка на участие",
                text=f"{_display_name(participant.user)}: {participant.reading.title}",
                badge="Заявка",
                created_at=participant.joined_at,
                app_path=f"/community/reading-clubs/{participant.reading.slug}",
                site_path=participant.reading.get_absolute_url(),
                action_label="К чтению",
                accent="green",
            )
        )
    groups["reading_clubs"] += len(pending_reading_participants)

    unread_offer_threads = (
        AuthorOfferResponse.objects.unread_for(user)
        .select_related("offer", "offer__author", "respondent")
        .order_by("-last_activity_at")[:20]
    )
    for response in unread_offer_threads:
        items.append(
            _item(
                key=f"author-offer-thread-{response.pk}",
                kind="cooperation_message",
                section="Сотрудничество",
                title="Новое сообщение в отклике",
                text=response.offer.title,
                badge="Сообщение",
                created_at=response.last_activity_at,
                app_path="/cooperation",
                site_path=reverse("collaborations:offer_response_detail", args=[response.pk]),
                action_label="Ответить",
                accent="red",
            )
        )
    groups["cooperation"] += len(unread_offer_threads)

    unread_blogger_request_threads = (
        BloggerRequestResponse.objects.unread_for(user)
        .select_related("request", "request__blogger", "responder", "book")
        .order_by("-last_activity_at")[:20]
    )
    for response in unread_blogger_request_threads:
        items.append(
            _item(
                key=f"blogger-request-thread-{response.pk}",
                kind="cooperation_message",
                section="Сотрудничество",
                title="Новое сообщение в отклике",
                text=response.request.title,
                badge="Сообщение",
                created_at=response.last_activity_at,
                app_path="/cooperation",
                site_path=reverse("collaborations:blogger_request_response_detail", args=[response.pk]),
                action_label="Ответить",
                accent="red",
            )
        )
    groups["cooperation"] += len(unread_blogger_request_threads)

    unread_collaborations = (
        Collaboration.objects.unread_for(user)
        .select_related("author", "partner", "offer", "request")
        .order_by("-last_activity_at")[:20]
    )
    for collaboration in unread_collaborations:
        title = collaboration.offer.title if collaboration.offer else collaboration.request.title
        items.append(
            _item(
                key=f"collaboration-thread-{collaboration.pk}",
                kind="cooperation_message",
                section="Сотрудничество",
                title="Новое сообщение по сотрудничеству",
                text=title,
                badge="Сообщение",
                created_at=collaboration.last_activity_at,
                app_path="/cooperation",
                site_path=reverse("collaborations:collaboration_detail", args=[collaboration.pk]),
                action_label="Открыть чат",
                accent="red",
            )
        )
    groups["cooperation"] += len(unread_collaborations)

    if include_informational:
        monthly_awards = (
            MonthlyChallenge.objects.filter(user=user, awarded_at__isnull=False)
            .order_by("-awarded_at", "-month")[:10]
        )
        for challenge in monthly_awards:
            is_new = bool(challenge.awarded_at and challenge.awarded_at >= recent_awards_since)
            award_url = build_monthly_challenge_award_url(
                challenge.kind,
                month=challenge.month,
                awarded=True,
            )
            items.append(
                _item(
                    key=f"monthly-award-{challenge.kind}-{challenge.month:%Y-%m}",
                    kind="monthly_award",
                    section="Мини-игры",
                    title="Выдана награда",
                    text=f"{MONTHLY_CHALLENGE_TITLES.get(challenge.kind, 'Ежемесячная игра')} за {month_display(challenge.month)}",
                    badge="Награда",
                    created_at=challenge.awarded_at,
                    app_path=f"/games/monthly-{challenge.kind}",
                    site_path=f"/games/monthly-{challenge.kind}/",
                    action_label="Посмотреть",
                    unread=is_new,
                    image_url=award_url,
                    accent="gold",
                )
            )
            if is_new:
                groups["awards"] += 1

        current_month = timezone.localdate().replace(day=1)
        forgotten_selection = (
            ForgottenBookEntry.objects.filter(
                user=user,
                selected_month=current_month,
                selected_at__isnull=False,
            )
            .select_related("book")
            .order_by("-selected_at")
            .first()
        )
        if forgotten_selection:
            items.append(
                _item(
                    key=f"forgotten-selection-{forgotten_selection.pk}",
                    kind="forgotten_month_selection",
                    section="Игры",
                    title="Выбрана книга месяца",
                    text=getattr(forgotten_selection.book, "title", "12 забытых книг"),
                    badge="12 забытых книг",
                    created_at=forgotten_selection.selected_at,
                    app_path="/games/forgotten-books-12",
                    site_path="/games/forgotten-books/",
                    action_label="К игре",
                    unread=True,
                    accent="orange",
                )
            )
            groups["games"] += 1

    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    unread_count = sum(1 for item in items if item.get("unread"))
    return {
        "unread_count": unread_count,
        "items": items[:60],
        "groups": groups,
    }
