from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable
from urllib.parse import urlparse

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.encoding import force_str
from rest_framework import parsers, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.services import InsufficientCoinsError, charge_feature_access
from books.models import Book, Genre
from collaborations.models import (
    AuthorOffer,
    AuthorOfferResponse,
    AuthorOfferResponseComment,
    BloggerRequest,
    BloggerRequestResponse,
    BloggerRequestResponseComment,
    Collaboration,
    CollaborationMessage,
    CollaborationStatusUpdate,
    ReviewPlatform,
)


def _label(value: Any) -> str:
    return force_str(value) if value is not None else ""


def _absolute_url(request, value: str | None) -> str:
    if not value:
        return ""
    value = str(value)
    if value.startswith(("http://", "https://", "//")):
        return value
    return request.build_absolute_uri(value)


def _file_url(request, file_value) -> str:
    if not file_value:
        return ""
    try:
        return _absolute_url(request, file_value.url)
    except (AttributeError, ValueError):
        return ""


def _file_name(file_value) -> str:
    if not file_value:
        return ""
    try:
        return str(file_value.name).rsplit("/", 1)[-1]
    except (AttributeError, ValueError):
        return ""


def _normalize_review_link(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        raw = f"https:{raw}"
    elif not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"

    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or any(char.isspace() for char in raw):
        return ""
    return raw


def _parse_review_links(value: Any) -> list[str] | None:
    if isinstance(value, str):
        parts = value.replace(";", "\n").splitlines()
    elif isinstance(value, Iterable):
        parts = list(value)
    else:
        parts = [value]

    links: list[str] = []
    for item in parts:
        if not str(item or "").strip():
            continue
        normalized = _normalize_review_link(item)
        if not normalized:
            return None
        if normalized not in links:
            links.append(normalized)
    return links


def _display_datetime(value: datetime | None) -> tuple[str | None, str]:
    if not value:
        return None, ""
    local_value = timezone.localtime(value)
    return local_value.isoformat(), local_value.strftime("%d.%m.%Y, %H:%M")


def _display_date(value: date | None) -> tuple[str | None, str]:
    if not value:
        return None, ""
    return value.isoformat(), value.strftime("%d.%m.%Y")


def _choice_payload(choices: Iterable[tuple[str, Any]]) -> list[dict[str, str]]:
    return [{"value": value, "label": _label(label)} for value, label in choices]


def _parse_ids(value: Any) -> list[int]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in value.replace(";", ",").split(",")]
    elif isinstance(value, Iterable):
        parts = list(value)
    else:
        parts = [value]

    ids: list[int] = []
    for item in parts:
        try:
            item_id = int(item)
        except (TypeError, ValueError):
            continue
        if item_id not in ids:
            ids.append(item_id)
    return ids


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "да"}


def _future_or_today(value: Any) -> date | None:
    parsed = value if isinstance(value, date) else parse_date(str(value or ""))
    if not parsed:
        return None
    if parsed < timezone.localdate():
        return None
    return parsed


def _json_error(message: str, *, code: int = status.HTTP_400_BAD_REQUEST) -> Response:
    return Response({"detail": message}, status=code)


def _profile(user):
    return getattr(user, "profile", None)


def _model_has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)
    except Exception:
        return False
    return True


def _safe_display(instance, method_name: str) -> str:
    method = getattr(instance, method_name, None)
    if callable(method):
        return _label(method())
    return ""


def _safe_unread_count(manager, user) -> int:
    unread_for = getattr(manager, "unread_for", None)
    if not callable(unread_for):
        return 0
    return unread_for(user).count()


def _safe_filtered_unread_count(manager, user, *filters, **kwargs) -> int:
    unread_for = getattr(manager, "unread_for", None)
    if not callable(unread_for):
        return 0
    return unread_for(user).filter(*filters, **kwargs).count()


def _safe_has_unread(instance, user) -> bool:
    has_unread_for = getattr(instance, "has_unread_for", None)
    if not callable(has_unread_for):
        return False
    return bool(has_unread_for(user))


PUBLIC_BOOK_FILTER = {
    "book__visibility": Book.Visibility.PUBLIC,
    "book__is_hidden_by_admin": False,
}
PUBLIC_OFFER_BOOK_FILTER = {
    "offer__book__visibility": Book.Visibility.PUBLIC,
    "offer__book__is_hidden_by_admin": False,
}


def _public_optional_book_q(prefix: str = "book") -> Q:
    return Q(**{f"{prefix}__isnull": True}) | Q(
        **{
            f"{prefix}__visibility": Book.Visibility.PUBLIC,
            f"{prefix}__is_hidden_by_admin": False,
        }
    )


def _public_optional_offer_book_q() -> Q:
    return Q(offer__isnull=True) | Q(**PUBLIC_OFFER_BOOK_FILTER)


def _user_is_author(user) -> bool:
    profile = _profile(user)
    return bool(profile and profile.is_author)


def _user_is_blogger(user) -> bool:
    profile = _profile(user)
    return bool(profile and profile.is_blogger)


