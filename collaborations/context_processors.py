from __future__ import annotations

from .models import AuthorOfferResponse, Collaboration


def collaboration_notifications(request):
    user = getattr(request, "user", None)
    notifications = {
        "pending_offer_responses": 0,
        "pending_partner_confirmations": 0,
        "pending_author_confirmations": 0,
        "total": 0,
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

    notifications.update(
        {
            "pending_offer_responses": pending_offer_responses,
            "pending_partner_confirmations": awaiting_partner,
            "pending_author_confirmations": awaiting_author,
        }
    )
    notifications["total"] = (
        pending_offer_responses + awaiting_partner + awaiting_author
    )
    return {"collaboration_notifications": notifications}