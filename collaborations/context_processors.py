from __future__ import annotations

from reading_clubs.models import ReadingParticipant
from reading_clubs.services import get_unread_discussion_total

from games.models import BookExchangeOffer

from .models import AuthorOfferResponse, Collaboration


def collaboration_notifications(request):
    user = getattr(request, "user", None)
    notifications = {
        "pending_offer_responses": 0,
        "pending_partner_confirmations": 0,
        "pending_author_confirmations": 0,
        "unread_offer_threads": 0,
        "unread_collaboration_threads": 0,
        "unread_reading_topics": 0,
        "total": 0,
        "pending_reading_participants": 0,
        "pending_game_offers": 0,
    }

    if user is None or not getattr(user, "is_authenticated", False):
        return {"collaboration_notifications": notifications}

    pending_offer_responses = AuthorOfferResponse.objects.filter(
        offer__author=user,
        status=AuthorOfferResponse.Status.PENDING,
    ).count()

    awaiting_partner = Collaboration.objects.filter(
        partner=user,
        author_approved=True,
        partner_approved=False,
        status__in=[Collaboration.Status.NEGOTIATION, Collaboration.Status.ACTIVE],
    ).count()

    awaiting_author = Collaboration.objects.filter(
        author=user,
        partner_approved=True,
        author_approved=False,
        status__in=[Collaboration.Status.NEGOTIATION, Collaboration.Status.ACTIVE],
    ).count()

    unread_offer_threads = AuthorOfferResponse.objects.unread_for(user).count()
    unread_collaborations = Collaboration.objects.unread_for(user).count()

    pending_reading_participants = ReadingParticipant.objects.filter(
        reading__creator=user,
        status=ReadingParticipant.Status.PENDING,
    ).count()

    pending_game_offers = BookExchangeOffer.objects.filter(
        challenge__user=user,
        status=BookExchangeOffer.Status.PENDING,
    ).count()

    unread_reading_topics = get_unread_discussion_total(user)

    notifications.update(
        {
            "pending_offer_responses": pending_offer_responses,
            "pending_partner_confirmations": awaiting_partner,
            "pending_author_confirmations": awaiting_author,
            "unread_offer_threads": unread_offer_threads,
            "unread_collaboration_threads": unread_collaborations,
            "unread_reading_topics": unread_reading_topics,
            "pending_reading_participants": pending_reading_participants,
            "pending_game_offers": pending_game_offers,
        }
    )
    notifications["total"] = (
        pending_offer_responses
        + awaiting_partner
        + awaiting_author
        + unread_offer_threads
        + unread_collaborations
        + unread_reading_topics
        + pending_reading_participants
        + pending_game_offers
    )
    return {"collaboration_notifications": notifications}