def _can_respond_to_offer(offer: AuthorOffer, user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if offer.author_id == user.id:
        return False
    return bool(offer.allow_regular_users or _user_is_blogger(user))


def _charge_profile(user, description: str):
    profile = _profile(user)
    if profile is None:
        raise InsufficientCoinsError("Профиль пользователя не найден.")
    return charge_feature_access(profile, description=description)


def _user_payload(request, user) -> dict[str, Any] | None:
    if not user:
        return None

    profile = _profile(user)
    avatar_url = _file_url(request, getattr(profile, "avatar", None)) if profile else ""
    name = user.get_full_name() or user.username
    return {
        "id": user.id,
        "name": name,
        "username": user.username,
        "avatar_url": avatar_url,
        "is_author": _user_is_author(user),
        "is_blogger": _user_is_blogger(user),
        "profile_url": f"/profile/{user.username}",
    }


def _book_payload(request, book: Book | None) -> dict[str, Any] | None:
    if not book:
        return None
    cover_url = ""
    if hasattr(book, "get_original_cover_url"):
        cover_url = book.get_original_cover_url()
    elif hasattr(book, "get_cover_url"):
        cover_url = book.get_cover_url()

    return {
        "id": book.id,
        "title": book.title,
        "authors": list(book.authors.order_by("name").values_list("name", flat=True)[:4]),
        "cover_url": _absolute_url(request, cover_url),
        "detail_url": f"/books/{book.id}",
    }


def _option_payload(item) -> dict[str, Any]:
    return {"id": item.id, "name": item.name}


def _response_comments(request, comments) -> list[dict[str, Any]]:
    rows = []
    for comment in comments:
        created_at, created_label = _display_datetime(comment.created_at)
        rows.append(
            {
                "id": comment.id,
                "author": _user_payload(request, comment.author),
                "text": comment.text,
                "created_at": created_at,
                "created_label": created_label,
            }
        )
    return rows


def _serialize_author_offer(
    request,
    offer: AuthorOffer,
    *,
    include_response: bool = True,
) -> dict[str, Any]:
    user = request.user
    existing_response = None
    if include_response and getattr(user, "is_authenticated", False):
        response = getattr(offer, "_current_user_response", None)
        if response is None:
            response = (
                AuthorOfferResponse.objects.filter(offer=offer, respondent=user)
                .select_related("respondent", "respondent__profile", "offer", "offer__book")
                .prefetch_related("comments__author", "comments__author__profile")
                .first()
            )
        if response:
            existing_response = _serialize_response(request, response, "offer", compact_source=True)

    return {
        "id": offer.id,
        "title": offer.title,
        "offered_format": offer.offered_format,
        "offered_format_label": _label(offer.get_offered_format_display()),
        "synopsis": offer.synopsis,
        "review_requirements": offer.review_requirements,
        "text_review_length": offer.text_review_length,
        "expected_platforms": [_option_payload(item) for item in offer.expected_platforms.all()],
        "video_review_type": offer.video_review_type,
        "video_review_type_label": _label(offer.get_video_review_type_display()),
        "video_requires_unboxing": offer.video_requires_unboxing,
        "video_requires_aesthetics": offer.video_requires_aesthetics,
        "video_requires_review": offer.video_requires_review,
        "considers_paid_collaboration": offer.considers_paid_collaboration,
        "allow_regular_users": offer.allow_regular_users,
        "book": _book_payload(request, offer.book),
        "author": _user_payload(request, offer.author),
        "responses_count": getattr(offer, "responses_total", None)
        if getattr(offer, "responses_total", None) is not None
        else offer.responses.count(),
        "can_respond": _can_respond_to_offer(offer, user),
        "existing_response": existing_response,
        "created_at": offer.created_at.isoformat(),
    }


def _can_respond_to_blogger_request(item: BloggerRequest, user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if item.blogger_id == user.id:
        return False
    if item.target_audience == BloggerRequest.TargetAudience.AUTHORS:
        return _user_is_author(user)
    return _user_is_blogger(user)


def _serialize_blogger_request(
    request,
    item: BloggerRequest,
    *,
    include_response: bool = True,
) -> dict[str, Any]:
    user = request.user
    existing_response = None
    if include_response and getattr(user, "is_authenticated", False):
        response = getattr(item, "_current_user_response", None)
        if response is None:
            response = (
                BloggerRequestResponse.objects.filter(request=item, responder=user)
                .filter(_public_optional_book_q("book"))
                .select_related("responder", "responder__profile", "book", "request")
                .prefetch_related("book__authors", "comments__author", "comments__author__profile")
                .first()
            )
        if response:
            existing_response = _serialize_response(request, response, "request", compact_source=True)

    return {
        "id": item.id,
        "title": item.title,
        "blogger": _user_payload(request, item.blogger),
        "preferred_genres": [_option_payload(genre) for genre in item.preferred_genres.all()],
        "accepts_paper": item.accepts_paper,
        "accepts_electronic": item.accepts_electronic,
        "accepts_audio": item.accepts_audio,
        "review_formats": [_option_payload(platform) for platform in item.review_formats.all()],
        "review_platform_links": item.review_platform_links,
        "additional_info": item.additional_info,
        "collaboration_type": item.collaboration_type,
        "collaboration_type_label": _safe_display(item, "get_collaboration_type_display"),
        "collaboration_terms": item.collaboration_terms,
        "target_audience": item.target_audience,
        "target_audience_label": _safe_display(item, "get_target_audience_display"),
        "blogger_collaboration_platform": getattr(item, "blogger_collaboration_platform_id", None),
        "blogger_collaboration_platform_other": getattr(item, "blogger_collaboration_platform_other", ""),
        "blogger_collaboration_goal": getattr(item, "blogger_collaboration_goal", ""),
        "blogger_collaboration_goal_label": _safe_display(item, "get_blogger_collaboration_goal_display"),
        "blogger_collaboration_goal_other": getattr(item, "blogger_collaboration_goal_other", ""),
        "responses_count": getattr(item, "responses_total", None)
        if getattr(item, "responses_total", None) is not None
        else item.responses.count(),
        "can_respond": _can_respond_to_blogger_request(item, user),
        "existing_response": existing_response,
        "created_at": item.created_at.isoformat(),
    }


def _serialize_response(
    request,
    response: AuthorOfferResponse | BloggerRequestResponse,
    kind: str,
    *,
    compact_source: bool = False,
) -> dict[str, Any]:
    user = request.user
    if kind == "offer":
        source_owner_id = response.offer.author_id
        respondent = response.respondent
        comments = response.comments.select_related("author", "author__profile").order_by("created_at")
        offer = None if compact_source else _serialize_author_offer(request, response.offer, include_response=False)
        blogger_request = None
        responder_type = "blogger" if _user_is_blogger(respondent) else "reader"
        book = response.offer.book
    else:
        source_owner_id = response.request.blogger_id
        respondent = response.responder
        comments = response.comments.select_related("author", "author__profile").order_by("created_at")
        offer = None
        blogger_request = None if compact_source else _serialize_blogger_request(request, response.request, include_response=False)
        responder_type = response.responder_type
        book = response.book

    return {
        "id": response.id,
        "kind": kind,
        "status": response.status,
        "status_label": _label(response.get_status_display()),
        "respondent": _user_payload(request, respondent),
        "responder_type": responder_type,
        "platform_links": getattr(response, "platform_links", ""),
        "platform_link": getattr(response, "platform_link", ""),
        "message": response.message,
        "book": _book_payload(request, book),
        "offer": offer,
        "request": blogger_request,
        "comments": _response_comments(request, comments),
        "can_accept": user.id == source_owner_id and response.status == response.Status.PENDING,
        "can_decline": user.id == source_owner_id and response.status == response.Status.PENDING,
        "can_withdraw": user.id == respondent.id and response.status == response.Status.PENDING,
        "can_comment": response.is_participant(user) and response.allows_discussion(),
        "has_unread": _safe_has_unread(response, user),
        "created_at": response.created_at.isoformat(),
    }


def _collaboration_book(collaboration: Collaboration) -> Book | None:
    if collaboration.offer and collaboration.offer.book_id:
        return collaboration.offer.book
    if collaboration.request:
        response = (
            collaboration.request.responses.filter(
                responder=collaboration.author,
                status=BloggerRequestResponse.Status.ACCEPTED,
            )
            .select_related("book")
            .first()
        )
        if response:
            return response.book
    return None


def _serialize_message(request, message: CollaborationMessage) -> dict[str, Any]:
    created_at, created_label = _display_datetime(message.created_at)
    return {
        "id": message.id,
        "author": _user_payload(request, message.author),
        "text": message.text,
        "epub_url": _file_url(request, message.epub_file),
        "epub_name": _file_name(message.epub_file),
        "created_at": created_at,
        "created_label": created_label,
    }


def _serialize_collaboration(request, collaboration: Collaboration) -> dict[str, Any]:
    user = request.user
    deadline, deadline_label = _display_date(collaboration.deadline)
    review_links = collaboration.get_review_links()
    book = _collaboration_book(collaboration)

    source_title = "Сотрудничество"
    if collaboration.offer:
        source_title = collaboration.offer.title
    elif collaboration.request:
        source_title = collaboration.request.title

    return {
        "id": collaboration.id,
        "source_type": "offer" if collaboration.offer_id else "request",
        "title": source_title,
        "status": collaboration.status,
        "status_label": _label(collaboration.get_status_display()),
        "deadline": deadline,
        "deadline_label": deadline_label,
        "author_approved": collaboration.author_approved,
        "partner_approved": collaboration.partner_approved,
        "review_links": review_links,
        "author": _user_payload(request, collaboration.author),
        "partner": _user_payload(request, collaboration.partner),
        "book": _book_payload(request, book),
        "offer": _serialize_author_offer(request, collaboration.offer, include_response=False) if collaboration.offer else None,
        "request": _serialize_blogger_request(request, collaboration.request, include_response=False) if collaboration.request else None,
        "messages": [_serialize_message(request, message) for message in collaboration.messages.select_related("author", "author__profile").order_by("created_at")[:60]],
        "needs_attention": collaboration.needs_attention,
        "waiting_for_me": (user.id == collaboration.author_id and collaboration.waiting_for_author_confirmation)
        or (user.id == collaboration.partner_id and collaboration.waiting_for_partner_confirmation),
        "can_message": collaboration.is_participant(user) and collaboration.allows_discussion(),
        "can_upload_epub": user.id == collaboration.author_id and collaboration.allows_discussion(),
        "can_approve": collaboration.is_participant(user)
        and collaboration.status == Collaboration.Status.NEGOTIATION
        and (
            (user.id == collaboration.author_id and not collaboration.author_approved)
            or (user.id == collaboration.partner_id and not collaboration.partner_approved)
        ),
        "can_submit_review_links": user.id == collaboration.partner_id
        and collaboration.status in {Collaboration.Status.NEGOTIATION, Collaboration.Status.ACTIVE},
        "can_confirm_completion": user.id == collaboration.author_id
        and bool(review_links)
        and collaboration.status in {Collaboration.Status.ACTIVE, Collaboration.Status.NEGOTIATION},
        "can_mark_failed": user.id == collaboration.author_id
        and collaboration.status in {Collaboration.Status.ACTIVE, Collaboration.Status.NEGOTIATION},
        "can_change_status": user.id == collaboration.author_id
        and collaboration.status in {Collaboration.Status.NEGOTIATION, Collaboration.Status.ACTIVE},
        "has_unread": _safe_has_unread(collaboration, user),
    }


def _overview_payload(request, *, query: str = "", audience: str = "") -> dict[str, Any]:
    user = request.user
    offers_qs = (
        AuthorOffer.objects.filter(is_active=True)
        .filter(**PUBLIC_BOOK_FILTER)
        .select_related("author", "author__profile", "book")
        .prefetch_related("expected_platforms", "book__authors")
        .order_by("-created_at")
    )
    requests_qs = (
        BloggerRequest.objects.filter(is_active=True)
        .select_related("blogger", "blogger__profile")
        .prefetch_related("preferred_genres", "review_formats")
        .order_by("-created_at")
    )

    if query:
        offers_qs = offers_qs.filter(Q(title__icontains=query) | Q(synopsis__icontains=query) | Q(review_requirements__icontains=query))
        requests_qs = requests_qs.filter(Q(title__icontains=query) | Q(additional_info__icontains=query) | Q(collaboration_terms__icontains=query))

    if audience in {"authors", "bloggers"}:
        requests_qs = requests_qs.filter(target_audience=audience)

    offers = list(offers_qs[:40])
    blogger_requests = list(requests_qs[:40])

    if getattr(user, "is_authenticated", False):
        offer_responses = {
            item.offer_id: item
            for item in AuthorOfferResponse.objects.filter(offer__in=offers, respondent=user)
            .select_related("respondent", "respondent__profile", "offer", "offer__book")
            .prefetch_related("comments__author", "comments__author__profile")
        }
        request_responses = {
            item.request_id: item
            for item in BloggerRequestResponse.objects.filter(request__in=blogger_requests, responder=user)
            .filter(_public_optional_book_q("book"))
            .select_related("responder", "responder__profile", "request", "book")
            .prefetch_related("book__authors", "comments__author", "comments__author__profile")
        }
        for offer in offers:
            offer._current_user_response = offer_responses.get(offer.id)
        for item in blogger_requests:
            item._current_user_response = request_responses.get(item.id)

    incoming_offer_responses = AuthorOfferResponse.objects.none()
    incoming_request_responses = BloggerRequestResponse.objects.none()
    my_offer_responses = AuthorOfferResponse.objects.none()
    my_request_responses = BloggerRequestResponse.objects.none()
    collaborations_qs = Collaboration.objects.none()
    author_books_qs = Book.objects.none()
    collaborations_count = 0

    if getattr(user, "is_authenticated", False):
        incoming_offer_responses = list(
            AuthorOfferResponse.objects.filter(offer__author=user)
            .filter(**PUBLIC_OFFER_BOOK_FILTER)
            .select_related("respondent", "respondent__profile", "offer", "offer__author", "offer__author__profile", "offer__book")
            .prefetch_related("offer__book__authors", "comments__author", "comments__author__profile")
            .order_by("-updated_at")[:30]
        )
        incoming_request_responses = list(
            BloggerRequestResponse.objects.filter(request__blogger=user)
            .filter(_public_optional_book_q("book"))
            .select_related("responder", "responder__profile", "request", "request__blogger", "request__blogger__profile", "book")
            .prefetch_related("book__authors", "comments__author", "comments__author__profile")
            .order_by("-updated_at")[:30]
        )
        my_offer_responses = list(
            AuthorOfferResponse.objects.filter(respondent=user)
            .filter(**PUBLIC_OFFER_BOOK_FILTER)
            .select_related("respondent", "respondent__profile", "offer", "offer__author", "offer__author__profile", "offer__book")
            .prefetch_related("offer__book__authors", "comments__author", "comments__author__profile")
            .order_by("-updated_at")[:30]
        )
        my_request_responses = list(
            BloggerRequestResponse.objects.filter(responder=user)
            .filter(_public_optional_book_q("book"))
            .select_related("responder", "responder__profile", "request", "request__blogger", "request__blogger__profile", "book")
            .prefetch_related("book__authors", "comments__author", "comments__author__profile")
            .order_by("-updated_at")[:30]
        )
        collaborations_base_qs = Collaboration.objects.filter(Q(author=user) | Q(partner=user)).filter(
            _public_optional_offer_book_q()
        )
        collaborations_count = collaborations_base_qs.count()
        collaborations_qs = list(
            collaborations_base_qs
            .select_related(
                "author",
                "author__profile",
                "partner",
                "partner__profile",
                "offer",
                "offer__book",
                "offer__author",
                "request",
                "request__blogger",
            )
            .prefetch_related("offer__book__authors", "messages__author", "messages__author__profile")
            .order_by("-updated_at")[:30]
        )
        author_books_qs = list(Book.objects.public().filter(contributors=user).prefetch_related("authors").order_by("-created_at")[:80])

    incoming_responses_payload = [
        *[_serialize_response(request, item, "offer") for item in incoming_offer_responses],
        *[_serialize_response(request, item, "request") for item in incoming_request_responses],
    ]
    my_responses_payload = [
        *[_serialize_response(request, item, "offer") for item in my_offer_responses],
        *[_serialize_response(request, item, "request") for item in my_request_responses],
    ]
    responses = [*incoming_responses_payload, *my_responses_payload]
    incoming_response_count = len(incoming_offer_responses) + len(incoming_request_responses)
    my_response_count = len(my_offer_responses) + len(my_request_responses)
    seen_response_keys = set()
    unique_responses = []
    for item in responses:
        key = (item["kind"], item["id"])
        if key not in seen_response_keys:
            unique_responses.append(item)
            seen_response_keys.add(key)

    unread_count = 0
    if getattr(user, "is_authenticated", False):
        unread_count = (
            _safe_filtered_unread_count(AuthorOfferResponse.objects, user, **PUBLIC_OFFER_BOOK_FILTER)
            + _safe_filtered_unread_count(BloggerRequestResponse.objects, user, _public_optional_book_q("book"))
            + _safe_filtered_unread_count(Collaboration.objects, user, _public_optional_offer_book_q())
        )

    return {
        "profile": {
            "user": _user_payload(request, user),
            "is_author": _user_is_author(user),
            "is_blogger": _user_is_blogger(user),
            "can_create_offer": _user_is_author(user),
            "can_create_blogger_request": _user_is_blogger(user),
        },
        "counters": {
            "offers": offers_qs.count(),
            "blogger_requests": requests_qs.count(),
            "incoming_responses": incoming_response_count,
            "my_responses": my_response_count,
            "collaborations": collaborations_count,
            "unread": unread_count,
        },
        "offers": [_serialize_author_offer(request, offer) for offer in offers],
        "blogger_requests": [_serialize_blogger_request(request, item) for item in blogger_requests],
        "incoming_responses": incoming_responses_payload[:60],
        "my_responses": my_responses_payload[:60],
        "responses": unique_responses[:60],
        "collaborations": [_serialize_collaboration(request, item) for item in collaborations_qs],
        "platforms": [_option_payload(item) for item in ReviewPlatform.objects.order_by("name")],
        "genres": [_option_payload(item) for item in Genre.objects.order_by("name")],
        "author_books": [_book_payload(request, book) for book in author_books_qs],
        "choices": {
            "book_formats": _choice_payload(AuthorOffer.BookFormat.choices),
            "offered_formats": _choice_payload(AuthorOffer.BookFormat.choices),
            "video_review_types": _choice_payload(AuthorOffer.VideoReviewType.choices),
            "collaboration_types": _choice_payload(BloggerRequest.CollaborationType.choices),
            "target_audiences": _choice_payload(BloggerRequest.TargetAudience.choices),
            "blogger_goals": _choice_payload(getattr(getattr(BloggerRequest, "BloggerCollaborationGoal", None), "choices", [])),
            "response_statuses": _choice_payload(AuthorOfferResponse.Status.choices),
            "collaboration_statuses": _choice_payload(Collaboration.Status.choices),
        },
    }


class VKAppCooperationOverviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(
            _overview_payload(
                request,
                query=str(request.query_params.get("q", "")).strip(),
                audience=str(request.query_params.get("audience", "")).strip(),
            )
        )


class VKAppCooperationOfferCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        user = request.user
        if not _user_is_author(user):
            return _json_error("Создать предложение может только автор.", code=status.HTTP_403_FORBIDDEN)

        data = request.data
        title = str(data.get("title", "")).strip()
        review_requirements = str(data.get("review_requirements", "")).strip()
        if not review_requirements:
            return _json_error("Заполните требования к отзыву.")

        book_id = data.get("book")
        if not book_id:
            return _json_error("Выберите книгу из списка ваших авторских книг.")
        book = get_object_or_404(Book.objects.public(), pk=book_id, contributors=user)
        if not title:
            title = book.title

        try:
            _charge_profile(user, "Публикация предложения о сотрудничестве")
        except InsufficientCoinsError as exc:
            return _json_error(str(exc), code=status.HTTP_402_PAYMENT_REQUIRED)

        offer = AuthorOffer.objects.create(
            author=user,
            title=title,
            offered_format=data.get("offered_format") or AuthorOffer.BookFormat.ELECTRONIC,
            synopsis=str(data.get("synopsis", "")).strip(),
            review_requirements=review_requirements,
            text_review_length=int(data.get("text_review_length") or 0),
            video_review_type=data.get("video_review_type") or AuthorOffer.VideoReviewType.NONE,
            book=book,
            video_requires_unboxing=_parse_bool(data.get("video_requires_unboxing")),
            video_requires_aesthetics=_parse_bool(data.get("video_requires_aesthetics")),
            video_requires_review=_parse_bool(data.get("video_requires_review", True)),
            considers_paid_collaboration=_parse_bool(data.get("considers_paid_collaboration")),
            allow_regular_users=_parse_bool(data.get("allow_regular_users")),
        )
        offer.expected_platforms.set(ReviewPlatform.objects.filter(pk__in=_parse_ids(data.get("expected_platforms"))))
        return Response(_overview_payload(request))


class VKAppCooperationBloggerRequestCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        user = request.user
        if not _user_is_blogger(user):
            return _json_error("Создать заявку может блогер.", code=status.HTTP_403_FORBIDDEN)

        data = request.data
        title = str(data.get("title", "")).strip()
        if not title:
            return _json_error("Заполните название заявки.")

        target_audience = data.get("target_audience") or BloggerRequest.TargetAudience.AUTHORS
        has_platform_field = _model_has_field(BloggerRequest, "blogger_collaboration_platform")
        has_platform_other_field = _model_has_field(BloggerRequest, "blogger_collaboration_platform_other")
        has_goal_field = _model_has_field(BloggerRequest, "blogger_collaboration_goal")
        has_goal_other_field = _model_has_field(BloggerRequest, "blogger_collaboration_goal_other")
        platform_id = data.get("blogger_collaboration_platform") or None
        platform = ReviewPlatform.objects.filter(pk=platform_id).first() if platform_id and has_platform_field else None

        if target_audience == BloggerRequest.TargetAudience.BLOGGERS:
            has_platform = bool(platform or str(data.get("blogger_collaboration_platform_other", "")).strip())
            has_goal = bool(data.get("blogger_collaboration_goal")) if has_goal_field else True
            if not has_platform or not has_goal:
                return _json_error("Для заявки блогерам укажите площадку и цель проекта.")

        try:
            _charge_profile(user, "Публикация заявки на сотрудничество")
        except InsufficientCoinsError as exc:
            return _json_error(str(exc), code=status.HTTP_402_PAYMENT_REQUIRED)

        create_kwargs = {
            "blogger": user,
            "title": title,
            "accepts_paper": _parse_bool(data.get("accepts_paper", True)),
            "accepts_electronic": _parse_bool(data.get("accepts_electronic", True)),
            "accepts_audio": _parse_bool(data.get("accepts_audio")),
            "review_platform_links": str(data.get("review_platform_links", "")).strip(),
            "additional_info": str(data.get("additional_info", "")).strip(),
            "collaboration_type": data.get("collaboration_type") or BloggerRequest.CollaborationType.BARTER,
            "collaboration_terms": str(data.get("collaboration_terms", "")).strip(),
            "target_audience": target_audience,
        }
        if has_platform_field:
            create_kwargs["blogger_collaboration_platform"] = platform
        if has_platform_other_field:
            create_kwargs["blogger_collaboration_platform_other"] = str(data.get("blogger_collaboration_platform_other", "")).strip()
        if has_goal_field:
            goal_choices = getattr(getattr(BloggerRequest, "BloggerCollaborationGoal", None), "choices", [])
            first_goal = goal_choices[0][0] if goal_choices else ""
            create_kwargs["blogger_collaboration_goal"] = data.get("blogger_collaboration_goal") or first_goal
        if has_goal_other_field:
            create_kwargs["blogger_collaboration_goal_other"] = str(data.get("blogger_collaboration_goal_other", "")).strip()

        item = BloggerRequest.objects.create(**create_kwargs)
        item.preferred_genres.set(Genre.objects.filter(pk__in=_parse_ids(data.get("preferred_genres"))))
        item.review_formats.set(ReviewPlatform.objects.filter(pk__in=_parse_ids(data.get("review_formats"))))
        return Response(_overview_payload(request))


class VKAppCooperationOfferRespondView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk: int):
        offer = get_object_or_404(
            AuthorOffer.objects.select_related("author").filter(**PUBLIC_BOOK_FILTER),
            pk=pk,
            is_active=True,
        )
        if not _can_respond_to_offer(offer, request.user):
            return _json_error("Вы не можете откликнуться на это предложение.", code=status.HTTP_403_FORBIDDEN)
        response, _created = AuthorOfferResponse.objects.get_or_create(offer=offer, respondent=request.user)
        response.platform_links = str(request.data.get("platform_links", "")).strip()
        response.message = str(request.data.get("message", "")).strip()
        response.status = AuthorOfferResponse.Status.PENDING
        response.save(update_fields=["platform_links", "message", "status", "updated_at"])
        response.register_activity(request.user)
        return Response(_overview_payload(request))


class VKAppCooperationBloggerRequestRespondView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk: int):
        item = get_object_or_404(BloggerRequest.objects.select_related("blogger"), pk=pk, is_active=True)
        if not _can_respond_to_blogger_request(item, request.user):
            return _json_error("Вы не можете откликнуться на эту заявку.", code=status.HTTP_403_FORBIDDEN)

        book = None
        responder_type = BloggerRequestResponse.ResponderType.BLOGGER
        platform_link = str(request.data.get("platform_link", "")).strip()
        if item.target_audience == BloggerRequest.TargetAudience.AUTHORS:
            responder_type = BloggerRequestResponse.ResponderType.AUTHOR
            book_id = request.data.get("book")
            if not book_id:
                return _json_error("Выберите книгу для предложения.")
            book = get_object_or_404(Book.objects.public(), pk=book_id, contributors=request.user)
        elif not platform_link:
            return _json_error("Укажите ссылку на площадку.")

        response, _created = BloggerRequestResponse.objects.get_or_create(request=item, responder=request.user)
        response.responder_type = responder_type
        response.message = str(request.data.get("message", "")).strip()
        response.book = book
        response.platform_link = platform_link
        response.status = BloggerRequestResponse.Status.PENDING
        response.save(update_fields=["responder_type", "message", "book", "platform_link", "status", "updated_at"])
        response.register_activity(request.user)
        return Response(_overview_payload(request))


def _response_for_kind(kind: str, pk: int):
    if kind == "offer":
        return get_object_or_404(
            AuthorOfferResponse.objects.select_related("offer", "offer__author", "respondent").filter(
                **PUBLIC_OFFER_BOOK_FILTER
            ),
            pk=pk,
        )
    if kind == "request":
        return get_object_or_404(
            BloggerRequestResponse.objects.select_related("request", "request__blogger", "responder", "book").filter(
                _public_optional_book_q("book")
            ),
            pk=pk,
        )
    return None


class VKAppCooperationResponseAcceptView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, kind: str, pk: int):
        response = _response_for_kind(kind, pk)
        if response is None:
            return _json_error("Отклик не найден.", code=status.HTTP_404_NOT_FOUND)

        deadline = _future_or_today(request.data.get("deadline"))
        if deadline is None:
            return _json_error("Укажите дедлайн не раньше сегодняшней даты.")

        user = request.user
        if kind == "offer":
            if response.offer.author_id != user.id:
                return _json_error("Принять отклик может только автор предложения.", code=status.HTTP_403_FORBIDDEN)
            collaboration, _created = Collaboration.objects.update_or_create(
                offer=response.offer,
                partner=response.respondent,
                defaults={
                    "author": response.offer.author,
                    "deadline": deadline,
                    "status": Collaboration.Status.NEGOTIATION,
                    "author_approved": True,
                    "partner_approved": False,
                    "author_confirmed": False,
                    "partner_confirmed": False,
                    "review_links": "",
                },
            )
        else:
            if response.request.blogger_id != user.id:
                return _json_error("Принять отклик может только автор заявки.", code=status.HTTP_403_FORBIDDEN)
            collaboration, _created = Collaboration.objects.update_or_create(
                request=response.request,
                author=response.responder,
                defaults={
                    "partner": response.request.blogger,
                    "deadline": deadline,
                    "status": Collaboration.Status.NEGOTIATION,
                    "author_approved": False,
                    "partner_approved": True,
                    "author_confirmed": False,
                    "partner_confirmed": False,
                    "review_links": "",
                },
            )

        response.status = response.Status.ACCEPTED
        response.save(update_fields=["status", "updated_at"])
        response.move_discussion_to_collaboration(collaboration)
        collaboration.register_activity(user)
        response.register_activity(user)
        return Response(_overview_payload(request))


class VKAppCooperationResponseDeclineView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, kind: str, pk: int):
        response = _response_for_kind(kind, pk)
        if response is None:
            return _json_error("Отклик не найден.", code=status.HTTP_404_NOT_FOUND)

        owner_id = response.offer.author_id if kind == "offer" else response.request.blogger_id
        if owner_id != request.user.id:
            return _json_error("Отклонить отклик может только владелец.", code=status.HTTP_403_FORBIDDEN)

        response.status = response.Status.DECLINED
        response.save(update_fields=["status", "updated_at"])
        response.register_activity(request.user)
        return Response(_overview_payload(request))


class VKAppCooperationResponseWithdrawView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, kind: str, pk: int):
        response = _response_for_kind(kind, pk)
        if response is None:
            return _json_error("Отклик не найден.", code=status.HTTP_404_NOT_FOUND)

        responder_id = response.respondent_id if kind == "offer" else response.responder_id
        if responder_id != request.user.id or response.status != response.Status.PENDING:
            return _json_error("Этот отклик нельзя отозвать.", code=status.HTTP_403_FORBIDDEN)

        response.status = response.Status.WITHDRAWN
        response.save(update_fields=["status", "updated_at"])
        response.register_activity(request.user)
        return Response(_overview_payload(request))


class VKAppCooperationResponseCommentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, kind: str, pk: int):
        response = _response_for_kind(kind, pk)
        if response is None:
            return _json_error("Отклик не найден.", code=status.HTTP_404_NOT_FOUND)
        if not response.is_participant(request.user) or not response.allows_discussion():
            return _json_error("Обсуждение этого отклика недоступно.", code=status.HTTP_403_FORBIDDEN)

        text = str(request.data.get("text", "")).strip()
        if not text:
            return _json_error("Напишите комментарий.")
        if kind == "offer":
            AuthorOfferResponseComment.objects.create(response=response, author=request.user, text=text[:1000])
        else:
            BloggerRequestResponseComment.objects.create(response=response, author=request.user, text=text[:1000])
        response.register_activity(request.user)
        return Response(_overview_payload(request))


class VKAppCooperationApproveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk: int):
        collaboration = get_object_or_404(Collaboration.objects.filter(_public_optional_offer_book_q()), pk=pk)
        if not collaboration.is_participant(request.user):
            return _json_error("Сотрудничество недоступно.", code=status.HTTP_403_FORBIDDEN)

        deadline = _future_or_today(request.data.get("deadline"))
        if deadline is None:
            return _json_error("Укажите дедлайн не раньше сегодняшней даты.")

        deadline_changed = collaboration.deadline != deadline
        collaboration.deadline = deadline
        if request.user.id == collaboration.author_id:
            collaboration.author_approved = True
            if deadline_changed:
                collaboration.partner_approved = False
        if request.user.id == collaboration.partner_id:
            collaboration.partner_approved = True
            if deadline_changed:
                collaboration.author_approved = False
        if collaboration.author_approved and collaboration.partner_approved:
            collaboration.status = Collaboration.Status.ACTIVE
        else:
            collaboration.status = Collaboration.Status.NEGOTIATION
        collaboration.save(update_fields=["deadline", "author_approved", "partner_approved", "status", "updated_at"])
        collaboration.register_activity(request.user)
        return Response(_overview_payload(request))


class VKAppCooperationStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk: int):
        collaboration = get_object_or_404(Collaboration.objects.filter(_public_optional_offer_book_q()), pk=pk)
        if request.user.id != collaboration.author_id:
            return _json_error("Статус может менять только автор.", code=status.HTTP_403_FORBIDDEN)

        target_status = str(request.data.get("status", "")).strip()
        if target_status == Collaboration.Status.COMPLETED:
            links = collaboration.get_review_links()
            if not links:
                return _json_error("Сначала нужны ссылки на опубликованные отзывы.")
            CollaborationStatusUpdate.confirm_completion(collaboration, links)
            collaboration.author_confirmed = True
            collaboration.save(update_fields=["author_confirmed", "updated_at"])
        elif target_status == Collaboration.Status.FAILED:
            CollaborationStatusUpdate.mark_failed(collaboration)
        elif target_status == Collaboration.Status.ACTIVE:
            if not (collaboration.author_approved and collaboration.partner_approved):
                return _json_error("Сначала дедлайн должны подтвердить оба участника.")
            collaboration.status = target_status
            collaboration.save(update_fields=["status", "updated_at"])
        elif target_status == Collaboration.Status.NEGOTIATION:
            collaboration.status = target_status
            collaboration.save(update_fields=["status", "updated_at"])
        else:
            return _json_error("Недопустимый статус.")

        collaboration.register_activity(request.user)
        return Response(_overview_payload(request))


class VKAppCooperationReviewLinksView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk: int):
        collaboration = get_object_or_404(Collaboration.objects.filter(_public_optional_offer_book_q()), pk=pk)
        if request.user.id != collaboration.partner_id:
            return _json_error("Ссылки на отзывы добавляет партнер.", code=status.HTTP_403_FORBIDDEN)
        if not collaboration.allows_discussion():
            return _json_error("Ссылки нельзя изменить для завершенного сотрудничества.")

        links = _parse_review_links(request.data.get("review_links", ""))
        if not links:
            return _json_error("Добавьте корректные ссылки на опубликованные отзывы.")
        collaboration.review_links = "\n".join(links)
        collaboration.partner_confirmed = True
        collaboration.status = Collaboration.Status.ACTIVE
        collaboration.save(update_fields=["review_links", "partner_confirmed", "status", "updated_at"])
        collaboration.register_activity(request.user)
        return Response(_overview_payload(request))


class VKAppCooperationMessageView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    @transaction.atomic
    def post(self, request, pk: int):
        collaboration = get_object_or_404(Collaboration.objects.filter(_public_optional_offer_book_q()), pk=pk)
        if not collaboration.is_participant(request.user) or not collaboration.allows_discussion():
            return _json_error("Сообщения недоступны.", code=status.HTTP_403_FORBIDDEN)

        text = str(request.data.get("text", "")).strip()
        epub_file = request.FILES.get("epub_file")
        if not text:
            return _json_error("Напишите сообщение.")
        if epub_file:
            if request.user.id != collaboration.author_id:
                return _json_error("EPUB может прикрепить только автор.", code=status.HTTP_403_FORBIDDEN)
            if not epub_file.name.lower().endswith(".epub"):
                return _json_error("Можно прикрепить только EPUB-файл.")

        CollaborationMessage.objects.create(
            collaboration=collaboration,
            author=request.user,
            text=text[:2000],
            epub_file=epub_file,
        )
        collaboration.register_activity(request.user)
        return Response(_overview_payload(request))
