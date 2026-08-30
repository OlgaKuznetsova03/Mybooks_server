from collections import OrderedDict
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.contrib.auth import authenticate, get_user_model
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import DatabaseError, connection, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.text import get_valid_filename
from rest_framework import generics, parsers, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView


logger = logging.getLogger(__name__)

from accounts.models import (
    BookChallenge,
    CoinTransaction,
    DAILY_LOGIN_REWARD_COINS,
    Profile,
    RewardAdTicket,
    YANDEX_AD_REWARD_COINS,
)
from accounts.services import InsufficientCoinsError
from accounts.views import (
    _build_book_challenge_context,
    _collect_profile_stats,
    _resolve_book_challenge_year,
)
from books.api_clients import google_books_client
from books.models import Book, Genre, Rating
from books.utils import build_book_search_filter
from books.views import (
    BOOK_LIST_POPULAR_DISCOVERY_CACHE_KEY,
    BOOK_LIST_POPULAR_DISCOVERY_CACHE_TIMEOUT,
    BOOK_LIST_RECENT_DISCOVERY_CACHE_KEY,
    BOOK_LIST_RECENT_DISCOVERY_CACHE_TIMEOUT,
    _attach_default_status_to_shelf_entries,
    _book_list_querysets,
    build_book_list_discovery_payload,
    load_book_list_popular_discovery_snapshot,
    save_book_list_popular_discovery_snapshot,
)
from games.catalog import GAME_ICON_URLS, get_game_cards
from games.models import (
    BookExchangeChallenge,
    BookExchangeOffer,
    BookJourneyAssignment,
    ForgottenBookEntry,
    Game,
    GameShelfState,
    MonthlyChallenge,
    NobelLaureateAssignment,
    YasnayaPolyanaNominationBook,
)
from games.services.book_journey import BookJourneyMap
from games.services.nobel_challenge import NobelLaureatesChallenge
from games.services.book_exchange import BookExchangeGame
from games.services.forgotten_books import ForgottenBooksGame
from games.services.read_before_buy import ReadBeforeBuyGame
from games.services.monthly_challenges import (
    MONTHLY_CHALLENGE_TITLES,
    calculate_completion,
    ensure_award_state,
    kind_from_slug,
    month_display,
    monthly_game_detail,
    save_monthly_challenge,
)
from games.services.monthly_awards import build_monthly_challenge_award_url
from collaborations.notifications import collect_notification_items
from reading_clubs.models import ReadingClub, ReadingParticipant
from reading_marathons.models import MarathonParticipant, ReadingMarathon
from shelves.models import (
    BookProgress,
    BookProgressMedium,
    CharacterNote,
    HomeLibraryEntry,
    ProgressAnnotation,
    PurchaseList,
    PurchaseListItem,
    ReadingFeedEntry,
    Shelf,
    ShelfItem,
)
from shelves.services import (
    ALL_DEFAULT_READ_SHELF_NAMES,
    DEFAULT_HOME_LIBRARY_SHELF,
    DEFAULT_READING_SHELF,
    DEFAULT_UNFINISHED_SHELF,
    DEFAULT_WANT_SHELF,
    ensure_default_shelves,
    get_default_shelf_status_map,
    get_home_library_shelf,
    move_book_to_read_shelf,
    move_book_to_reading_shelf,
    move_book_to_unfinished_shelf,
)
from user_ratings.models import UserPointEvent
from user_ratings.services import BOOK_COMPLETION, award_for_book_completion, award_for_review

from .authentication import issue_mobile_token
from .pagination import StandardResultsSetPagination
from .serializers import BookListSerializer
from .vk_app_serializers import (
    VKAppBookCreateSerializer,
    VKAppBookDetailSerializer,
    VKAppLoginSerializer,
    VKAppProfileSerializer,
    VKAppProfileUpdateSerializer,
    VKAppRegisterSerializer,
)
from .vk_views import build_user_shelves_payload


class VKAppImageProxyView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    allowed_hosts = {
        "s3.ru1.storage.beget.cloud",
        "kalejdoskopknig.ru",
        "www.kalejdoskopknig.ru",
    }
    max_image_size = 8 * 1024 * 1024

    def get(self, request, *args, **kwargs):
        raw_url = str(request.query_params.get("url") or "").strip()
        parsed_url = urlparse(raw_url)

        if parsed_url.scheme not in {"http", "https"} or parsed_url.hostname not in self.allowed_hosts:
            return Response({"detail": "Недопустимая ссылка на изображение."}, status=status.HTTP_400_BAD_REQUEST)

        upstream_request = Request(
            raw_url,
            headers={
                "User-Agent": "KalejdoskopBooksVKApp/1.0",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            },
        )

        try:
            with urlopen(upstream_request, timeout=10) as upstream_response:
                content_type = upstream_response.headers.get_content_type()
                if not content_type.startswith("image/"):
                    return Response({"detail": "Ссылка не ведет на изображение."}, status=status.HTTP_400_BAD_REQUEST)

                content = upstream_response.read(self.max_image_size + 1)
        except (HTTPError, URLError, TimeoutError, ValueError):
            return Response({"detail": "Не удалось загрузить изображение."}, status=status.HTTP_400_BAD_REQUEST)

        if len(content) > self.max_image_size:
            return Response({"detail": "Изображение слишком большое."}, status=status.HTTP_400_BAD_REQUEST)

        response = HttpResponse(content, content_type=content_type)
        response["Cache-Control"] = "public, max-age=86400"
        response["Access-Control-Allow-Origin"] = "*"
        return response


class VKAppGeneratedImageUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    allowed_content_types = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
    max_image_size = 8 * 1024 * 1024

    def _absolute_url(self, request, url):
        if not url:
            return None
        url = str(url).strip()
        if url.startswith("//"):
            return f"{request.scheme}:{url}"
        if url.startswith(("http://", "https://")):
            return url
        if url.startswith("/"):
            return request.build_absolute_uri(url)
        return request.build_absolute_uri(f"/{url.lstrip('/')}")

    def post(self, request, *args, **kwargs):
        image = request.FILES.get("image")
        if not image:
            return Response({"detail": "Передайте изображение."}, status=status.HTTP_400_BAD_REQUEST)

        content_type = str(getattr(image, "content_type", "") or "").lower()
        if content_type not in self.allowed_content_types:
            return Response({"detail": "Можно загрузить только изображение JPG, PNG или WebP."}, status=status.HTTP_400_BAD_REQUEST)

        if image.size > self.max_image_size:
            return Response({"detail": "Изображение слишком большое."}, status=status.HTTP_400_BAD_REQUEST)

        raw_filename = str(request.data.get("filename") or image.name or "kalejdoskop-image.jpg")
        filename = get_valid_filename(raw_filename) or "kalejdoskop-image.jpg"
        if "." not in filename:
            filename = f"{filename}.jpg"

        storage_path = f"vk_app_exports/{request.user.id}/{uuid4().hex}-{filename}"
        saved_path = default_storage.save(storage_path, image)
        file_url = self._absolute_url(request, default_storage.url(saved_path))

        return Response(
            {
                "url": file_url,
                "filename": filename,
            },
            status=status.HTTP_201_CREATED,
        )


class VKAppNotificationsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return Response(collect_notification_items(request.user))



GAME_SITE_PATHS = {
    "read-before-buy": "/games/read-before-buy/",
    "book-exchange-challenge": "/games/book-exchange/",
    "forgotten-books-12": "/games/forgotten-books/",
    "book-journey-map": "/games/journey-map/",
    "nobel-laureates": "/games/nobel-laureates/",
    "yasnaya-polyana-foreign-2026": "/games/yasnaya-polyana-foreign-2026/",
    "monthly-mini-books": "/games/monthly-mini-books/",
    "monthly-book-list": "/games/monthly-book-list/",
    "monthly-pages-minutes": "/games/monthly-pages-minutes/",
}

GAME_MECHANICS = {
    "read-before-buy": "points",
    "book-exchange-challenge": "exchange",
    "forgotten-books-12": "forgotten",
    "book-journey-map": "stages",
    "nobel-laureates": "stages",
    "yasnaya-polyana-foreign-2026": "annual",
    "monthly-mini-books": "monthly",
    "monthly-book-list": "monthly",
    "monthly-pages-minutes": "monthly",
}

GAME_ICON_BY_MECHANIC = {
    "annual": GAME_ICON_URLS.get("yasnaya-polyana-foreign-2026"),
}


def _vk_app_absolute_url(request, url):
    if not url:
        return None
    url = str(url).strip()
    if not url:
        return None
    if url.startswith("//"):
        return f"{request.scheme}:{url}"
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("/"):
        return request.build_absolute_uri(url)
    return request.build_absolute_uri(f"/{url.lstrip('/')}")


def _vk_app_book_cover_url(request, book):
    original_url = None
    original_getter = getattr(book, "get_original_cover_url", None)
    if callable(original_getter):
        try:
            original_url = original_getter()
        except Exception:
            original_url = None
    cover_url = None
    cover_getter = getattr(book, "get_cover_url", None)
    if callable(cover_getter):
        try:
            cover_url = cover_getter()
        except Exception:
            cover_url = None
    return _vk_app_absolute_url(request, original_url or cover_url)


def _vk_app_book_authors(book):
    try:
        return ", ".join(book.authors.all().values_list("name", flat=True))
    except Exception:
        return ""


def _vk_app_author_countries(book):
    try:
        countries = sorted(
            {
                author.country.strip()
                for author in book.authors.all()
                if getattr(author, "country", None) and author.country.strip()
            }
        )
        return ", ".join(countries)
    except Exception:
        return ""


def _vk_app_rating_stars(score_value):
    if score_value is None:
        return {"full": 0, "half": 0, "empty": 5}
    try:
        stars = max(0, min(5, float(score_value) / 2))
    except (TypeError, ValueError):
        return {"full": 0, "half": 0, "empty": 5}
    half_steps = int(round(stars * 2))
    full = half_steps // 2
    half = half_steps % 2
    empty = max(5 - full - half, 0)
    return {"full": full, "half": half, "empty": empty}


def _vk_app_date_payload(value):
    if not value:
        return (None, None)
    try:
        if hasattr(value, "tzinfo"):
            local_value = timezone.localtime(value) if timezone.is_aware(value) else value
            date_value = local_value.date()
        else:
            date_value = value
        return (date_value.isoformat(), date_value.strftime("%d.%m.%Y"))
    except Exception:
        return (None, None)


def _vk_app_user_name(user):
    if not user:
        return "Читатель"
    full_name = " ".join(
        part.strip()
        for part in [getattr(user, "first_name", ""), getattr(user, "last_name", "")]
        if part and part.strip()
    )
    return full_name or getattr(user, "username", "") or "Читатель"


def _vk_app_user_avatar_url(request, user):
    try:
        profile = getattr(user, "profile", None)
        avatar = getattr(profile, "avatar", None)
        if not avatar:
            return None
        return _vk_app_absolute_url(request, avatar.url)
    except Exception:
        return None


def _vk_app_rating_summary_payload(book):
    if not getattr(book, "is_publicly_visible", False):
        return {
            "average": None,
            "rating": None,
            "votes": 0,
            "votes_count": 0,
            "reviews": 0,
            "reviews_count": 0,
            "categories": [],
        }

    try:
        summary = book.get_rating_summary()
    except Exception:
        summary = {}

    score_summary = summary.get("score", {}) if isinstance(summary, dict) else {}
    average = score_summary.get("average")
    count = score_summary.get("count")
    categories = []

    for field_name, label in getattr(Rating, "CATEGORY_FIELDS", []):
        field_summary = summary.get(field_name, {}) if isinstance(summary, dict) else {}
        categories.append(
            {
                "field": field_name,
                "label": label,
                "average": field_summary.get("average"),
                "count": field_summary.get("count"),
            }
        )

    reviews_count = (
        Rating.objects.filter(book=book)
        .exclude(review__isnull=True)
        .exclude(review__exact="")
        .count()
    )

    return {
        "average": average,
        "rating": average,
        "votes": count or 0,
        "votes_count": count or 0,
        "reviews": reviews_count,
        "reviews_count": reviews_count,
        "categories": categories,
    }


def _vk_app_rating_payload(request, rating):
    created_at, created_label = _vk_app_date_payload(getattr(rating, "created_at", None))
    book = rating.book
    return {
        "id": rating.id,
        "book_id": book.id,
        "book_title": book.title,
        "book_author": _vk_app_book_authors(book),
        "book_cover_url": _vk_app_book_cover_url(request, book),
        "score": rating.score,
        "rating": rating.score,
        "plot_score": rating.plot_score,
        "characters_score": rating.characters_score,
        "atmosphere_score": rating.atmosphere_score,
        "art_score": rating.art_score,
        "review": rating.review or "",
        "text": rating.review or "",
        "created_at": created_at,
        "created_label": created_label,
        "date": created_label,
        "user_id": rating.user_id,
        "user_name": _vk_app_user_name(rating.user),
        "author": _vk_app_user_name(rating.user),
        "user_avatar": _vk_app_user_avatar_url(request, rating.user),
        "is_mine": bool(getattr(request.user, "is_authenticated", False) and request.user.id == rating.user_id),
        "app_path": f"/books/{book.id}",
        "site_path": f"/books/{book.id}/",
    }


def _vk_app_parse_score(value):
    if value in (None, ""):
        return None, None
    try:
        score = int(str(value).strip())
    except (TypeError, ValueError):
        return None, "Оценка должна быть числом от 1 до 10."
    if score < 1 or score > 10:
        return None, "Оценка должна быть числом от 1 до 10."
    return score, None


PROFILE_ACTIVITY_LIMIT = 20


def _vk_app_profile_book_payload(request, book):
    created_iso, created_label = _vk_app_date_payload(getattr(book, "created_at", None))
    return {
        "id": book.id,
        "title": book.title,
        "authors": _vk_app_book_authors(book),
        "cover_url": _vk_app_book_cover_url(request, book),
        "pages": book.get_total_pages() if hasattr(book, "get_total_pages") else None,
        "created_at": created_iso,
        "created_label": created_label,
        "app_path": f"/books/{book.id}",
        "site_path": f"/books/{book.id}/",
    }


def _vk_app_profile_author_books(request, user, *, public_only=False):
    is_author = user.groups.filter(name="author").exists()
    queryset = (
        Book.objects.filter(contributors=user)
        .select_related("primary_isbn")
        .prefetch_related("authors")
        .order_by("-created_at", "title")
    )
    if public_only:
        queryset = queryset.filter(
            visibility=Book.Visibility.PUBLIC,
            is_hidden_by_admin=False,
        )
    items = [
        _vk_app_profile_book_payload(request, book)
        for book in queryset[:PROFILE_ACTIVITY_LIMIT]
    ]
    total = queryset.count()
    return {
        "is_author": is_author,
        "can_manage": is_author,
        "count": total,
        "has_more": total > len(items),
        "items": items,
    }


def _vk_app_activity_status_label(status_code):
    return {
        "active": "Идет сейчас",
        "upcoming": "Скоро начнется",
        "past": "Завершено",
        "completed": "Выполнено",
        "in_progress": "В процессе",
        "approved": "Участвует",
        "pending": "Заявка на рассмотрении",
    }.get(str(status_code or ""), "Активность")


def _vk_app_activity_dates_payload(start_date, end_date=None):
    start_iso, start_label = _vk_app_date_payload(start_date)
    end_iso, end_label = _vk_app_date_payload(end_date)
    return {
        "start_date": start_iso,
        "start_label": start_label,
        "end_date": end_iso,
        "end_label": end_label,
    }


def _vk_app_club_activity_payload(club, role, participant_status=None):
    status_code = getattr(club, "status", "")
    return {
        "id": club.id,
        "type": "reading_club",
        "role": role,
        "participant_status": participant_status,
        "participant_status_label": _vk_app_activity_status_label(participant_status),
        "title": club.title,
        "book_id": club.book_id,
        "book_title": getattr(getattr(club, "book", None), "title", ""),
        "status": status_code,
        "status_label": _vk_app_activity_status_label(status_code),
        **_vk_app_activity_dates_payload(club.start_date, club.end_date),
        "app_path": f"/community/reading-clubs/{club.slug}",
        "site_path": club.get_absolute_url(),
    }


def _vk_app_marathon_activity_payload(marathon, role, participant_status=None):
    status_code = getattr(marathon, "status", "")
    return {
        "id": marathon.id,
        "type": "marathon",
        "role": role,
        "participant_status": participant_status,
        "participant_status_label": _vk_app_activity_status_label(participant_status),
        "title": marathon.title,
        "status": status_code,
        "status_label": _vk_app_activity_status_label(status_code),
        **_vk_app_activity_dates_payload(marathon.start_date, marathon.end_date),
        "app_path": f"/community/marathons/{marathon.slug}",
        "site_path": marathon.get_absolute_url(),
    }


def _vk_app_profile_game_activities(user):
    items = []

    journey_assignments = list(
        BookJourneyAssignment.objects.filter(user=user)
        .select_related("book")
        .order_by("stage_number")
    )
    if journey_assignments:
        completed = sum(1 for item in journey_assignments if item.is_completed)
        active = next((item for item in journey_assignments if not item.is_completed), None)
        items.append(
            {
                "slug": "book-journey-map",
                "type": "game",
                "title": "Книжное путешествие",
                "status": "completed" if completed == BookJourneyMap.get_stage_count() else "in_progress",
                "status_label": _vk_app_activity_status_label(
                    "completed" if completed == BookJourneyMap.get_stage_count() else "in_progress"
                ),
                "completed_count": completed,
                "total_count": BookJourneyMap.get_stage_count(),
                "current_stage": getattr(active, "stage_number", None),
                "app_path": "/games/book-journey-map",
                "site_path": GAME_SITE_PATHS.get("book-journey-map"),
            }
        )

    forgotten_entries = list(
        ForgottenBookEntry.objects.filter(user=user)
        .select_related("book")
        .order_by("added_at")
    )
    if forgotten_entries:
        items.append(
            {
                "slug": "forgotten-books-12",
                "type": "game",
                "title": "12 забытых книг",
                "status": "in_progress",
                "status_label": _vk_app_activity_status_label("in_progress"),
                "total_count": len(forgotten_entries),
                "selected_count": sum(1 for item in forgotten_entries if item.selected_month),
                "completed_count": sum(1 for item in forgotten_entries if item.completed_at),
                "app_path": "/games/forgotten-books-12",
                "site_path": GAME_SITE_PATHS.get("forgotten-books-12"),
            }
        )

    exchange_challenges = list(
        BookExchangeChallenge.objects.filter(user=user)
        .select_related("game")
        .order_by("-started_at")[:PROFILE_ACTIVITY_LIMIT]
    )
    for challenge in exchange_challenges:
        items.append(
            {
                "slug": "book-exchange-challenge",
                "type": "game",
                "title": "Обмен читательскими вызовами",
                "round_number": challenge.round_number,
                "status": challenge.status,
                "status_label": _vk_app_activity_status_label(challenge.status),
                "accepted_count": challenge.accepted_count,
                "target_count": challenge.target_books,
                "app_path": "/games/book-exchange-challenge",
                "site_path": challenge.get_absolute_url(),
            }
        )

    shelf_states = list(
        GameShelfState.objects.filter(user=user)
        .select_related("game", "shelf")
        .order_by("-updated_at")[:PROFILE_ACTIVITY_LIMIT]
    )
    for state in shelf_states:
        items.append(
            {
                "slug": getattr(state.game, "slug", ""),
                "type": "game",
                "title": getattr(state.game, "title", "") or "Игра",
                "status": "in_progress",
                "status_label": _vk_app_activity_status_label("in_progress"),
                "shelf_name": getattr(state.shelf, "name", ""),
                "points_balance": state.points_balance,
                "books_reviewed": state.books_reviewed,
                "books_purchased": state.books_purchased,
                "app_path": f"/games/{state.game.slug}",
                "site_path": GAME_SITE_PATHS.get(state.game.slug) or f"/games/{state.game.slug}/",
            }
        )

    nobel_assignments = list(
        NobelLaureateAssignment.objects.filter(user=user)
        .select_related("book")
        .order_by("stage_number")
    )
    if nobel_assignments:
        completed = sum(1 for item in nobel_assignments if item.is_completed)
        items.append(
            {
                "slug": "nobel-laureates",
                "type": "game",
                "title": "Прочитать всех нобелевских лауреатов",
                "status": "in_progress",
                "status_label": _vk_app_activity_status_label("in_progress"),
                "completed_count": completed,
                "total_count": NobelLaureatesChallenge.get_stage_count(),
                "app_path": "/games/nobel-laureates",
                "site_path": GAME_SITE_PATHS.get("nobel-laureates"),
            }
        )

    return {
        "count": len(items),
        "items": items[:PROFILE_ACTIVITY_LIMIT],
        "has_more": len(items) > PROFILE_ACTIVITY_LIMIT,
        "has_data": bool(items),
    }


def _vk_app_profile_activities(user):
    clubs_owned = [
        _vk_app_club_activity_payload(club, "creator", ReadingParticipant.Status.APPROVED)
        for club in ReadingClub.objects.filter(
            creator=user,
            book__visibility=Book.Visibility.PUBLIC,
            book__is_hidden_by_admin=False,
        )
        .select_related("book")
        .order_by("-start_date", "-created_at")[:PROFILE_ACTIVITY_LIMIT]
    ]
    clubs_participating = [
        _vk_app_club_activity_payload(club, "participant", ReadingParticipant.Status.APPROVED)
        for club in ReadingClub.objects.filter(
            participants__user=user,
            participants__status=ReadingParticipant.Status.APPROVED,
            book__visibility=Book.Visibility.PUBLIC,
            book__is_hidden_by_admin=False,
        )
        .exclude(creator=user)
        .select_related("book")
        .order_by("-start_date", "-created_at")
        .distinct()[:PROFILE_ACTIVITY_LIMIT]
    ]
    clubs_pending = [
        _vk_app_club_activity_payload(club, "pending", ReadingParticipant.Status.PENDING)
        for club in ReadingClub.objects.filter(
            participants__user=user,
            participants__status=ReadingParticipant.Status.PENDING,
            book__visibility=Book.Visibility.PUBLIC,
            book__is_hidden_by_admin=False,
        )
        .select_related("book")
        .order_by("-start_date", "-created_at")
        .distinct()[:PROFILE_ACTIVITY_LIMIT]
    ]

    marathons_owned = [
        _vk_app_marathon_activity_payload(marathon, "creator", MarathonParticipant.Status.APPROVED)
        for marathon in ReadingMarathon.objects.filter(creator=user)
        .order_by("-start_date", "-created_at")[:PROFILE_ACTIVITY_LIMIT]
    ]
    marathons_participating = [
        _vk_app_marathon_activity_payload(marathon, "participant", MarathonParticipant.Status.APPROVED)
        for marathon in ReadingMarathon.objects.filter(
            participants__user=user,
            participants__status=MarathonParticipant.Status.APPROVED,
        )
        .exclude(creator=user)
        .order_by("-start_date", "-created_at")
        .distinct()[:PROFILE_ACTIVITY_LIMIT]
    ]
    marathons_pending = [
        _vk_app_marathon_activity_payload(marathon, "pending", MarathonParticipant.Status.PENDING)
        for marathon in ReadingMarathon.objects.filter(
            participants__user=user,
            participants__status=MarathonParticipant.Status.PENDING,
        )
        .order_by("-start_date", "-created_at")
        .distinct()[:PROFILE_ACTIVITY_LIMIT]
    ]

    games = _vk_app_profile_game_activities(user)
    clubs_has_data = any((clubs_owned, clubs_participating, clubs_pending))
    marathons_has_data = any((marathons_owned, marathons_participating, marathons_pending))

    return {
        "games": games,
        "reading_clubs": {
            "owned": clubs_owned,
            "participating": clubs_participating,
            "pending": clubs_pending,
            "count": len(clubs_owned) + len(clubs_participating) + len(clubs_pending),
            "has_data": clubs_has_data,
        },
        "marathons": {
            "owned": marathons_owned,
            "participating": marathons_participating,
            "pending": marathons_pending,
            "count": len(marathons_owned) + len(marathons_participating) + len(marathons_pending),
            "has_data": marathons_has_data,
        },
        "has_any": games["has_data"] or clubs_has_data or marathons_has_data,
    }


def _vk_app_profile_awards(user):
    pending_queryset = MonthlyChallenge.objects.filter(user=user, awarded_at__isnull=True)
    for challenge in pending_queryset:
        completed, _progress = calculate_completion(challenge)
        ensure_award_state(challenge, completed)

    awards = []
    queryset = (
        MonthlyChallenge.objects.filter(user=user, awarded_at__isnull=False)
        .order_by("-month", "kind")
    )
    total = queryset.count()

    for challenge in queryset[:PROFILE_ACTIVITY_LIMIT]:
        awards.append(
            {
                "id": challenge.id,
                "kind": challenge.kind,
                "title": MONTHLY_CHALLENGE_TITLES.get(challenge.kind, "Награда"),
                "month": challenge.month.isoformat(),
                "month_display": month_display(challenge.month),
                "awarded_at": challenge.awarded_at.isoformat() if challenge.awarded_at else None,
                "award_url": build_monthly_challenge_award_url(
                    challenge.kind,
                    month=challenge.month,
                    awarded=True,
                ),
                "app_path": f"/games/monthly-{challenge.kind}",
            }
        )

    return {
        "items": awards,
        "count": total,
        "has_data": bool(awards),
        "has_more": total > len(awards),
    }


def _db_table_has_column(model, column_name):
    try:
        with connection.cursor() as cursor:
            description = connection.introspection.get_table_description(cursor, model._meta.db_table)
        columns = {getattr(column, "name", column[0]) for column in description}
        return column_name in columns
    except DatabaseError:
        return True


def _serialize_game_card(card):
    slug = getattr(card, "slug", "")
    is_available = bool(getattr(card, "is_available", True))
    mechanic = GAME_MECHANICS.get(slug, "planned" if not is_available else "points")
    return {
        "slug": slug,
        "title": getattr(card, "title", ""),
        "description": getattr(card, "description", ""),
        "status": "available" if is_available else "planned",
        "mechanic": mechanic,
        "badge": getattr(card, "badge", None),
        "highlights": list(getattr(card, "highlights", ()) or ()),
        "icon_url": getattr(card, "icon_url", None) or GAME_ICON_URLS.get(slug),
        "site_path": GAME_SITE_PATHS.get(slug),
    }


def _serialize_annual_game(game):
    total = getattr(game, "nominations_count", None)
    shortlist = getattr(game, "shortlist_count", None)
    if total is None or shortlist is None:
        try:
            nominations = game.yasnaya_polyana_nominations.all()
            total = nominations.count()
            shortlist = nominations.filter(is_shortlist=True).count()
        except Exception:
            total = 0
            shortlist = 0

    highlights = []
    if total:
        highlights.append(f"{total} книг в списке")
    if shortlist:
        highlights.append(f"{shortlist} в коротком списке")
    highlights.append("ежегодный сезон")

    return {
        "slug": game.slug,
        "title": game.title,
        "description": game.description,
        "status": "available",
        "mechanic": "annual",
        "badge": str(game.year) if game.year else "сезон",
        "year": game.year,
        "highlights": highlights,
        "icon_url": GAME_ICON_BY_MECHANIC["annual"],
        "site_path": GAME_SITE_PATHS.get(game.slug) or f"/games/{game.slug}/",
        "stats": [
            {"label": "Книг", "value": str(total or 0)},
            {"label": "Короткий список", "value": str(shortlist or 0)},
        ],
    }


def _annual_games_queryset():
    return Game.objects.filter(year__isnull=False).order_by("-year", "title")


def _serialize_journey_stages():
    stages = []
    for stage in BookJourneyMap.get_stages():
        terrain = BookJourneyMap.TERRAIN.get(stage.terrain, {})
        stages.append(
            {
                "number": stage.number,
                "title": stage.title,
                "requirement": stage.requirement,
                "description": stage.description,
                "badge": terrain.get("label") or stage.terrain,
                "status": "available",
            }
        )
    return stages


def _serialize_journey_book(request, book, progress=None):
    payload = {
        "id": book.id,
        "book_id": book.id,
        "title": book.title,
        "authors": _vk_app_book_authors(book),
        "cover_url": _vk_app_book_cover_url(request, book),
        "app_path": f"/books/{book.id}",
        "site_path": f"/books/{book.id}/",
        "tracker_url": f"/books/{book.id}/tracker",
    }
    if progress:
        payload["progress_id"] = progress.id
        payload["progress_percent"] = float(progress.percent or 0)
        payload["current_page"] = progress.current_page
    return payload


def _journey_available_books(request, user):
    read_book_ids = set(
        ShelfItem.objects.filter(
            shelf__user=user,
            shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
        ).values_list("book_id", flat=True)
    )
    allowed_book_ids = (
        ShelfItem.objects.filter(
            shelf__user=user,
            shelf__name__in=[
                DEFAULT_HOME_LIBRARY_SHELF,
                DEFAULT_WANT_SHELF,
                DEFAULT_READING_SHELF,
            ],
        )
        .exclude(book_id__in=read_book_ids)
        .values_list("book_id", flat=True)
        .distinct()
    )
    books = list(
        Book.objects.visible_to_user(user)
        .filter(id__in=allowed_book_ids)
        .prefetch_related("authors")
        .order_by("title")[:200]
    )
    progress_lookup = {}
    for progress in BookProgress.objects.filter(
        user=user,
        book_id__in=[book.id for book in books],
    ).order_by("-updated_at"):
        progress_lookup.setdefault(progress.book_id, progress)
    return [
        _serialize_journey_book(request, book, progress_lookup.get(book.id))
        for book in books
    ]


def _serialize_journey_assignment(request, assignment, progress=None, rating=None):
    started_at, started_at_display = _vk_app_date_payload(assignment.started_at)
    completed_at, completed_at_display = _vk_app_date_payload(assignment.completed_at)
    percent = None
    current_page = None
    if progress:
        try:
            percent = float(progress.percent or 0)
        except (TypeError, ValueError):
            percent = None
        current_page = progress.current_page
    is_completed = bool(assignment.is_completed)
    return {
        "id": assignment.id,
        "stage_number": assignment.stage_number,
        "status": assignment.status,
        "status_label": "Выполнено" if is_completed else "В процессе",
        "is_completed": is_completed,
        "book": _serialize_journey_book(request, assignment.book, progress),
        "progress_percent": percent,
        "current_page": current_page,
        "has_review": bool(rating and str(getattr(rating, "review", "") or "").strip()),
        "started_at": started_at,
        "started_at_display": started_at_display,
        "completed_at": completed_at,
        "completed_at_display": completed_at_display,
        "can_release": not is_completed,
    }


def _serialize_book_journey_game(request):
    user = getattr(request, "user", None)
    is_authenticated = bool(getattr(user, "is_authenticated", False))
    stages_source = BookJourneyMap.get_stages()
    terrain_legend = [
        {
            "key": key,
            "label": item.get("label") or key,
            "hint": item.get("description") or "",
        }
        for key, item in BookJourneyMap.get_terrain_legend()
    ]

    assignment_lookup = {}
    progress_lookup = {}
    review_lookup = {}
    active_stage_number = None
    available_books = []
    if is_authenticated:
        assignments = list(
            BookJourneyAssignment.objects.filter(user=user)
            .select_related("book")
            .prefetch_related("book__authors")
            .order_by("stage_number")
        )
        assignment_lookup = {item.stage_number: item for item in assignments}
        book_ids = [assignment.book_id for assignment in assignments]
        if book_ids:
            for progress in BookProgress.objects.filter(
                user=user,
                book_id__in=book_ids,
            ).order_by("-updated_at"):
                progress_lookup.setdefault(progress.book_id, progress)
            for rating in Rating.objects.filter(user=user, book_id__in=book_ids).order_by("-created_at"):
                review_lookup.setdefault(rating.book_id, rating)
        for assignment in assignments:
            if assignment.status == BookJourneyAssignment.Status.IN_PROGRESS:
                active_stage_number = assignment.stage_number
                break
        available_books = _journey_available_books(request, user)

    stages = []
    completed_count = 0
    in_progress_count = 0
    assigned_count = 0
    next_available_stage = None
    for stage in stages_source:
        assignment = assignment_lookup.get(stage.number)
        terrain = BookJourneyMap.TERRAIN.get(stage.terrain, {})
        status_code = "available"
        assignment_payload = None
        if assignment:
            assigned_count += 1
            status_code = "completed" if assignment.is_completed else "in_progress"
            assignment_payload = _serialize_journey_assignment(
                request,
                assignment,
                progress_lookup.get(assignment.book_id),
                review_lookup.get(assignment.book_id),
            )
        if status_code == "completed":
            completed_count += 1
        elif status_code == "in_progress":
            in_progress_count += 1
        elif next_available_stage is None:
            next_available_stage = stage.number

        stages.append(
            {
                "number": stage.number,
                "title": stage.title,
                "requirement": stage.requirement,
                "description": stage.description,
                "terrain": stage.terrain,
                "terrain_label": terrain.get("label") or stage.terrain,
                "badge": terrain.get("label") or stage.terrain,
                "top": stage.top,
                "left": stage.left,
                "status": status_code,
                "assignment": assignment_payload,
                "can_assign": (
                    is_authenticated
                    and status_code != "completed"
                    and (active_stage_number is None or active_stage_number == stage.number)
                ),
                "can_release": bool(assignment_payload and assignment_payload["can_release"]),
            }
        )

    total_stages = len(stages)
    available_count = max(total_stages - completed_count - in_progress_count, 0)
    progress_percent = round((completed_count / total_stages) * 100) if total_stages else 0

    return {
        "total_stages": total_stages,
        "completed_count": completed_count,
        "in_progress_count": in_progress_count,
        "available_count": available_count,
        "assigned_count": assigned_count,
        "progress_percent": progress_percent,
        "active_stage_number": active_stage_number,
        "next_available_stage": next_available_stage,
        "can_assign": is_authenticated,
        "stages": stages,
        "available_books": available_books,
        "terrain_legend": terrain_legend,
    }


def _serialize_nobel_book(request, book):
    return _serialize_journey_book(request, book)


def _nobel_available_books(request, user):
    allowed_shelves = [DEFAULT_WANT_SHELF, *ALL_DEFAULT_READ_SHELF_NAMES]
    books = (
        Book.objects.visible_to_user(user).filter(
            shelf_items__shelf__user=user,
            shelf_items__shelf__name__in=allowed_shelves,
        )
        .distinct()
        .prefetch_related("authors")
        .order_by("title")[:300]
    )
    available_books = []

    for book in books:
        payload = _serialize_nobel_book(request, book)
        payload["search"] = f"{book.title} {_vk_app_book_authors(book)}".lower()
        available_books.append(payload)

    return available_books


def _serialize_nobel_assignment(request, assignment, rating=None, read_entry=None):
    read_added_at = getattr(read_entry, "added_at", None)
    completed_at_value = assignment.completed_at or read_added_at
    completed_at, completed_at_display = _vk_app_date_payload(completed_at_value)
    is_completed = bool(assignment.is_completed or read_entry)

    return {
        "id": assignment.id,
        "stage_number": assignment.stage_number,
        "status": "completed" if is_completed else assignment.status,
        "status_label": "Выполнено" if is_completed else "В процессе",
        "is_completed": is_completed,
        "book": _serialize_nobel_book(request, assignment.book),
        "has_review": bool(rating and str(getattr(rating, "review", "") or "").strip()),
        "completed_at": completed_at,
        "completed_at_display": completed_at_display,
        "can_release": not is_completed,
    }


def _serialize_nobel_stages(request=None):
    user = getattr(request, "user", None)
    is_authenticated = bool(getattr(user, "is_authenticated", False))
    assignment_lookup = {}
    review_lookup = {}
    read_entry_lookup = {}

    if is_authenticated:
        assignments = list(
            NobelLaureateAssignment.objects.filter(user=user)
            .select_related("book")
            .prefetch_related("book__authors")
            .order_by("stage_number")
        )
        assignment_lookup = {item.stage_number: item for item in assignments}
        book_ids = [assignment.book_id for assignment in assignments]
        if book_ids:
            for read_entry in (
                ShelfItem.objects.filter(
                    shelf__user=user,
                    shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
                    book_id__in=book_ids,
                )
                .order_by("-added_at")
            ):
                read_entry_lookup.setdefault(read_entry.book_id, read_entry)
            for rating in Rating.objects.filter(user=user, book_id__in=book_ids).order_by("-created_at"):
                review_lookup.setdefault(rating.book_id, rating)

    stages = []

    for stage in NobelLaureatesChallenge.get_stages():
        assignment = assignment_lookup.get(stage.number)
        status_code = "available"
        assignment_payload = None

        if assignment:
            read_entry = read_entry_lookup.get(assignment.book_id)
            is_completed = bool(assignment.is_completed or read_entry)
            status_code = "completed" if is_completed else "in_progress"
            assignment_payload = _serialize_nobel_assignment(
                request,
                assignment,
                review_lookup.get(assignment.book_id),
                read_entry,
            )

        stages.append(
            {
                "number": stage.number,
                "title": stage.laureate,
                "requirement": stage.requirement,
                "description": stage.description,
                "badge": str(stage.year),
                "status": status_code,
                "assignment": assignment_payload,
                "can_assign": is_authenticated and status_code != "completed",
                "can_release": bool(assignment_payload and assignment_payload["can_release"]),
            }
        )

    return stages


def _serialize_read_before_buy_game(request):
    user = getattr(request, "user", None)
    is_authenticated = bool(getattr(user, "is_authenticated", False))
    purchase_cost = ReadBeforeBuyGame.PURCHASE_COST
    empty_overall = {
        "points_balance": 0,
        "books_reviewed": 0,
        "books_purchased": 0,
        "total_books": 0,
        "available_purchases": 0,
        "next_purchase_points": purchase_cost,
        "progress_percent": 0,
    }

    if not is_authenticated:
        return {
            "purchase_cost": purchase_cost,
            "shelf_count": 0,
            "can_enroll": False,
            "overall": empty_overall,
            "states": [],
        }

    total_books_subquery = Subquery(
        ShelfItem.objects.filter(shelf=OuterRef("shelf"))
        .order_by()
        .values("shelf")
        .annotate(item_count=Count("pk", distinct=True))
        .values("item_count")[:1]
    )
    states_qs = (
        ReadBeforeBuyGame.iter_participating_shelves(user)
        .prefetch_related("purchases__book")
        .annotate(
            total_books=Coalesce(
                total_books_subquery,
                Value(0),
                output_field=IntegerField(),
            )
        )
        .order_by("-points_balance", "shelf__name")
    )
    states = []
    total_books = 0
    points_balance = 0
    books_reviewed = 0
    books_purchased = 0

    for state in states_qs:
        state_total_books = int(getattr(state, "total_books", 0) or 0)
        state_points = int(state.points_balance or 0)
        state_available = state_points // purchase_cost if purchase_cost else 0
        state_progress = min(100, round((state_points / purchase_cost) * 100)) if purchase_cost else 0
        purchases = []
        for purchase in list(state.purchases.all())[:3]:
            created_at, created_at_display = _vk_app_date_payload(getattr(purchase, "created_at", None))
            book = getattr(purchase, "book", None)
            purchases.append(
                {
                    "id": purchase.id,
                    "book_id": getattr(book, "id", None),
                    "title": getattr(book, "title", None) or "Покупка книги",
                    "points_spent": int(purchase.points_spent or 0),
                    "created_at": created_at,
                    "created_at_display": created_at_display,
                }
            )

        states.append(
            {
                "id": state.id,
                "shelf_id": state.shelf_id,
                "shelf_name": state.shelf.name,
                "points_balance": state_points,
                "total_points_earned": int(state.total_points_earned or 0),
                "books_reviewed": int(state.books_reviewed or 0),
                "books_purchased": int(state.books_purchased or 0),
                "total_books": state_total_books,
                "points_needed": max(0, purchase_cost - state_points),
                "available_purchases": state_available,
                "progress_percent": state_progress,
                "purchases": purchases,
            }
        )
        total_books += state_total_books
        points_balance += state_points
        books_reviewed += int(state.books_reviewed or 0)
        books_purchased += int(state.books_purchased or 0)

    overall_available = sum(item["available_purchases"] for item in states)
    overall_progress = min(100, round((points_balance / purchase_cost) * 100)) if purchase_cost else 0
    return {
        "purchase_cost": purchase_cost,
        "shelf_count": len(states),
        "can_enroll": len(states) == 0,
        "overall": {
            "points_balance": points_balance,
            "books_reviewed": books_reviewed,
            "books_purchased": books_purchased,
            "total_books": total_books,
            "available_purchases": overall_available,
            "next_purchase_points": max(0, purchase_cost - points_balance),
            "progress_percent": overall_progress,
        },
        "states": states,
    }


def _vk_app_short_text(value, limit=180):
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    truncated = text[:limit].rsplit(" ", 1)[0]
    if not truncated:
        truncated = text[:limit]
    return truncated.rstrip(" .,;:") + "…"


def _vk_app_user_payload(request, user):
    profile = getattr(user, "profile", None)
    avatar = getattr(profile, "avatar", None)
    avatar_url = None
    if avatar:
        try:
            avatar_url = avatar.url
        except Exception:
            avatar_url = None
    return {
        "id": user.id,
        "username": user.username,
        "avatar_url": _vk_app_absolute_url(request, avatar_url),
    }


def _serialize_book_exchange_book(request, book):
    user = getattr(request, "user", None)
    read_item = None
    if getattr(user, "is_authenticated", False):
        read_item = (
            ShelfItem.objects.filter(
                shelf__user=user,
                shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
                book=book,
            )
            .order_by("-added_at")
            .first()
        )
    read_at, read_at_display = _vk_app_date_payload(getattr(read_item, "added_at", None))
    return {
        "id": book.id,
        "book_id": book.id,
        "title": book.title,
        "authors": _vk_app_book_authors(book),
        "cover_url": _vk_app_book_cover_url(request, book),
        "synopsis": _vk_app_short_text(getattr(book, "synopsis", ""), 180),
        "is_read": bool(read_item),
        "read_at": read_at,
        "read_at_display": read_at_display,
        "app_path": f"/books/{book.id}",
        "site_path": f"/books/{book.id}/",
    }


def _serialize_book_exchange_offer(request, offer):
    entry = getattr(offer, "accepted_entry", None)
    created_at, created_at_display = _vk_app_date_payload(getattr(offer, "created_at", None))
    responded_at, responded_at_display = _vk_app_date_payload(getattr(offer, "responded_at", None))
    accepted_at, accepted_at_display = _vk_app_date_payload(getattr(entry, "accepted_at", None))
    finished_at, finished_at_display = _vk_app_date_payload(getattr(entry, "finished_at", None))
    review_at, review_at_display = _vk_app_date_payload(getattr(entry, "review_submitted_at", None))
    completed_at, completed_at_display = _vk_app_date_payload(getattr(entry, "completed_at", None))
    return {
        "id": offer.id,
        "status": offer.status,
        "book": _serialize_book_exchange_book(request, offer.book),
        "offered_by": _vk_app_user_payload(request, offer.offered_by),
        "created_at": created_at,
        "created_at_display": created_at_display,
        "responded_at": responded_at,
        "responded_at_display": responded_at_display,
        "accepted_at": accepted_at,
        "accepted_at_display": accepted_at_display,
        "finished_at": finished_at,
        "finished_at_display": finished_at_display,
        "review_submitted_at": review_at,
        "review_submitted_at_display": review_at_display,
        "completed_at": completed_at,
        "completed_at_display": completed_at_display,
        "is_completed": bool(entry and entry.is_completed),
    }


def _serialize_book_exchange_challenge(request, challenge):
    accepted_count = challenge.accepted_books.filter(
        book__visibility=Book.Visibility.PUBLIC,
        book__is_hidden_by_admin=False,
    ).count()
    public_offers = challenge.offers.filter(
        book__visibility=Book.Visibility.PUBLIC,
        book__is_hidden_by_admin=False,
    )
    pending_count = public_offers.filter(status=BookExchangeOffer.Status.PENDING).count()
    declined_count = public_offers.filter(status=BookExchangeOffer.Status.DECLINED).count()
    total_offers = pending_count + accepted_count + declined_count
    allowed_declines = total_offers // 2
    remaining_declines = max(0, allowed_declines - declined_count)
    deadline_at, deadline_display = _vk_app_date_payload(getattr(challenge, "deadline_at", None))
    days_left = None
    if challenge.deadline_at:
        deadline = timezone.localtime(challenge.deadline_at)
        days_left = max((deadline.date() - timezone.localdate()).days, 0)
    user = getattr(request, "user", None)
    is_owner = bool(getattr(user, "is_authenticated", False) and challenge.user_id == user.id)
    return {
        "id": challenge.id,
        "round_number": challenge.round_number,
        "owner": _vk_app_user_payload(request, challenge.user),
        "target_books": challenge.target_books,
        "accepted_count": accepted_count,
        "pending_count": pending_count,
        "declined_count": declined_count,
        "total_offers": total_offers,
        "remaining_slots": max(challenge.target_books - accepted_count, 0),
        "remaining_declines": remaining_declines,
        "can_accept_more": challenge.can_accept_more(),
        "is_owner": is_owner,
        "status": challenge.status,
        "genres": list(challenge.genres.values_list("name", flat=True)),
        "deadline_at": deadline_at,
        "deadline_display": deadline_display,
        "days_left": days_left,
        "app_path": f"/games/{BookExchangeGame.SLUG}",
        "site_path": challenge.get_absolute_url(),
    }


def _serialize_book_exchange_game(request):
    user = getattr(request, "user", None)
    is_authenticated = bool(getattr(user, "is_authenticated", False))
    genre_options = [
        {"id": genre.id, "name": genre.name}
        for genre in Genre.objects.all().order_by("name")
    ]

    if not is_authenticated:
        return {
            "can_start": False,
            "active_challenge": None,
            "accepted": [],
            "pending": [],
            "declined": [],
            "community_challenges": [],
            "completed_challenges": [],
            "genre_options": genre_options,
        }

    challenge = BookExchangeGame.get_active_challenge(user)
    accepted = []
    pending = []
    declined = []
    if challenge:
        bundle = BookExchangeGame.get_offer_bundle(challenge)
        accepted = [_serialize_book_exchange_offer(request, offer) for offer in bundle.accepted]
        pending = [_serialize_book_exchange_offer(request, offer) for offer in bundle.pending]
        declined = [_serialize_book_exchange_offer(request, offer) for offer in bundle.declined]

    community_challenges = [
        _serialize_book_exchange_challenge(request, item)
        for item in BookExchangeGame.get_public_active_challenges(exclude_user=user).prefetch_related("genres")[:30]
    ]
    completed_challenges = [
        _serialize_book_exchange_challenge(request, item)
        for item in BookExchangeGame.get_completed_challenges(user).prefetch_related("accepted_books", "offers")[:10]
    ]

    return {
        "can_start": challenge is None,
        "active_challenge": _serialize_book_exchange_challenge(request, challenge) if challenge else None,
        "accepted": accepted,
        "pending": pending,
        "declined": declined,
        "community_challenges": community_challenges,
        "completed_challenges": completed_challenges,
        "genre_options": genre_options,
    }


def _serialize_forgotten_book(request, book):
    user = getattr(request, "user", None)
    progress = None
    read_item = None

    if getattr(user, "is_authenticated", False):
        progress = (
            BookProgress.objects.filter(user=user, book=book)
            .order_by("-updated_at")
            .first()
        )
        read_item = (
            ShelfItem.objects.filter(
                shelf__user=user,
                shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
                book=book,
            )
            .order_by("-added_at")
            .first()
        )

    read_at, read_at_display = _vk_app_date_payload(getattr(read_item, "added_at", None))
    payload = {
        "id": book.id,
        "book_id": book.id,
        "title": book.title,
        "authors": _vk_app_book_authors(book),
        "cover_url": _vk_app_book_cover_url(request, book),
        "is_read": bool(read_item),
        "read_at": read_at,
        "read_at_display": read_at_display,
        "app_path": f"/books/{book.id}",
        "site_path": f"/books/{book.id}/",
    }

    if progress:
        payload["progress_id"] = progress.id
        payload["tracker_url"] = f"/tracker/{progress.id}/"

    return payload


def _forgotten_entry_status(entry):
    if entry.completed_at:
        return ("completed", "Завершено")
    if entry.finished_at and entry.review_submitted_at:
        return ("completed", "Завершено")
    if entry.finished_at:
        return ("read", "Нужен отзыв")
    if entry.review_submitted_at:
        return ("reviewed", "Нужно прочитать")
    if entry.selected_month:
        return ("selected", "Выбрана")
    return ("pending", "В ожидании")


def _serialize_forgotten_entry(request, entry):
    added_at, added_at_display = _vk_app_date_payload(entry.added_at)
    selected_month, selected_month_display = _vk_app_date_payload(entry.selected_month)
    selected_at, selected_at_display = _vk_app_date_payload(entry.selected_at)
    finished_at, finished_at_display = _vk_app_date_payload(entry.finished_at)
    review_at, review_at_display = _vk_app_date_payload(entry.review_submitted_at)
    completed_at, completed_at_display = _vk_app_date_payload(entry.completed_at)
    deadline_at, deadline_display = _vk_app_date_payload(entry.get_deadline())
    status_code, status_label = _forgotten_entry_status(entry)

    return {
        "id": entry.id,
        "book": _serialize_forgotten_book(request, entry.book),
        "added_at": added_at,
        "added_at_display": added_at_display,
        "selected_month": selected_month,
        "selected_month_display": selected_month_display,
        "selected_at": selected_at,
        "selected_at_display": selected_at_display,
        "deadline_at": deadline_at,
        "deadline_display": deadline_display,
        "finished_at": finished_at,
        "finished_at_display": finished_at_display,
        "review_submitted_at": review_at,
        "review_submitted_at_display": review_at_display,
        "completed_at": completed_at,
        "completed_at_display": completed_at_display,
        "is_selected": bool(entry.is_selected),
        "is_completed": bool(entry.is_completed),
        "can_remove": not entry.is_selected,
        "status": status_code,
        "status_label": status_label,
    }


def _serialize_forgotten_books_game(request):
    user = getattr(request, "user", None)
    is_authenticated = bool(getattr(user, "is_authenticated", False))
    max_books = ForgottenBooksGame.MAX_BOOKS

    if not is_authenticated:
        return {
            "max_books": max_books,
            "added_books_count": 0,
            "remaining_slots": max_books,
            "progress_percent": 0,
            "selection": None,
            "entries": [],
            "pending_entries": [],
            "selected_entries": [],
            "available_books": [],
            "can_add_more": False,
        }

    selection = ForgottenBooksGame.ensure_monthly_selection(user)
    if not selection:
        selection = ForgottenBooksGame.get_current_selection(user)

    entries_for_sync = list(
        ForgottenBooksGame.get_entries(user)
        .select_related("book")
        .prefetch_related("book__authors")
    )
    for entry in entries_for_sync:
        ForgottenBookEntry.sync_for_user_book(user, entry.book)

    entries = list(
        ForgottenBooksGame.get_entries(user)
        .select_related("book")
        .prefetch_related("book__authors")
        .order_by("selected_month", "added_at", "book__title")
    )
    entry_book_ids = [entry.book_id for entry in entries]
    selected_entries = [entry for entry in entries if entry.selected_month]
    pending_entries = [entry for entry in entries if not entry.selected_month]
    remaining_slots = max(0, max_books - len(entries))

    available_books = []
    if remaining_slots:
        home_shelf = get_home_library_shelf(user)
        home_items = (
            ShelfItem.objects.filter(shelf=home_shelf)
            .exclude(book_id__in=entry_book_ids)
            .select_related("book")
            .prefetch_related("book__authors")
            .order_by("-added_at", "book__title")[:120]
        )
        available_books = [_serialize_forgotten_book(request, item.book) for item in home_items]

    selection_payload = None
    if selection:
        try:
            selection_entry = next((entry for entry in entries if entry.id == selection.entry.id), selection.entry)
            selection_payload = _serialize_forgotten_entry(request, selection_entry)
            month_start, month_start_display = _vk_app_date_payload(selection.month_start)
            deadline_at, deadline_display = _vk_app_date_payload(selection.deadline)
            selection_payload.update(
                {
                    "month_start": month_start,
                    "month_start_display": month_start_display,
                    "deadline_at": deadline_at,
                    "deadline_display": deadline_display,
                }
            )
        except Exception:
            selection_payload = None

    return {
        "max_books": max_books,
        "added_books_count": len(entries),
        "remaining_slots": remaining_slots,
        "progress_percent": round((len(entries) / max_books) * 100) if max_books else 0,
        "selection": selection_payload,
        "entries": [_serialize_forgotten_entry(request, entry) for entry in entries],
        "pending_entries": [_serialize_forgotten_entry(request, entry) for entry in pending_entries],
        "selected_entries": [
            _serialize_forgotten_entry(request, entry)
            for entry in sorted(
                selected_entries,
                key=lambda item: (item.selected_month or date.min, item.added_at),
                reverse=True,
            )
        ],
        "available_books": available_books,
        "can_add_more": remaining_slots > 0,
    }


def _static_game_detail(card, request=None):
    base = _serialize_game_card(card)
    slug = card.slug
    detail = {
        **base,
        "summary": card.description,
        "stats": [],
        "checklist": [],
        "sections": [],
        "stages": [],
    }

    monthly_kind = kind_from_slug(slug)
    if monthly_kind:
        detail.update(
            {
                "summary": card.description,
                "stats": [
                    {"label": "Формат", "value": "месяц", "hint": "регулярная игра"},
                    {"label": "Награда", "value": "2 состояния", "hint": "до и после выполнения"},
                ],
                "checklist": list(getattr(card, "highlights", ()) or ()),
            }
        )
        if request is not None and getattr(request.user, "is_authenticated", False):
            detail.update(monthly_game_detail(request, request.user, monthly_kind))
    elif slug == "read-before-buy":
        detail.update(
            {
                "summary": "Игра связывает чтение, отзывы и домашнюю библиотеку: чем больше страниц и отзывов, тем быстрее копятся баллы на новую книгу.",
                "stats": [
                    {"label": "Стоимость книги", "value": "1300", "hint": "баллов"},
                    {"label": "Страница", "value": "1", "hint": "балл"},
                    {"label": "Бонус", "value": "+50 / +150", "hint": "за большие книги"},
                ],
                "checklist": [
                    "Подключите домашнюю библиотеку.",
                    "Читайте и обновляйте прогресс.",
                    "Пишите отзывы к завершенным книгам.",
                    "Копите баллы на новую книгу.",
                ],
                "sections": [
                    {
                        "title": "Как начисляются баллы",
                        "items": [
                            "За каждую прочитанную страницу начисляется 1 балл.",
                            "За большие книги есть дополнительный бонус.",
                            "Покупка книги в игре стоит 1300 баллов.",
                        ],
                    }
                ],
            }
        )
    
        if request is not None:
            detail["points_game"] = _serialize_read_before_buy_game(request)
    elif slug == "book-exchange-challenge":
        detail.update(
            {
                "summary": "Личный книжный вызов: вы задаете цель и жанры, а другие читатели предлагают книги из своего прочитанного.",
                "stats": [
                    {"label": "Цель", "value": "своя", "hint": "по книгам"},
                    {"label": "Жанры", "value": "любимые", "hint": "для предложений"},
                    {"label": "Срок", "value": "1 год", "hint": "на чтение"},
                ],
                "checklist": [
                    "Создайте раунд.",
                    "Укажите цель и любимые жанры.",
                    "Принимайте подходящие предложения.",
                    "Читайте книги и оставляйте отзывы.",
                ],
            }
        )
        if request is not None:
            detail["exchange_game"] = _serialize_book_exchange_game(request)
    elif slug == "forgotten-books-12":
        detail.update(
            {
                "summary": "Игра возвращает к книгам, которые уже есть в домашней библиотеке, но постоянно откладываются.",
                "stats": [
                    {"label": "Лимит", "value": "12", "hint": "книг"},
                    {"label": "Выбор", "value": "1", "hint": "книга в месяц"},
                    {"label": "Финиш", "value": "отзыв", "hint": "до конца месяца"},
                ],
                "checklist": [
                    "Добавьте до 12 книг из домашней библиотеки.",
                    "В начале месяца сервис выберет книгу.",
                    "Прочитайте выбранную книгу.",
                    "Напишите отзыв до конца месяца.",
                ],
            }
        )
        if request is not None:
            detail["forgotten_game"] = _serialize_forgotten_books_game(request)
    elif slug == "book-journey-map":
        detail.update(
            {
                "summary": BookJourneyMap.SUBTITLE,
                "stats": [
                    {"label": "Этапов", "value": str(BookJourneyMap.get_stage_count()), "hint": "на карте"},
                    {"label": "Правило", "value": "отзыв", "hint": "закрывает этап"},
                ],
                "checklist": list(BookJourneyMap.CHECKLIST),
                "stages": _serialize_journey_stages(),
                "sections": [
                    {
                        "title": "Местности карты",
                        "items": [item["label"] for _, item in BookJourneyMap.get_terrain_legend()],
                    }
                ],
            }
        )
        if request is not None:
            detail["journey_game"] = _serialize_book_journey_game(request)
    elif slug == "nobel-laureates":
        detail.update(
            {
                "summary": NobelLaureatesChallenge.DESCRIPTION,
                "stats": [
                    {"label": "Этапов", "value": str(NobelLaureatesChallenge.get_stage_count()), "hint": "лауреата"},
                    {"label": "Порядок", "value": "любой", "hint": "без очереди"},
                ],
                "checklist": list(NobelLaureatesChallenge.CHECKLIST),
                "stages": _serialize_nobel_stages(request),
                "available_books": (
                    _nobel_available_books(request, request.user)
                    if request is not None and getattr(request.user, "is_authenticated", False)
                    else []
                ),
            }
        )

    return detail


def _serialize_annual_book(request, nomination, read_book_ids, read_shelf_items, ratings_map):
    book = nomination.book
    is_read = book.id in read_book_ids
    shelf_item = read_shelf_items.get(book.id)
    rating = ratings_map.get(book.id)
    score = getattr(rating, "score", None)
    read_at, read_at_display = _vk_app_date_payload(getattr(shelf_item, "added_at", None))
    status_label = "Прочитано" if is_read else "Не прочитано"
    if nomination.is_shortlist:
        status_label = f"Короткий список · {status_label}"

    return {
        "id": book.id,
        "book_id": book.id,
        "nomination_id": nomination.id,
        "title": book.title,
        "authors": _vk_app_book_authors(book),
        "author_country": _vk_app_author_countries(book),
        "cover_url": _vk_app_book_cover_url(request, book),
        "status": status_label,
        "is_shortlist": nomination.is_shortlist,
        "is_read": is_read,
        "read_at": read_at,
        "read_at_display": read_at_display,
        "score": score,
        "stars": _vk_app_rating_stars(score),
        "app_path": f"/books/{book.id}",
        "site_path": f"/books/{book.id}/",
    }


def _annual_game_detail(request, game):
    user = request.user
    is_authenticated = bool(getattr(user, "is_authenticated", False))
    can_manage = bool(is_authenticated and getattr(user, "is_superuser", False))
    has_game_column = _db_table_has_column(YasnayaPolyanaNominationBook, "game_id")
    read_book_ids = set()
    read_shelf_items = {}
    ratings_map = {}
    if is_authenticated:
        read_shelf_qs = list(
            ShelfItem.objects.filter(
                shelf__user=user,
                shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
            ).order_by("-added_at")
        )
        read_book_ids = {item.book_id for item in read_shelf_qs}
        read_shelf_items = {item.book_id: item for item in read_shelf_qs}
        ratings_map = {
            rating.book_id: rating
            for rating in Rating.objects.filter(user=user, book_id__in=read_book_ids).order_by("created_at")
        }

    nomination_queryset = YasnayaPolyanaNominationBook.objects.all()
    if has_game_column:
        nomination_queryset = nomination_queryset.filter(game=game)

    nominations = list(
        nomination_queryset
        .select_related("book")
        .prefetch_related("book__authors")
        .order_by("-is_shortlist", "book__title")
    )

    unread_books = []
    read_books = []
    shortlist_books = []
    for nomination in nominations:
        book_payload = _serialize_annual_book(request, nomination, read_book_ids, read_shelf_items, ratings_map)
        if nomination.is_shortlist:
            shortlist_books.append(book_payload)
        if nomination.book_id in read_book_ids:
            read_books.append(book_payload)
        elif not nomination.is_shortlist:
            unread_books.append(book_payload)

    base = _serialize_annual_game(game)
    total_count = len(nominations)
    read_count = len(read_books)
    shortlist_count = len(shortlist_books)
    highlights = []
    if total_count:
        highlights.append(f"{total_count} книг в списке")
    if shortlist_count:
        highlights.append(f"{shortlist_count} в коротком списке")
    highlights.append("ежегодный сезон")
    base["highlights"] = highlights

    return {
        **base,
        "summary": game.description,
        "stats": [
            {"label": "Всего", "value": str(total_count), "hint": "книг"},
            {"label": "Прочитано", "value": str(read_count), "hint": "из списка"},
            {"label": "Не прочитано", "value": str(max(total_count - read_count, 0)), "hint": "осталось"},
            {"label": "Короткий", "value": str(shortlist_count), "hint": "список"},
        ],
        "checklist": [
            "Откройте книгу из списка сезона.",
            "Добавьте ее на полку или в трекер чтения.",
            "Отмечайте прочитанные книги на своих полках.",
            "Следите за переходом книг в короткий список.",
        ],
        "sections": [
            {
                "title": "Что видно в сезоне",
                "items": [
                    "Длинный список книг номинации.",
                    "Короткий список, если он уже сформирован.",
                    "Какие книги пользователь уже прочитал.",
                ],
            }
        ],
        "permissions": {
            "can_manage": can_manage,
            "can_clone": can_manage,
        },
        "books": {
            "shortlist": shortlist_books,
            "unread": unread_books,
            "read": read_books,
        },
    }


class VKAppGamesView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        cards = get_game_cards()
        available_games = [_serialize_game_card(card) for card in cards if card.is_available]
        planned_games = [_serialize_game_card(card) for card in cards if not card.is_available]
        annual_games = [_serialize_annual_game(game) for game in _annual_games_queryset()]

        return Response(
            {
                "available_games": available_games,
                "planned_games": planned_games,
                "annual_games": annual_games,
            }
        )


class VKAppGameDetailView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug, *args, **kwargs):
        cards = get_game_cards()
        annual_game = Game.objects.filter(slug=slug).first()
        if annual_game and (
            annual_game.year is not None
            or slug == "yasnaya-polyana-foreign-2026"
        ):
            try:
                return Response(_annual_game_detail(request, annual_game))
            except DatabaseError:
                return Response(
                    {
                        "detail": (
                            "Данные сезонной игры временно недоступны. "
                            "Проверьте структуру таблицы номинаций сезонных игр на сервере."
                        )
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

        for card in cards:
            if card.slug == slug:
                return Response(_static_game_detail(card, request))

        return Response({"detail": "Игра не найдена."}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, slug, *args, **kwargs):
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            return Response({"detail": "Войдите в аккаунт, чтобы управлять игрой."}, status=status.HTTP_401_UNAUTHORIZED)

        cards = get_game_cards()
        card = next((item for item in cards if item.slug == slug), None)
        if card is None:
            return Response({"detail": "Игра не найдена."}, status=status.HTTP_404_NOT_FOUND)

        action = str(request.data.get("action") or "").strip()

        monthly_kind = kind_from_slug(slug)
        if monthly_kind:
            if action not in {"monthly_save", "save", "configure"}:
                return Response({"detail": "Неизвестное действие."}, status=status.HTTP_400_BAD_REQUEST)
            try:
                save_monthly_challenge(user, monthly_kind, request.data)
            except InsufficientCoinsError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_402_PAYMENT_REQUIRED)
            except (TypeError, ValueError) as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            detail = "Ежемесячный вызов сохранен."
            return Response({"detail": detail, "game": _static_game_detail(card, request)})

        if slug == "read-before-buy":
            if action == "enroll":
                shelf = get_home_library_shelf(user)
                ReadBeforeBuyGame.enable_for_shelf(user, shelf)
                detail = "Домашняя библиотека подключена к игре."
            elif action == "bulk_purchase":
                try:
                    state_id = int(request.data.get("state_id") or 0)
                    count = int(request.data.get("count") or 0)
                except (TypeError, ValueError):
                    return Response({"detail": "Укажите количество покупок."}, status=status.HTTP_400_BAD_REQUEST)
                if count <= 0:
                    return Response({"detail": "Укажите количество покупок."}, status=status.HTTP_400_BAD_REQUEST)
                state = ReadBeforeBuyGame.get_state_by_id(user, state_id)
                if not state:
                    return Response({"detail": "Полка не найдена или не подключена к игре."}, status=status.HTTP_404_NOT_FOUND)
                success, _message, _level = ReadBeforeBuyGame.spend_points_for_bulk_purchase(state, count)
                if not success:
                    return Response({"detail": "Недостаточно баллов для покупки."}, status=status.HTTP_400_BAD_REQUEST)
                detail = "Покупка учтена, баллы списаны."
            else:
                return Response({"detail": "Неизвестное действие."}, status=status.HTTP_400_BAD_REQUEST)

            return Response({"detail": detail, "game": _static_game_detail(card, request)})

        if slug == "book-journey-map":
            if action in {"assign", "journey-assign", "journey_assign", "assign_book"}:
                try:
                    stage_number = int(request.data.get("stage_number") or request.data.get("stage") or 0)
                    book_id = int(request.data.get("book_id") or request.data.get("book") or 0)
                except (TypeError, ValueError):
                    return Response({"detail": "Выберите этап и книгу для путешествия."}, status=status.HTTP_400_BAD_REQUEST)

                stage = BookJourneyMap.get_stage_by_number(stage_number)
                if not stage:
                    return Response({"detail": "Этап на карте не найден."}, status=status.HTTP_404_NOT_FOUND)

                try:
                    book = Book.objects.visible_to_user(user).prefetch_related("authors").get(pk=book_id)
                except Book.DoesNotExist:
                    return Response({"detail": "Книга не найдена."}, status=status.HTTP_404_NOT_FOUND)

                if ShelfItem.objects.filter(
                    shelf__user=user,
                    shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
                    book=book,
                ).exists():
                    return Response(
                        {"detail": "Прочитанную книгу нельзя прикрепить к новому этапу."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if not ShelfItem.objects.filter(
                    shelf__user=user,
                    shelf__name__in=[
                        DEFAULT_HOME_LIBRARY_SHELF,
                        DEFAULT_WANT_SHELF,
                        DEFAULT_READING_SHELF,
                    ],
                    book=book,
                ).exists():
                    return Response(
                        {"detail": "Сначала добавьте книгу на полку «Хочу прочитать», «Читаю» или в домашнюю библиотеку."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                active_other = (
                    BookJourneyAssignment.objects.filter(
                        user=user,
                        status=BookJourneyAssignment.Status.IN_PROGRESS,
                    )
                    .exclude(stage_number=stage_number)
                    .first()
                )
                if active_other:
                    return Response(
                        {"detail": f"Сначала завершите или снимите книгу с этапа #{active_other.stage_number}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                with transaction.atomic():
                    assignment, _created = BookJourneyAssignment.objects.get_or_create(
                        user=user,
                        stage_number=stage_number,
                        defaults={"book": book},
                    )
                    if assignment.is_completed:
                        return Response(
                            {"detail": "Завершенный этап нельзя пройти повторно."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    assignment.reset_progress(book=book)
                    move_book_to_reading_shelf(user, book)
                    BookProgress.objects.get_or_create(
                        event=None,
                        user=user,
                        book=book,
                        defaults={"percent": Decimal("0"), "current_page": 0},
                    )
                    BookJourneyAssignment.sync_for_user_book(user, book)
                detail = f"Книга «{book.title}» прикреплена к этапу #{stage_number}."

            elif action in {"release", "journey-release", "journey_release", "release_book"}:
                try:
                    stage_number = int(request.data.get("stage_number") or request.data.get("stage") or 0)
                except (TypeError, ValueError):
                    return Response({"detail": "Выберите этап, с которого нужно снять книгу."}, status=status.HTTP_400_BAD_REQUEST)

                stage = BookJourneyMap.get_stage_by_number(stage_number)
                if not stage:
                    return Response({"detail": "Этап на карте не найден."}, status=status.HTTP_404_NOT_FOUND)

                assignment = BookJourneyAssignment.objects.filter(
                    user=user,
                    stage_number=stage_number,
                ).first()
                if not assignment:
                    return Response({"detail": "Для этого этапа пока не выбрана книга."}, status=status.HTTP_404_NOT_FOUND)
                if assignment.is_completed:
                    return Response({"detail": "Завершенный этап нельзя отменить."}, status=status.HTTP_400_BAD_REQUEST)

                assignment.delete()
                detail = f"Этап «{stage.title}» снова свободен."
            else:
                return Response({"detail": "Неизвестное действие."}, status=status.HTTP_400_BAD_REQUEST)

            return Response({"detail": detail, "game": _static_game_detail(card, request)})

        if slug == ForgottenBooksGame.SLUG:
            if action in {"add", "forgotten-add", "forgotten_add", "add_forgotten_book"}:
                try:
                    book_id = int(request.data.get("book_id") or request.data.get("book") or 0)
                except (TypeError, ValueError):
                    return Response({"detail": "Выберите книгу из домашней библиотеки."}, status=status.HTTP_400_BAD_REQUEST)

                try:
                    book = Book.objects.visible_to_user(user).get(pk=book_id)
                except Book.DoesNotExist:
                    return Response({"detail": "Книга не найдена."}, status=status.HTTP_404_NOT_FOUND)

                success, detail, _level = ForgottenBooksGame.add_book(user, book)
                if not success:
                    return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
                ForgottenBooksGame.ensure_monthly_selection(user)

            elif action in {"remove", "forgotten-remove", "forgotten_remove", "remove_forgotten_book"}:
                try:
                    entry_id = int(request.data.get("entry_id") or request.data.get("entry") or 0)
                except (TypeError, ValueError):
                    return Response({"detail": "Выберите книгу, которую нужно убрать."}, status=status.HTTP_400_BAD_REQUEST)

                try:
                    entry = ForgottenBookEntry.objects.select_related("book").get(pk=entry_id, user=user)
                except ForgottenBookEntry.DoesNotExist:
                    return Response({"detail": "Книга в списке не найдена."}, status=status.HTTP_404_NOT_FOUND)

                success, detail, _level = ForgottenBooksGame.remove_entry(entry)
                if not success:
                    return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)

            else:
                return Response({"detail": "Неизвестное действие."}, status=status.HTTP_400_BAD_REQUEST)

            return Response({"detail": detail, "game": _static_game_detail(card, request)})

        if slug == NobelLaureatesChallenge.SLUG:
            if action in {"assign", "nobel-assign", "nobel_assign", "assign_book"}:
                try:
                    stage_number = int(request.data.get("stage_number") or request.data.get("stage") or 0)
                    book_id = int(request.data.get("book_id") or request.data.get("book") or 0)
                except (TypeError, ValueError):
                    return Response({"detail": "Выберите лауреата и книгу."}, status=status.HTTP_400_BAD_REQUEST)

                stage = NobelLaureatesChallenge.get_stage_by_number(stage_number)
                if not stage:
                    return Response({"detail": "Лауреат не найден в списке Нобелевской премии."}, status=status.HTTP_404_NOT_FOUND)

                try:
                    book = Book.objects.visible_to_user(user).prefetch_related("authors").get(pk=book_id)
                except Book.DoesNotExist:
                    return Response({"detail": "Книга не найдена."}, status=status.HTTP_404_NOT_FOUND)

                if not ShelfItem.objects.filter(
                    shelf__user=user,
                    shelf__name__in=[DEFAULT_WANT_SHELF, *ALL_DEFAULT_READ_SHELF_NAMES],
                    book=book,
                ).exists():
                    return Response(
                        {"detail": "Добавьте книгу на полку «Хочу прочитать» или «Прочитано», прежде чем прикреплять ее к лауреату."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                with transaction.atomic():
                    assignment, created = NobelLaureateAssignment.objects.get_or_create(
                        user=user,
                        stage_number=stage_number,
                        defaults={"book": book},
                    )
                    if not created and assignment.is_completed:
                        return Response({"detail": "Завершенный этап уже нельзя изменить."}, status=status.HTTP_400_BAD_REQUEST)
                    assignment.reset_progress(book=book)
                    NobelLaureateAssignment.sync_for_user_book(user, book)
                    assignment.refresh_from_db()

                detail = f"Книга «{book.title}» прикреплена к лауреату «{stage.laureate}»."

            elif action in {"release", "nobel-release", "nobel_release", "release_book"}:
                try:
                    stage_number = int(request.data.get("stage_number") or request.data.get("stage") or 0)
                except (TypeError, ValueError):
                    return Response({"detail": "Выберите лауреата, с которого нужно снять книгу."}, status=status.HTTP_400_BAD_REQUEST)

                stage = NobelLaureatesChallenge.get_stage_by_number(stage_number)
                if not stage:
                    return Response({"detail": "Лауреат не найден в списке Нобелевской премии."}, status=status.HTTP_404_NOT_FOUND)

                assignment = NobelLaureateAssignment.objects.filter(user=user, stage_number=stage_number).first()
                if not assignment:
                    return Response({"detail": "Для этого лауреата пока не выбрана книга."}, status=status.HTTP_404_NOT_FOUND)
                if assignment.is_completed:
                    return Response({"detail": "Нельзя снять книгу с уже завершенного этапа."}, status=status.HTTP_400_BAD_REQUEST)

                assignment.delete()
                detail = f"Лауреат «{stage.laureate}» снова свободен для выбора."

            else:
                return Response({"detail": "Неизвестное действие."}, status=status.HTTP_400_BAD_REQUEST)

            return Response({"detail": detail, "game": _static_game_detail(card, request)})

        if slug != BookExchangeGame.SLUG:
            return Response({"detail": "Действие для этой игры не поддерживается."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

        if action == "start":
            if BookExchangeGame.has_active_challenge(user):
                return Response({"detail": "Сначала завершите текущий раунд."}, status=status.HTTP_400_BAD_REQUEST)
            try:
                target_books = int(request.data.get("target_books") or 0)
            except (TypeError, ValueError):
                return Response({"detail": "Укажите, сколько книг готовы принять."}, status=status.HTTP_400_BAD_REQUEST)
            if target_books < 1 or target_books > 50:
                return Response({"detail": "Можно выбрать от 1 до 50 книг."}, status=status.HTTP_400_BAD_REQUEST)

            raw_genre_ids = request.data.get("genre_ids") or request.data.get("genres") or []
            if isinstance(raw_genre_ids, str):
                raw_genre_ids = [item.strip() for item in raw_genre_ids.split(",") if item.strip()]
            if not isinstance(raw_genre_ids, (list, tuple)):
                raw_genre_ids = []
            genre_ids = []
            genre_names = []
            for item in raw_genre_ids:
                text = str(item).strip()
                if text.isdigit():
                    genre_ids.append(int(text))
                elif text:
                    genre_names.append(text)
            genres = list(Genre.objects.filter(Q(id__in=genre_ids) | Q(name__in=genre_names)).distinct())
            if not genres:
                return Response({"detail": "Выберите хотя бы один жанр."}, status=status.HTTP_400_BAD_REQUEST)
            challenge = BookExchangeGame.start_new_challenge(user, target_books=target_books, genres=genres)
            detail = f"Стартовал раунд #{challenge.round_number}."

        elif action == "respond":
            challenge = BookExchangeGame.get_active_challenge(user)
            if not challenge:
                return Response({"detail": "Активный раунд не найден."}, status=status.HTTP_404_NOT_FOUND)
            try:
                offer_id = int(request.data.get("offer_id") or 0)
            except (TypeError, ValueError):
                return Response({"detail": "Предложение не найдено."}, status=status.HTTP_400_BAD_REQUEST)
            decision = str(request.data.get("decision") or "").strip()
            if decision not in {"accept", "decline"}:
                return Response({"detail": "Выберите действие для предложения."}, status=status.HTTP_400_BAD_REQUEST)
            try:
                offer = (
                    BookExchangeOffer.objects.select_related("challenge", "book", "offered_by")
                    .filter(book__visibility=Book.Visibility.PUBLIC, book__is_hidden_by_admin=False)
                    .get(pk=offer_id, challenge=challenge)
                )
            except BookExchangeOffer.DoesNotExist:
                return Response({"detail": "Предложение не найдено."}, status=status.HTTP_404_NOT_FOUND)
            if decision == "accept":
                success, detail, _level = BookExchangeGame.accept_offer(offer, acting_user=user)
            else:
                success, detail, _level = BookExchangeGame.decline_offer(offer, acting_user=user)
            if not success:
                return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)

        elif action == "offer":
            try:
                challenge_id = int(request.data.get("challenge_id") or 0)
                book_id = int(request.data.get("book_id") or 0)
            except (TypeError, ValueError):
                return Response({"detail": "Выберите книгу и вызов."}, status=status.HTTP_400_BAD_REQUEST)
            challenge = BookExchangeGame.get_public_active_challenges().filter(pk=challenge_id).prefetch_related("genres").first()
            if not challenge:
                return Response({"detail": "Вызов не найден или уже завершен."}, status=status.HTTP_404_NOT_FOUND)
            try:
                book = Book.objects.public().prefetch_related("genres").get(pk=book_id)
            except Book.DoesNotExist:
                return Response({"detail": "Книга не найдена."}, status=status.HTTP_404_NOT_FOUND)
            success, detail, _level = BookExchangeGame.offer_book(challenge, offered_by=user, book=book)
            if not success:
                return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)

        else:
            return Response({"detail": "Неизвестное действие."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": detail, "game": _static_game_detail(card, request)})


def _grant_vk_app_daily_reward(user):
    profile, _ = Profile.objects.get_or_create(user=user)
    daily_reward_tx = profile.grant_daily_login_reward(
        description="Ежедневный бонус за вход в мини-приложение VK",
    )
    profile.refresh_from_db(fields=["coins", "last_daily_reward_at"])

    return profile, {
        "awarded": daily_reward_tx is not None,
        "coins": DAILY_LOGIN_REWARD_COINS if daily_reward_tx else 0,
        "balance_after": (
            daily_reward_tx.balance_after
            if daily_reward_tx
            else profile.coins
        ),
        "reward_date": (
            profile.last_daily_reward_at.isoformat()
            if profile.last_daily_reward_at
            else None
        ),
    }


class VKAppLoginView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = VKAppLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].lower()
        password = serializer.validated_data["password"]

        user_model = get_user_model()
        user = None
        try:
            candidate = user_model.objects.filter(email__iexact=email).first()
            if candidate:
                user = authenticate(request, username=candidate.username, password=password)
        except DatabaseError:
            return Response(
                {"detail": "Сервис авторизации временно недоступен. Попробуйте позже."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if not user:
            return Response(
                {"detail": "Неверный email или пароль."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile, daily_reward = _grant_vk_app_daily_reward(user)
        profile_payload = dict(VKAppProfileSerializer(profile, context={"request": request}).data)
        profile_payload["id"] = user.id
        profile_payload["awards"] = _vk_app_profile_awards(user)
        token = issue_mobile_token(user, rotate=True)
        return Response(
            {
                "token": token,
                "user": profile_payload,
                "daily_reward": daily_reward,
            }
        )


class VKAppRegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = VKAppRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.save()
        profile, daily_reward = _grant_vk_app_daily_reward(user)
        profile_payload = dict(VKAppProfileSerializer(profile, context={"request": request}).data)
        profile_payload["id"] = user.id
        profile_payload["awards"] = _vk_app_profile_awards(user)
        token = issue_mobile_token(user)

        return Response(
            {
                "token": token,
                "user": profile_payload,
                "daily_reward": daily_reward,
            },
            status=status.HTTP_201_CREATED,
        )


def _reward_ad_day_start(now):
    return timezone.make_aware(
        datetime.combine(timezone.localdate(now), datetime.min.time()),
        timezone.get_current_timezone(),
    )


class VKAppRewardAdStartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        provider = str(request.data.get("provider") or "").strip().lower()
        allowed_providers = {choice for choice, _ in RewardAdTicket.Provider.choices}
        if provider not in allowed_providers:
            return Response({"detail": "Неизвестный рекламный провайдер."}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        daily_limit = max(1, int(getattr(settings, "REWARD_AD_DAILY_LIMIT", 10)))
        cooldown_seconds = max(0, int(getattr(settings, "REWARD_AD_COOLDOWN_SECONDS", 60)))
        min_view_seconds = max(1, int(getattr(settings, "REWARD_AD_MIN_VIEW_SECONDS", 5)))
        ticket_ttl_seconds = max(min_view_seconds + 30, int(getattr(settings, "REWARD_AD_TICKET_TTL_SECONDS", 900)))
        profile, _ = Profile.objects.get_or_create(user=request.user)

        if profile.has_active_premium:
            return Response(
                {"detail": "При активном Премиуме монеты не списываются, рекламная награда не требуется."},
                status=status.HTTP_403_FORBIDDEN,
            )

        with transaction.atomic():
            profile = Profile.objects.select_for_update().get(pk=profile.pk)
            claimed_today = RewardAdTicket.objects.filter(
                profile=profile,
                claimed_at__gte=_reward_ad_day_start(now),
            ).count()
            if claimed_today >= daily_limit:
                return Response(
                    {"detail": "Дневной лимит рекламных наград уже получен.", "daily_remaining": 0},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

            latest_claim = (
                RewardAdTicket.objects.filter(profile=profile, claimed_at__isnull=False)
                .order_by("-claimed_at")
                .values_list("claimed_at", flat=True)
                .first()
            )
            if latest_claim:
                retry_after = cooldown_seconds - int((now - latest_claim).total_seconds())
                if retry_after > 0:
                    return Response(
                        {
                            "detail": "Следующую рекламную награду можно получить немного позже.",
                            "retry_after": retry_after,
                            "daily_remaining": daily_limit - claimed_today,
                        },
                        status=status.HTTP_429_TOO_MANY_REQUESTS,
                    )

            RewardAdTicket.objects.filter(
                profile=profile,
                claimed_at__isnull=True,
                expires_at__gt=now,
            ).update(expires_at=now)

            ad_unit_id = ""
            if provider == RewardAdTicket.Provider.YANDEX:
                ad_unit_id = str(getattr(settings, "YANDEX_REWARDED_AD_UNIT_ID", "")).strip()
                if not ad_unit_id:
                    return Response({"detail": "Рекламный блок временно не настроен."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

            ticket = RewardAdTicket.objects.create(
                profile=profile,
                provider=provider,
                ad_unit_id=ad_unit_id,
                not_before=now + timedelta(seconds=min_view_seconds),
                expires_at=now + timedelta(seconds=ticket_ttl_seconds),
            )

            balance_before = None
            transaction_record = None
            if provider == RewardAdTicket.Provider.VK:
                # VK can close its ad WebView before the client sends a second
                # request. Credit the shared Profile.coins balance atomically
                # with ticket issuance so that the reward cannot be lost.
                balance_before = profile.coins
                transaction_record = profile.reward_ad_view(
                    YANDEX_AD_REWARD_COINS,
                    description=f"Reward for viewing an ad ({ticket.get_provider_display()})",
                )
                profile.refresh_from_db(fields=("coins",))
                if profile.coins != balance_before + YANDEX_AD_REWARD_COINS:
                    raise RuntimeError("Reward ad coin balance was not updated")

                ticket.claimed_at = now
                ticket.transaction = transaction_record
                ticket.save(update_fields=("claimed_at", "transaction"))

        response_data = {
            "ticket": str(ticket.token),
            "provider": ticket.provider,
            "reward_amount": YANDEX_AD_REWARD_COINS,
            "expires_at": ticket.expires_at.isoformat(),
            "daily_remaining": daily_limit - claimed_today,
        }

        if transaction_record is not None:
            logger.info(
                "Reward ad ticket issued and coins credited: user_id=%s profile_id=%s "
                "ticket=%s provider=%s transaction_id=%s balance_after=%s",
                request.user.pk,
                profile.pk,
                ticket.token,
                ticket.provider,
                transaction_record.pk,
                profile.coins,
            )
            response_data.update(
                {
                    "coins_awarded": YANDEX_AD_REWARD_COINS,
                    "balance_before": balance_before,
                    "balance_after": profile.coins,
                    "transaction_id": transaction_record.pk,
                    "already_claimed": False,
                    "daily_remaining": max(0, daily_limit - claimed_today - 1),
                }
            )
        else:
            logger.info(
                "Reward ad ticket issued: user_id=%s profile_id=%s ticket=%s provider=%s",
                request.user.pk,
                profile.pk,
                ticket.token,
                ticket.provider,
            )

        return Response(
            response_data,
            status=status.HTTP_201_CREATED,
        )


class VKAppRewardAdClaimView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        token = str(request.data.get("ticket") or "").strip()
        if not token:
            return Response({"detail": "Не указан билет рекламной награды."}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        daily_limit = max(1, int(getattr(settings, "REWARD_AD_DAILY_LIMIT", 10)))
        cooldown_seconds = max(0, int(getattr(settings, "REWARD_AD_COOLDOWN_SECONDS", 60)))
        profile, _ = Profile.objects.get_or_create(user=request.user)

        with transaction.atomic():
            profile = Profile.objects.select_for_update().get(pk=profile.pk)
            try:
                ticket = (
                    RewardAdTicket.objects.select_for_update()
                    .select_related("transaction")
                    .get(profile=profile, token=token)
                )
            except (RewardAdTicket.DoesNotExist, ValueError, ValidationError):
                return Response({"detail": "Рекламная награда не найдена."}, status=status.HTTP_404_NOT_FOUND)

            if ticket.claimed_at:
                transaction_record = ticket.transaction
                recovered_award = False

                # Older deployments could mark the ticket as claimed before
                # linking the coin transaction. Recover such a ticket once,
                # while first looking for the matching unlinked ledger entry.
                if transaction_record is None:
                    transaction_record = (
                        CoinTransaction.objects.filter(
                            profile=profile,
                            transaction_type=CoinTransaction.Type.AD_REWARD,
                            created_at__gte=ticket.issued_at,
                            created_at__lte=ticket.claimed_at + timedelta(minutes=1),
                            reward_ad_ticket__isnull=True,
                        )
                        .order_by("created_at")
                        .first()
                    )

                    if transaction_record is None:
                        balance_before = profile.coins
                        transaction_record = profile.reward_ad_view(
                            YANDEX_AD_REWARD_COINS,
                            description=f"Восстановленная награда за просмотр рекламы ({ticket.get_provider_display()})",
                        )
                        profile.refresh_from_db(fields=("coins",))
                        if profile.coins != balance_before + YANDEX_AD_REWARD_COINS:
                            raise RuntimeError("Recovered reward ad coin balance was not updated")
                        recovered_award = True

                    ticket.transaction = transaction_record
                    ticket.save(update_fields=("transaction",))

                profile.refresh_from_db(fields=("coins",))
                balance_after = profile.coins
                logger.info(
                    "Reward ad claim replayed: user_id=%s profile_id=%s ticket=%s "
                    "transaction_id=%s recovered=%s balance_after=%s",
                    request.user.pk,
                    profile.pk,
                    ticket.token,
                    transaction_record.pk,
                    recovered_award,
                    balance_after,
                )
                return Response(
                    {
                        "coins_awarded": YANDEX_AD_REWARD_COINS if recovered_award else 0,
                        "reward_amount": YANDEX_AD_REWARD_COINS,
                        "balance_before": (
                            balance_after - YANDEX_AD_REWARD_COINS
                            if recovered_award
                            else balance_after
                        ),
                        "balance_after": balance_after,
                        "transaction_id": transaction_record.pk,
                        "already_claimed": not recovered_award,
                        "recovered": recovered_award,
                        "daily_remaining": max(
                            0,
                            daily_limit - RewardAdTicket.objects.filter(
                                profile=profile,
                                claimed_at__gte=_reward_ad_day_start(now),
                            ).count(),
                        ),
                    }
                )

            if profile.has_active_premium:
                return Response({"detail": "При активном Премиуме рекламная награда не требуется."}, status=status.HTTP_403_FORBIDDEN)
            if now < ticket.not_before:
                return Response({"detail": "Реклама еще не завершена."}, status=status.HTTP_409_CONFLICT)
            if now >= ticket.expires_at:
                return Response({"detail": "Время получения рекламной награды истекло."}, status=status.HTTP_410_GONE)

            claimed_today = RewardAdTicket.objects.filter(
                profile=profile,
                claimed_at__gte=_reward_ad_day_start(now),
            ).count()
            if claimed_today >= daily_limit:
                return Response(
                    {"detail": "Дневной лимит рекламных наград уже получен.", "daily_remaining": 0},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

            latest_claim = (
                RewardAdTicket.objects.filter(profile=profile, claimed_at__isnull=False)
                .order_by("-claimed_at")
                .values_list("claimed_at", flat=True)
                .first()
            )
            if latest_claim:
                retry_after = cooldown_seconds - int((now - latest_claim).total_seconds())
                if retry_after > 0:
                    return Response(
                        {"detail": "Следующую рекламную награду можно получить немного позже.", "retry_after": retry_after},
                        status=status.HTTP_429_TOO_MANY_REQUESTS,
                    )

            balance_before = profile.coins
            transaction_record = profile.reward_ad_view(
                YANDEX_AD_REWARD_COINS,
                description=f"Награда за просмотр рекламы ({ticket.get_provider_display()})",
            )
            profile.refresh_from_db(fields=("coins",))
            expected_balance = balance_before + YANDEX_AD_REWARD_COINS
            if profile.coins != expected_balance:
                raise RuntimeError("Reward ad coin balance was not updated")
            ticket.claimed_at = now
            ticket.transaction = transaction_record
            ticket.save(update_fields=("claimed_at", "transaction"))

            logger.info(
                "Reward ad coins credited: user_id=%s profile_id=%s ticket=%s "
                "transaction_id=%s balance_before=%s balance_after=%s",
                request.user.pk,
                profile.pk,
                ticket.token,
                transaction_record.pk,
                balance_before,
                profile.coins,
            )

        return Response(
            {
                "coins_awarded": YANDEX_AD_REWARD_COINS,
                "reward_amount": YANDEX_AD_REWARD_COINS,
                "balance_before": balance_before,
                "balance_after": profile.coins,
                "transaction_id": transaction_record.pk,
                "already_claimed": False,
                "recovered": False,
                "daily_remaining": max(0, daily_limit - claimed_today - 1),
            }
        )


class VKAppProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]

    def get(self, request, *args, **kwargs):
        profile, daily_reward = _grant_vk_app_daily_reward(request.user)
        serializer = VKAppProfileSerializer(profile, context={"request": request})
        profile_payload = dict(serializer.data)
        profile_payload["id"] = request.user.id

        books_added_count = request.user.contributed_books.count()
        shelves_payload = build_user_shelves_payload(request.user, request=request)
        author_books_payload = _vk_app_profile_author_books(request, request.user)
        activities_payload = _vk_app_profile_activities(request.user)
        awards_payload = _vk_app_profile_awards(request.user)
        points_total = (
            UserPointEvent.objects
            .filter(user=request.user)
            .aggregate(total=Sum("points"))
            .get("total")
            or 0
        )

        return Response(
            {
                "profile": profile_payload,
                "stats": {
                    "books_added": books_added_count,
                    "points": int(points_total),
                    "total_points": int(points_total),
                    "rating_points_total": int(points_total),
                    **shelves_payload["stats"],
                },
                "books": shelves_payload["books"],
                "shelves": shelves_payload["shelves"],
                "shelf_counts": shelves_payload["shelf_counts"],
                "author_books": author_books_payload,
                "activities": activities_payload,
                "awards": awards_payload,
                "daily_reward": daily_reward,
            }
        )

    def patch(self, request, *args, **kwargs):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        serializer = VKAppProfileUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()
        response_serializer = VKAppProfileSerializer(profile, context={"request": request})
        profile_payload = dict(response_serializer.data)
        profile_payload["id"] = request.user.id
        author_books_payload = _vk_app_profile_author_books(request, request.user)
        activities_payload = _vk_app_profile_activities(request.user)
        awards_payload = _vk_app_profile_awards(request.user)

        points_total = (
            UserPointEvent.objects
            .filter(user=request.user)
            .aggregate(total=Sum("points"))
            .get("total")
            or 0
        )

        return Response(
            {
                "profile": profile_payload,
                "stats": {
                    "points": int(points_total),
                    "total_points": int(points_total),
                    "rating_points_total": int(points_total),
                },
                "author_books": author_books_payload,
                "activities": activities_payload,
                "awards": awards_payload,
            }
        )

    def delete(self, request, *args, **kwargs):
        password = str(request.data.get("password") or "")
        if not password:
            return Response(
                {"detail": "Введите пароль для подтверждения удаления профиля."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not request.user.check_password(password):
            return Response(
                {"detail": "Неверный пароль."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        user.delete()
        return Response({"detail": "Профиль удалён."}, status=status.HTTP_200_OK)


class VKAppPublicProfileView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, username, *args, **kwargs):
        user_model = get_user_model()
        user = get_object_or_404(
            user_model.objects.select_related("profile"),
            username=username,
        )
        profile, _ = Profile.objects.get_or_create(user=user)
        is_owner = bool(
            request.user.is_authenticated and request.user.pk == user.pk
        )
        shelves_are_private = bool(profile.is_private and not is_owner)

        profile_payload = dict(
            VKAppProfileSerializer(profile, context={"request": request}).data
        )
        for field_name in (
            "email",
            "coins",
            "coin_balance",
            "has_active_premium",
            "has_unlimited_coins",
            "premium_expires_at",
        ):
            profile_payload.pop(field_name, None)
        profile_payload["id"] = user.id
        profile_payload["is_owner"] = is_owner

        if shelves_are_private:
            shelf_codes = (
                "want_to_read",
                "reading",
                "library",
                "read",
                "unfinished",
            )
            shelves_payload = {
                "books": [],
                "shelves": {code: [] for code in shelf_codes},
                "shelf_counts": {code: 0 for code in shelf_codes},
                "stats": {
                    "books_count": 0,
                    "library_books_count": 0,
                    "pages_read": 0,
                    "total_pages": 0,
                },
            }
        else:
            shelves_payload = build_user_shelves_payload(
                user,
                request=request,
                public_only=True,
            )

        author_books_payload = (
            {
                "is_author": user.groups.filter(name="author").exists(),
                "can_manage": False,
                "count": 0,
                "has_more": False,
                "items": [],
            }
            if shelves_are_private
            else _vk_app_profile_author_books(
                request,
                user,
                public_only=True,
            )
        )

        return Response(
            {
                "profile": profile_payload,
                "stats": shelves_payload["stats"],
                "books": shelves_payload["books"],
                "shelves": shelves_payload["shelves"],
                "shelf_counts": shelves_payload["shelf_counts"],
                "author_books": author_books_payload,
                "activities": {
                    "games": {"items": [], "count": 0, "has_data": False},
                    "reading_clubs": {
                        "owned": [],
                        "participating": [],
                        "pending": [],
                        "count": 0,
                        "has_data": False,
                    },
                    "marathons": {
                        "owned": [],
                        "participating": [],
                        "pending": [],
                        "count": 0,
                        "has_data": False,
                    },
                    "has_any": False,
                },
                "awards": {"items": [], "count": 0, "has_data": False},
                "is_private": shelves_are_private,
                "is_owner": is_owner,
            }
        )


class VKAppStatisticsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _absolute_url(self, request, url):
        if not url:
            return None
        url = str(url).strip()
        if not url:
            return None
        if url.startswith("//"):
            return f"{request.scheme}:{url}"
        if url.startswith(("http://", "https://")):
            return url
        if url.startswith("/"):
            return request.build_absolute_uri(url)
        return url

    def _plain_value(self, value):
        if isinstance(value, Decimal):
            if value == value.to_integral_value():
                return int(value)
            return float(value)
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: self._plain_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._plain_value(item) for item in value]
        return value

    def _book_authors(self, book):
        if not book:
            return []
        return [author.name for author in book.authors.all() if author.name]

    def _serialize_book_ref(self, request, book, cover_url=None, extra=None):
        if not book:
            return None
        authors = self._book_authors(book)
        payload = {
            "id": book.id,
            "title": book.title,
            "authors": authors,
            "author": ", ".join(authors),
            "cover_url": self._absolute_url(request, cover_url or book.get_original_cover_url() or book.get_cover_url()),
            "book_url": f"/books/{book.id}",
        }
        if extra:
            payload.update(extra)
        return payload

    def _serialize_period_book(self, request, entry):
        book = entry.get("book") if isinstance(entry, dict) else None
        return self._serialize_book_ref(
            request,
            book,
            cover_url=entry.get("cover_url") if isinstance(entry, dict) else None,
            extra={
                "format": entry.get("format") if isinstance(entry, dict) else None,
                "has_review": bool(entry.get("has_review")) if isinstance(entry, dict) else False,
                "review_url": entry.get("review_url") if isinstance(entry, dict) else None,
            },
        )

    def _serialize_calendar_book(self, request, book_payload):
        payload = self._plain_value(book_payload or {})
        if payload.get("cover_url"):
            payload["cover_url"] = self._absolute_url(request, payload.get("cover_url"))
        if payload.get("id"):
            payload["book_url"] = f"/books/{payload['id']}"
        return payload

    def _serialize_calendar_day(self, request, day):
        day_date = day.get("date") if isinstance(day, dict) else None
        payload = {
            "date": self._plain_value(day_date),
            "day": day_date.day if isinstance(day_date, date) else None,
            "in_month": bool(day.get("in_month")),
            "books": [self._serialize_calendar_book(request, book) for book in day.get("books", [])],
            "is_completion_day": bool(day.get("is_completion_day")),
            "pages_total": self._plain_value(day.get("pages_total")),
            "books_count": day.get("books_count") or 0,
            "audio_minutes": day.get("audio_minutes"),
            "audio_display": day.get("audio_display"),
            "reading_sessions": day.get("reading_sessions") or 0,
        }
        return payload

    def _serialize_calendar(self, request, calendar_payload):
        calendar_payload = calendar_payload or {}
        day_payloads = {}
        for iso_date, payload in (calendar_payload.get("day_payloads") or {}).items():
            prepared = self._plain_value(payload)
            prepared["books"] = [self._serialize_calendar_book(request, book) for book in prepared.get("books", [])]
            day_payloads[iso_date] = prepared

        completed_books = []
        for book in calendar_payload.get("completed_books") or []:
            prepared = self._plain_value(book)
            if prepared.get("cover_url"):
                prepared["cover_url"] = self._absolute_url(request, prepared.get("cover_url"))
            completed_books.append(prepared)

        return {
            "year": calendar_payload.get("year"),
            "month": calendar_payload.get("month"),
            "month_name": calendar_payload.get("month_name"),
            "weekday_labels": calendar_payload.get("weekday_labels") or [],
            "has_activity": bool(calendar_payload.get("has_activity")),
            "month_totals": self._plain_value(calendar_payload.get("month_totals") or {}),
            "weeks": [
                [self._serialize_calendar_day(request, day) for day in week]
                for week in calendar_payload.get("weeks") or []
            ],
            "day_payloads": day_payloads,
            "completed_books": completed_books,
        }

    def _serialize_pairs(self, labels, values, colors=None):
        colors = colors or []
        items = []
        for index, label in enumerate(labels or []):
            items.append(
                {
                    "label": label,
                    "value": self._plain_value((values or [])[index] if index < len(values or []) else 0),
                    "color": colors[index] if index < len(colors) else None,
                }
            )
        return items

    def _serialize_book_challenge(self, request, challenge):
        monthly_summaries = []
        for month in challenge.get("monthly_summaries") or []:
            covers = []
            for cover in month.get("covers") or []:
                book = cover.get("book")
                if not book:
                    continue
                covers.append(
                    {
                        "id": book.id,
                        "title": book.title,
                        "cover_url": self._absolute_url(request, cover.get("cover_url") or book.get_cover_url()),
                    }
                )
            monthly_summaries.append(
                {
                    "month": month.get("month"),
                    "label": month.get("label"),
                    "total": month.get("total") or 0,
                    "covers": covers,
                    "extra_count": month.get("extra_count") or 0,
                }
            )

        return {
            "year": challenge.get("year"),
            "available_years": challenge.get("available_years") or [],
            "goal": challenge.get("goal"),
            "year_books_count": challenge.get("year_books_count") or 0,
            "books_remaining": challenge.get("books_remaining"),
            "monthly_goal": challenge.get("monthly_goal"),
            "target_by_month": challenge.get("target_by_month"),
            "books_needed_this_month": challenge.get("books_needed_this_month"),
            "avg_pages_per_day": self._plain_value(challenge.get("avg_pages_per_day")),
            "recommended_pages": challenge.get("recommended_pages"),
            "month_labels": challenge.get("month_labels") or [],
            "month_values": challenge.get("month_values") or [],
            "current_month_label": challenge.get("current_month_label"),
            "monthly_summaries": monthly_summaries,
        }

    def _serialize_response(self, request, *, challenge_year=None, challenge_years=None, updated=False):
        if challenge_year is None or challenge_years is None:
            challenge_year, challenge_years = _resolve_book_challenge_year(request._request)

        stats_payload = _collect_profile_stats(request.user, request.query_params)
        stats = stats_payload.get("stats", {})
        stats_period = stats_payload.get("stats_period", {})
        calendar_payload = self._serialize_calendar(request, stats.get("reading_calendar") or {})
        book_challenge = _build_book_challenge_context(request.user, challenge_year, challenge_years)

        period_books = [
            item for item in (
                self._serialize_period_book(request, entry)
                for entry in stats.get("books") or []
            )
            if item is not None
        ]

        return {
            "updated": updated,
            "period": {
                "period": stats_period.get("period"),
                "label": stats_period.get("label"),
                "start": self._plain_value(stats_period.get("start")),
                "end": self._plain_value(stats_period.get("end")),
                "available_years": stats_period.get("available_years") or [],
                "available_months": stats_period.get("available_months") or [],
                "available_days": stats_period.get("available_days") or [],
                "selected_year": stats_period.get("selected_year"),
                "selected_month": stats_period.get("selected_month"),
                "selected_day": self._plain_value(stats_period.get("selected_day")),
            },
            "summary": {
                "pages_total": self._plain_value(stats.get("pages_total") or 0),
                "pages_average": self._plain_value(stats.get("pages_average")),
                "books_count": stats.get("books_count") or 0,
                "audio_total_display": stats.get("audio_total_display"),
                "audio_adjusted_display": stats.get("audio_adjusted_display"),
                "audio_tracked_display": stats.get("audio_tracked_display"),
            },
            "formats": self._serialize_pairs(
                stats.get("format_labels") or [],
                stats.get("format_values") or [],
                stats.get("format_palette") or [],
            ),
            "genres": self._serialize_pairs(stats.get("genre_labels") or [], stats.get("genre_values") or []),
            "calendar": calendar_payload,
            "books": period_books,
            "home_library": self._plain_value(stats.get("home_library") or {}),
            "book_challenge": self._serialize_book_challenge(request, book_challenge),
        }

    def _resolve_challenge_year_from_data(self, request):
        _, available_years = _resolve_book_challenge_year(request._request)
        today = timezone.localdate()
        raw_year = request.data.get("book_challenge_year") or request.data.get("year")
        try:
            selected_year = int(raw_year)
        except (TypeError, ValueError):
            selected_year = today.year
        if selected_year not in available_years:
            selected_year = today.year if today.year in available_years else available_years[-1]
        return selected_year, available_years

    def get(self, request, *args, **kwargs):
        return Response(self._serialize_response(request))

    def post(self, request, *args, **kwargs):
        challenge_year, challenge_years = self._resolve_challenge_year_from_data(request)
        raw_goal = str(request.data.get("book_challenge_goal") or request.data.get("goal") or "").strip()
        challenge = BookChallenge.objects.filter(user=request.user, year=challenge_year).first()

        if raw_goal:
            try:
                goal_value = int(raw_goal)
            except (TypeError, ValueError):
                return Response({"goal": ["Передайте корректное количество книг."]}, status=status.HTTP_400_BAD_REQUEST)
            if goal_value <= 0:
                return Response({"goal": ["Цель должна быть больше нуля."]}, status=status.HTTP_400_BAD_REQUEST)
            BookChallenge.objects.update_or_create(
                user=request.user,
                year=challenge_year,
                defaults={"goal": goal_value},
            )
        elif challenge:
            challenge.delete()

        return Response(
            self._serialize_response(
                request,
                challenge_year=challenge_year,
                challenge_years=challenge_years,
                updated=True,
            )
        )

class VKAppBookListCreateView(generics.ListCreateAPIView):
    pagination_class = StandardResultsSetPagination
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]
    shelf_status_codes = {
        "want": "want_to_read",
        "reading": "reading",
        "unfinished": "unfinished",
        "read": "read",
    }
    recent_reader_days = 30

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return VKAppBookCreateSerializer
        return BookListSerializer

    def _with_recent_reader_count(self, queryset):
        popular_window = timezone.now() - timedelta(days=self.recent_reader_days)
        recent_reader_count = (
            BookProgress.objects.filter(
                book=OuterRef("pk"),
                updated_at__gte=popular_window,
                book__visibility=Book.Visibility.PUBLIC,
                book__is_hidden_by_admin=False,
            )
            .values("book")
            .annotate(reader_count=Count("user", distinct=True))
            .values("reader_count")
        )

        return queryset.annotate(
            recent_reader_count=Coalesce(
                Subquery(recent_reader_count[:1]),
                Value(0),
                output_field=IntegerField(),
            )
        )

    def _apply_discovery_shelf_filter(self, queryset):
        shelf_title = (
            self.request.query_params.get("discovery_shelf")
            or self.request.query_params.get("shelf_title")
        )
        shelf_title = (shelf_title or "").strip()
        sort = (self.request.query_params.get("sort") or "").strip().lower()
        genre = (self.request.query_params.get("genre") or "").strip()

        if not shelf_title and not sort and not genre:
            return queryset

        normalized_title = shelf_title.casefold()

        if sort == "popular" or normalized_title == "популярные сейчас":
            return (
                self._with_recent_reader_count(queryset)
                .filter(recent_reader_count__gt=0)
                .order_by("-recent_reader_count", "-created_at", "-id")
            )

        if sort == "recent" or normalized_title == "недавно добавленные":
            return queryset.order_by("-created_at", "-id")

        genre_name = genre or shelf_title
        if genre_name:
            return (
                self._with_recent_reader_count(queryset.filter(genres__name__iexact=genre_name))
                .distinct()
                .order_by("-recent_reader_count", "-created_at", "title", "-id")
            )

        return queryset

    def get_queryset(self):
        queryset = (
            Book.objects.public()
            .select_related("primary_isbn")
            .prefetch_related("authors", "genres", "isbn", "publisher")
            .order_by("-created_at", "-id")
        )

        queryset = self._apply_discovery_shelf_filter(queryset)

        query = (
            self.request.query_params.get("q")
            or self.request.query_params.get("query")
            or self.request.query_params.get("search")
        )
        if query:
            cleaned = query.strip()
            if cleaned:
                queryset = queryset.filter(build_book_search_filter(cleaned)).distinct()

        return queryset

    def _attach_default_shelf_status(self, data, user):
        if not getattr(user, "is_authenticated", False):
            return

        if isinstance(data, dict):
            items = data.get("results")
        else:
            items = data

        if not isinstance(items, list):
            return

        book_ids = [item.get("id") for item in items if isinstance(item, dict)]
        status_map = get_default_shelf_status_map(user, book_ids)

        for item in items:
            if not isinstance(item, dict):
                continue

            status = status_map.get(item.get("id"))
            if not status:
                continue

            item["default_shelf_status"] = status
            api_status = self.shelf_status_codes.get(status.get("code"))
            if api_status:
                item["status"] = api_status
                item["shelf_status"] = api_status
                item["user_status"] = api_status

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        self._attach_default_shelf_status(response.data, request.user)
        return response

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        book = serializer.save()
        detail = VKAppBookDetailSerializer(book, context={"request": request})
        headers = self.get_success_headers(detail.data)
        return Response(detail.data, status=status.HTTP_201_CREATED, headers=headers)


class VKAppBookExternalSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _serialize_external_book(self, item):
        metadata = item.to_metadata_mapping()
        return {
            "id": item.external_id or "|".join(item.combined_isbns()) or item.title,
            "title": item.title,
            "subtitle": item.subtitle,
            "authors": item.authors,
            "publishers": item.publishers,
            "publish_date": item.publish_date,
            "page_count": item.number_of_pages,
            "binding": item.physical_format,
            "subjects": item.subjects,
            "languages": item.languages,
            "isbn_10": item.isbn_10,
            "isbn_13": item.isbn_13,
            "description": item.description,
            "cover_url": item.cover_url,
            "source_url": item.source_url,
            "isbn_metadata": metadata,
        }

    def get(self, request, *args, **kwargs):
        query = str(request.query_params.get("q") or "").strip()
        title = str(request.query_params.get("title") or "").strip()
        author = str(request.query_params.get("author") or "").strip()
        isbn = str(request.query_params.get("isbn") or "").strip()

        if query and not (title or author or isbn):
            title = query

        try:
            limit = int(request.query_params.get("limit") or 8)
        except (TypeError, ValueError):
            limit = 8
        limit = max(1, min(limit, 12))

        results = google_books_client.search(
            title=title or None,
            author=author or None,
            isbn=isbn or None,
            limit=limit,
        )

        return Response(
            {
                "provider": "google",
                "results": [self._serialize_external_book(item) for item in results],
                "error": google_books_client.last_error if not results else None,
            }
        )


class VKAppGenreListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        query = str(request.query_params.get("q") or "").strip()
        genres = Genre.objects.all().order_by("name")

        if query:
            genres = genres.filter(name__icontains=query)

        items = [
            {
                "id": genre.id,
                "name": genre.name,
                "slug": genre.slug,
            }
            for genre in genres
        ]

        return Response(
            {
                "count": len(items),
                "genres": items,
            }
        )


class VKAppBookDiscoveryView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        leader_books, annotated_books = _book_list_querysets()

        recent_payload = cache.get(BOOK_LIST_RECENT_DISCOVERY_CACHE_KEY)
        if recent_payload is None:
            recent_payload = build_book_list_discovery_payload(
                leader_books=leader_books,
                annotated_books=annotated_books,
                include_popular=False,
            )
            cache.set(
                BOOK_LIST_RECENT_DISCOVERY_CACHE_KEY,
                recent_payload,
                timeout=BOOK_LIST_RECENT_DISCOVERY_CACHE_TIMEOUT,
            )

        popular_payload = load_book_list_popular_discovery_snapshot()
        if popular_payload is None:
            popular_payload = cache.get(BOOK_LIST_POPULAR_DISCOVERY_CACHE_KEY)

        if popular_payload is None:
            popular_payload = build_book_list_discovery_payload(
                leader_books=leader_books,
                annotated_books=annotated_books,
                include_recent=False,
            )
            cache.set(
                BOOK_LIST_POPULAR_DISCOVERY_CACHE_KEY,
                popular_payload,
                timeout=BOOK_LIST_POPULAR_DISCOVERY_CACHE_TIMEOUT,
            )
            save_book_list_popular_discovery_snapshot(popular_payload)

        shelves = deepcopy(recent_payload.get("shelves", []))
        shelves.extend(deepcopy(popular_payload.get("shelves", [])))
        shelves = _attach_default_status_to_shelf_entries(shelves, request.user)

        return Response(
            {
                "total_books": int(recent_payload.get("total_books", 0) or 0),
                "shelves": shelves,
                "generated_at": recent_payload.get("generated_at") or popular_payload.get("generated_at"),
            }
        )


class VKAppBookDetailView(generics.RetrieveAPIView):
    serializer_class = VKAppBookDetailSerializer

    def get_queryset(self):
        return (
            Book.objects.visible_to_user(self.request.user)
            .select_related("primary_isbn")
            .prefetch_related("authors", "genres", "isbn", "publisher")
            .order_by("-created_at", "-id")
        )


class VKAppReviewListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        mine = str(request.query_params.get("mine") or request.query_params.get("user") or "").strip().lower()
        try:
            limit = int(request.query_params.get("limit") or 50)
        except (TypeError, ValueError):
            limit = 50
        limit = max(1, min(limit, 100))

        queryset = (
            Rating.objects.select_related("book", "user", "book__primary_isbn")
            .prefetch_related("book__authors")
            .filter(
                book__visibility=Book.Visibility.PUBLIC,
                book__is_hidden_by_admin=False,
            )
            .exclude(review__isnull=True)
            .exclude(review__exact="")
            .order_by("-created_at", "-id")
        )

        if mine in {"1", "true", "yes", "me", "my"}:
            queryset = queryset.filter(user=request.user)

        items = [_vk_app_rating_payload(request, rating) for rating in queryset[:limit]]

        return Response(
            {
                "count": queryset.count(),
                "items": items,
                "reviews": items,
            }
        )


class VKAppBookReviewListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    score_fields = ("score", "plot_score", "characters_score", "atmosphere_score", "art_score")

    def _get_book(self, pk):
        return get_object_or_404(
            Book.objects.visible_to_user(self.request.user)
            .select_related("primary_isbn")
            .prefetch_related("authors", "genres"),
            pk=pk,
        )

    def _book_reviews_response(self, request, book, *, status_code=status.HTTP_200_OK):
        queryset = (
            Rating.objects.filter(book=book)
            .select_related("book", "user", "book__primary_isbn")
            .prefetch_related("book__authors")
            .order_by("-created_at", "-id")
        )
        my_rating = queryset.filter(user=request.user).first()
        if not book.is_publicly_visible:
            queryset = queryset.filter(user=request.user)
        public_reviews = (
            queryset.exclude(review__isnull=True)
            .exclude(review__exact="")
            .order_by("-created_at", "-id")
        )
        items = [_vk_app_rating_payload(request, rating) for rating in public_reviews[:50]]
        my_payload = _vk_app_rating_payload(request, my_rating) if my_rating else None

        return Response(
            {
                "summary": _vk_app_rating_summary_payload(book),
                "my_review": my_payload,
                "items": items,
                "reviews": items,
            },
            status=status_code,
        )

    def get(self, request, pk, *args, **kwargs):
        return self._book_reviews_response(request, self._get_book(pk))

    def post(self, request, pk, *args, **kwargs):
        book = self._get_book(pk)
        rating, created = Rating.objects.get_or_create(book=book, user=request.user)
        previous_review = str(getattr(rating, "review", "") or "").strip()
        has_review_field = "review" in request.data or "text" in request.data or "body" in request.data

        for field_name in self.score_fields:
            if field_name not in request.data:
                continue
            score, error = _vk_app_parse_score(request.data.get(field_name))
            if error:
                return Response({field_name: [error]}, status=status.HTTP_400_BAD_REQUEST)
            setattr(rating, field_name, score)

        if has_review_field:
            review_text = (
                request.data.get("review")
                if "review" in request.data
                else request.data.get("text")
                if "text" in request.data
                else request.data.get("body")
            )
            rating.review = str(review_text or "").strip()

        has_score = any(getattr(rating, field_name, None) is not None for field_name in self.score_fields)
        has_review = bool(str(getattr(rating, "review", "") or "").strip())

        if not has_score and not has_review:
            if created:
                rating.delete()
            return Response(
                {"detail": "Добавьте оценку или текст отзыва."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rating.save()

        existing_read_date = None
        status_map = get_default_shelf_status_map(request.user, [book.pk])
        shelf_status = status_map.get(book.pk)
        if shelf_status and shelf_status.get("code") == "read":
            added_at = shelf_status.get("added_at")
            if hasattr(added_at, "date"):
                existing_read_date = added_at.date()
            elif isinstance(added_at, date):
                existing_read_date = added_at

        if has_review and book.is_publicly_visible:
            if not previous_review:
                award_for_review(request.user, rating)
            ReadBeforeBuyGame.handle_review(request.user, book, rating.review)
            move_book_to_read_shelf(request.user, book, read_date=existing_read_date)

        return self._book_reviews_response(
            request,
            book,
            status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


def _vk_app_purchase_book_payload(request, item):
    book = item.book
    return {
        "id": book.id,
        "title": book.title,
        "authors": _vk_app_book_authors(book),
        "author": _vk_app_book_authors(book),
        "cover_url": _vk_app_book_cover_url(request, book),
        "note": item.note,
        "added_at": item.added_at.isoformat() if item.added_at else None,
        "app_path": f"/books/{book.id}",
        "site_path": book.get_absolute_url() if hasattr(book, "get_absolute_url") else f"/books/{book.id}/",
    }


def _vk_app_purchase_list_payload(request, purchase_list, *, include_items=True):
    items = []
    if include_items:
        raw_items = getattr(purchase_list, "_prefetched_objects_cache", {}).get("items")
        if raw_items is None:
            raw_items = (
                purchase_list.items
                .select_related("book")
                .prefetch_related("book__authors")
                .order_by("-added_at", "-id")
            )
        items = [_vk_app_purchase_book_payload(request, item) for item in list(raw_items)]

    return {
        "id": purchase_list.id,
        "title": purchase_list.title,
        "name": purchase_list.title,
        "description": purchase_list.description,
        "books_count": int(getattr(purchase_list, "items_count", None) or purchase_list.items.count()),
        "created_at": purchase_list.created_at.isoformat() if purchase_list.created_at else None,
        "updated_at": purchase_list.updated_at.isoformat() if purchase_list.updated_at else None,
        "items": items,
        "books": items,
    }


class VKAppPurchaseListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _queryset(self, user):
        return (
            PurchaseList.objects
            .filter(user=user)
            .annotate(items_count=Count("items"))
            .prefetch_related("items__book__authors")
            .order_by("title", "id")
        )

    def get(self, request, *args, **kwargs):
        lists = [
            _vk_app_purchase_list_payload(request, purchase_list)
            for purchase_list in self._queryset(request.user)
        ]
        return Response({"results": lists, "items": lists, "purchase_lists": lists})

    def post(self, request, *args, **kwargs):
        title = str(request.data.get("title") or request.data.get("name") or "").strip()
        description = str(request.data.get("description") or "").strip()

        if not title:
            return Response({"title": ["Укажите название списка."]}, status=status.HTTP_400_BAD_REQUEST)

        purchase_list, created = PurchaseList.objects.get_or_create(
            user=request.user,
            title=title,
            defaults={"description": description},
        )
        if not created and description and purchase_list.description != description:
            purchase_list.description = description
            purchase_list.save(update_fields=["description", "updated_at"])

        return Response(
            _vk_app_purchase_list_payload(request, purchase_list),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class VKAppPurchaseListDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, request, list_id):
        return get_object_or_404(PurchaseList.objects.filter(user=request.user), pk=list_id)

    def patch(self, request, list_id, *args, **kwargs):
        purchase_list = self.get_object(request, list_id)
        title = str(request.data.get("title") or request.data.get("name") or "").strip()
        description = str(request.data.get("description") or "").strip()
        update_fields = []

        if title and purchase_list.title != title:
            if PurchaseList.objects.filter(user=request.user, title=title).exclude(pk=purchase_list.pk).exists():
                return Response({"title": ["Список с таким названием уже есть."]}, status=status.HTTP_400_BAD_REQUEST)
            purchase_list.title = title
            update_fields.append("title")

        if "description" in request.data and purchase_list.description != description:
            purchase_list.description = description
            update_fields.append("description")

        if update_fields:
            purchase_list.save(update_fields=[*update_fields, "updated_at"])

        return Response(_vk_app_purchase_list_payload(request, purchase_list))

    def delete(self, request, list_id, *args, **kwargs):
        purchase_list = self.get_object(request, list_id)
        purchase_list.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class VKAppPurchaseListItemView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_list(self, request, list_id):
        return get_object_or_404(PurchaseList.objects.filter(user=request.user), pk=list_id)

    def post(self, request, list_id, *args, **kwargs):
        purchase_list = self.get_list(request, list_id)
        raw_book_id = request.data.get("book_id") or request.data.get("book")
        if not raw_book_id:
            return Response({"book_id": ["Выберите книгу."]}, status=status.HTTP_400_BAD_REQUEST)

        book = Book.objects.visible_to_user(request.user).filter(pk=raw_book_id).first()
        if not book:
            return Response({"book_id": ["Книга не найдена."]}, status=status.HTTP_404_NOT_FOUND)

        note = str(request.data.get("note") or "").strip()
        item, created = PurchaseListItem.objects.get_or_create(
            purchase_list=purchase_list,
            book=book,
            defaults={"note": note},
        )
        if not created and note and item.note != note:
            item.note = note
            item.save(update_fields=["note"])
        purchase_list.save(update_fields=["updated_at"])

        return Response(
            {
                "success": True,
                "created": created,
                "item": _vk_app_purchase_book_payload(request, item),
                "purchase_list": _vk_app_purchase_list_payload(request, purchase_list),
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, list_id, *args, **kwargs):
        purchase_list = self.get_list(request, list_id)
        raw_book_id = request.data.get("book_id") or request.query_params.get("book_id") or request.data.get("book")
        if not raw_book_id:
            return Response({"book_id": ["Выберите книгу."]}, status=status.HTTP_400_BAD_REQUEST)

        PurchaseListItem.objects.filter(purchase_list=purchase_list, book_id=raw_book_id).delete()
        purchase_list.save(update_fields=["updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class VKAppBookShelfView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    shelf_aliases = {
        "want_to_read": "want_to_read",
        "to_read": "want_to_read",
        "planned": "want_to_read",
        "reading": "reading",
        "currently_reading": "reading",
        "in_progress": "reading",
        "library": "library",
        "home_library": "library",
        "my_library": "library",
        "read": "read",
        "finished": "read",
        "completed": "read",
        "unfinished": "unfinished",
        "not_finished": "unfinished",
        "dropped": "unfinished",
        "purchase_list": "purchase_list",
        "future_purchase": "purchase_list",
        "shopping_list": "purchase_list",
        "shopping": "purchase_list",
        "buy_later": "purchase_list",
    }

    def _normalize_shelf_status(self, value):
        raw_status = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        return self.shelf_aliases.get(raw_status)

    def _parse_date(self, value):
        if not value:
            return None, None

        if isinstance(value, date):
            return value, None

        try:
            return date.fromisoformat(str(value)), None
        except (TypeError, ValueError):
            return None, "Передайте дату в формате ГГГГ-ММ-ДД."

    def _to_bool(self, value):
        if isinstance(value, bool):
            return value

        return str(value).strip().lower() in {"1", "true", "yes", "on", "да"}

    def _get_request_value(self, request, *keys):
        for key in keys:
            if key in request.data:
                return request.data.get(key), True
        return None, False

    def _parse_optional_date_field(self, request, *keys):
        value, is_present = self._get_request_value(request, *keys)
        if not is_present:
            return None, None, False
        if value in (None, ""):
            return None, None, True

        parsed, error = self._parse_date(value)
        return parsed, error, True

    def _update_home_library_genres(self, entry, value):
        if value in (None, ""):
            entry.custom_genres.clear()
            return

        raw_items = value if isinstance(value, (list, tuple)) else str(value).split(",")
        genre_ids = []
        genre_names = []

        for raw_item in raw_items:
            if isinstance(raw_item, dict):
                raw_id = raw_item.get("id")
                raw_name = raw_item.get("name") or raw_item.get("title")
            else:
                raw_id = None
                raw_name = raw_item

            text = str(raw_name or "").strip()
            if raw_id:
                try:
                    genre_ids.append(int(raw_id))
                except (TypeError, ValueError):
                    pass
            elif text.isdigit():
                genre_ids.append(int(text))
            elif text:
                genre_names.append(text)

        genres = list(Genre.objects.filter(id__in=genre_ids))
        existing_names = {genre.name.strip().lower() for genre in genres}
        for name in genre_names:
            if name.strip().lower() in existing_names:
                continue
            genre = Genre.objects.filter(name__iexact=name).first()
            if genre is None:
                genre, _ = Genre.objects.get_or_create(name=name)
            genres.append(genre)
            existing_names.add(genre.name.strip().lower())

        entry.custom_genres.set(genres)

    def _update_home_library_entry(self, request, entry):
        text_fields = {
            "edition": ("edition", "home_library_edition", "copy_edition"),
            "language": ("language", "home_library_language", "copy_language"),
            "status": ("home_library_status", "copy_status", "library_status"),
            "location": ("location", "home_library_location", "library_location", "storage_place"),
            "shelf_section": ("shelf_section", "shelfSection", "section", "home_library_section"),
            "condition": ("condition", "home_library_condition", "copy_condition"),
            "series_name": ("series_name", "home_library_series", "library_series"),
            "disposition_note": ("disposition_note", "home_library_disposition_note", "library_disposition_note"),
            "notes": ("notes", "home_library_notes", "library_notes"),
        }
        update_fields = []

        format_value, has_format = self._get_request_value(
            request,
            "home_library_format_code",
            "format",
            "format_code",
        )
        if has_format:
            normalized_format = str(format_value or "").strip()
            valid_formats = {choice[0] for choice in HomeLibraryEntry.Format.choices}
            if normalized_format and normalized_format not in valid_formats:
                return {"format": ["Выберите корректный формат."]}
            if normalized_format and entry.format != normalized_format:
                entry.format = normalized_format
                update_fields.append("format")

        for field_name, keys in text_fields.items():
            value, is_present = self._get_request_value(request, *keys)
            if not is_present:
                continue
            cleaned_value = str(value or "").strip()
            if getattr(entry, field_name) != cleaned_value:
                setattr(entry, field_name, cleaned_value)
                update_fields.append(field_name)

        acquired_at, acquired_error, has_acquired_at = self._parse_optional_date_field(
            request,
            "acquired_at",
            "purchase_date",
        )
        if acquired_error:
            return {"purchase_date": [acquired_error]}
        if has_acquired_at and entry.acquired_at != acquired_at:
            entry.acquired_at = acquired_at
            update_fields.append("acquired_at")

        read_at, read_error, has_read_at = self._parse_optional_date_field(
            request,
            "read_at",
            "read_date",
            "date_read",
        )
        if read_error:
            return {"read_date": [read_error]}
        if has_read_at and entry.read_at != read_at:
            entry.read_at = read_at
            update_fields.append("read_at")

        for field_name, keys in {
            "is_classic": ("is_classic", "isClassic"),
            "is_disposed": ("is_disposed", "isDisposed"),
        }.items():
            value, is_present = self._get_request_value(request, *keys)
            if is_present:
                bool_value = self._to_bool(value)
                if getattr(entry, field_name) != bool_value:
                    setattr(entry, field_name, bool_value)
                    update_fields.append(field_name)

        if entry.is_disposed and not entry.disposition_note.strip():
            return {"disposition_note": ["Укажите, почему книга выбыла из коллекции."]}

        if update_fields:
            entry.save(update_fields=[*update_fields, "updated_at"])

        custom_genres, has_custom_genres = self._get_request_value(request, "custom_genres", "customGenres")
        if has_custom_genres:
            self._update_home_library_genres(entry, custom_genres)

        return None

    def _get_default_shelf(self, user, name, *, is_public=True):
        shelf, created = Shelf.objects.get_or_create(
            user=user,
            name=name,
            defaults={
                "is_default": True,
                "is_public": is_public,
            },
        )

        update_fields = []
        if not shelf.is_default:
            shelf.is_default = True
            update_fields.append("is_default")
        if created is False and shelf.is_public != is_public:
            shelf.is_public = is_public
            update_fields.append("is_public")
        if update_fields:
            shelf.save(update_fields=update_fields)

        return shelf

    def _get_or_create_purchase_list(self, request):
        raw_list_id = (
            request.data.get("purchase_list_id")
            or request.data.get("list_id")
            or request.data.get("shopping_list_id")
        )
        title = str(
            request.data.get("purchase_list_title")
            or request.data.get("list_title")
            or request.data.get("shopping_list_title")
            or request.data.get("title")
            or ""
        ).strip()

        if raw_list_id:
            purchase_list = PurchaseList.objects.filter(user=request.user, pk=raw_list_id).first()
            if purchase_list:
                return purchase_list, None
            return None, {"purchase_list_id": ["Список покупок не найден."]}

        if not title:
            title = "Будущие покупки"

        purchase_list, _ = PurchaseList.objects.get_or_create(user=request.user, title=title)
        return purchase_list, None

    def _create_or_get_active_progress(self, user, book):
        progress = (
            BookProgress.objects
            .filter(user=user, book=book, event__isnull=True, is_active=True)
            .order_by("-updated_at", "-id")
            .first()
        )
        if progress:
            return progress

        return BookProgress.objects.create(
            event=None,
            user=user,
            book=book,
            is_active=True,
            started_at=timezone.localdate(),
            finished_at=None,
            percent=Decimal("0"),
            current_page=0,
            reading_notes="",
        )

    def post(self, request, pk, *args, **kwargs):
        book = Book.objects.visible_to_user(request.user).filter(pk=pk).first()
        if not book:
            return Response({"detail": "Книга не найдена."}, status=status.HTTP_404_NOT_FOUND)

        shelf_status = self._normalize_shelf_status(
            request.data.get("status")
            or request.data.get("shelf")
            or request.data.get("state")
        )
        if not shelf_status:
            return Response(
                {"status": ["Выберите корректную полку."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        purchase_date, purchase_error, _ = self._parse_optional_date_field(
            request,
            "acquired_at",
            "purchase_date",
        )
        if purchase_error:
            return Response({"purchase_date": [purchase_error]}, status=status.HTTP_400_BAD_REQUEST)

        read_date, read_error, _ = self._parse_optional_date_field(
            request,
            "read_at",
            "read_date",
            "date_read",
        )
        if read_error:
            return Response({"read_date": [read_error]}, status=status.HTTP_400_BAD_REQUEST)

        mark_as_read = self._to_bool(request.data.get("mark_as_read"))
        progress = None
        purchase_list = None
        purchase_item = None

        ensure_default_shelves(request.user)

        with transaction.atomic():
            if shelf_status == "purchase_list":
                purchase_list, purchase_list_error = self._get_or_create_purchase_list(request)
                if purchase_list_error:
                    return Response(purchase_list_error, status=status.HTTP_400_BAD_REQUEST)
                purchase_item, _ = PurchaseListItem.objects.get_or_create(
                    purchase_list=purchase_list,
                    book=book,
                    defaults={"note": str(request.data.get("note") or "").strip()},
                )
                purchase_list.save(update_fields=["updated_at"])

            elif shelf_status == "want_to_read":
                ShelfItem.objects.filter(
                    shelf__user=request.user,
                    shelf__name__in=[
                        DEFAULT_READING_SHELF,
                        DEFAULT_UNFINISHED_SHELF,
                        *ALL_DEFAULT_READ_SHELF_NAMES,
                    ],
                    book=book,
                ).delete()
                want_shelf = self._get_default_shelf(request.user, DEFAULT_WANT_SHELF)
                ShelfItem.objects.get_or_create(shelf=want_shelf, book=book)

            elif shelf_status == "reading":
                move_book_to_reading_shelf(request.user, book)
                progress = self._create_or_get_active_progress(request.user, book)

            elif shelf_status == "library":
                home_shelf = get_home_library_shelf(request.user)
                home_item, _ = ShelfItem.objects.get_or_create(shelf=home_shelf, book=book)
                entry, _ = HomeLibraryEntry.objects.get_or_create(shelf_item=home_item)

                entry_errors = self._update_home_library_entry(request, entry)
                if entry_errors:
                    return Response(entry_errors, status=status.HTTP_400_BAD_REQUEST)

                if mark_as_read:
                    move_book_to_read_shelf(
                        request.user,
                        book,
                        read_date=read_date or timezone.localdate(),
                    )

            elif shelf_status == "read":
                move_book_to_read_shelf(
                    request.user,
                    book,
                    read_date=read_date or timezone.localdate(),
                )

            elif shelf_status == "unfinished":
                move_book_to_unfinished_shelf(request.user, book)

        data = dict(VKAppBookDetailSerializer(book, context={"request": request}).data)
        data["success"] = True
        data["status"] = shelf_status
        data["shelf"] = shelf_status

        if purchase_list:
            data["purchase_list"] = _vk_app_purchase_list_payload(request, purchase_list)
        if purchase_item:
            data["purchase_list_item"] = _vk_app_purchase_book_payload(request, purchase_item)

        if progress:
            data["progress_id"] = progress.id
            data["tracker_url"] = f"/tracker/{progress.id}/"

        return Response(data)

    def delete(self, request, pk, *args, **kwargs):
        shelf_status = self._normalize_shelf_status(
            request.data.get("status")
            or request.data.get("shelf")
            or request.data.get("state")
            or request.query_params.get("status")
            or request.query_params.get("shelf")
        )
        if not shelf_status or shelf_status == "purchase_list":
            return Response(
                {"status": ["Выберите корректную полку."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        book = Book.objects.filter(pk=pk).first()
        if not book:
            return Response(
                {"detail": "Книга не найдена."},
                status=status.HTTP_404_NOT_FOUND,
            )

        shelf_names_by_status = {
            "want_to_read": (DEFAULT_WANT_SHELF,),
            "reading": (DEFAULT_READING_SHELF,),
            "library": (DEFAULT_HOME_LIBRARY_SHELF,),
            "read": ALL_DEFAULT_READ_SHELF_NAMES,
            "unfinished": (DEFAULT_UNFINISHED_SHELF,),
        }
        deleted, _ = ShelfItem.objects.filter(
            shelf__user=request.user,
            shelf__name__in=shelf_names_by_status[shelf_status],
            book=book,
        ).delete()

        return Response(
            {
                "success": True,
                "removed": deleted > 0,
                "status": shelf_status,
                "shelf": shelf_status,
            }
        )


class VKAppBookTrackerView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _build_absolute_url(self, request, url):
        if not url:
            return ""

        if str(url).startswith(("http://", "https://", "//")):
            return url

        return request.build_absolute_uri(url)

    def _get_author_text(self, book):
        authors = [author.name for author in book.authors.all()]
        return ", ".join(author for author in authors if author) or "Автор не указан"

    def _format_date(self, value):
        if not value:
            return None

        if hasattr(value, "isoformat"):
            return value.isoformat()

        return str(value)

    def _to_float(self, value):
        if value is None:
            return None

        return float(value)

    def _to_bool(self, value):
        if isinstance(value, bool):
            return value

        return str(value).strip().lower() in {"1", "true", "yes", "on", "да"}

    def _get_completion_reward_event(self, user, book):
        content_type = ContentType.objects.get_for_model(book)
        return (
            UserPointEvent.objects.filter(
                user=user,
                event_type=UserPointEvent.EventType.BOOK_COMPLETED,
                content_type=content_type,
                object_id=book.pk,
            )
            .order_by("-created_at", "-id")
            .first()
        )

    def _serialize_completion_reward(self, event, *, awarded=False, already_awarded=False, limit_reached=False):
        points = event.points if event is not None else 0
        if points > 0 and awarded:
            reward_text = f"+{points} баллов за чтение"
        elif points > 0 and already_awarded:
            reward_text = f"+{points} баллов уже начислены"
        elif limit_reached:
            reward_text = "Лимит баллов за прочитанные книги на сегодня достигнут"
        else:
            reward_text = f"+{BOOK_COMPLETION.points} баллов за чтение"

        return {
            "points": points,
            "reward": points,
            "coins": points,
            "rewardText": reward_text,
            "reward_text": reward_text,
            "awarded": awarded,
            "already_awarded": already_awarded,
            "limit_reached": limit_reached,
        }
    def _parse_decimal(self, value):
        if value is None or value == "":
            return None, None

        try:
            return Decimal(str(value).replace(",", ".")), None
        except (InvalidOperation, TypeError, ValueError):
            return None, "Передайте корректное число."

    def _parse_int(self, value, *, default=None, minimum=None):
        if value in (None, ""):
            return default, None

        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default, "Передайте целое число."

        if minimum is not None and parsed < minimum:
            return default, f"Значение не может быть меньше {minimum}."

        return parsed, None

    def _parse_duration(self, value):
        if value in (None, ""):
            return None, None

        parts = str(value).strip().split(":")
        if len(parts) != 3:
            return None, "Используйте формат ЧЧ:ММ:СС."

        try:
            hours, minutes, seconds = (int(part) for part in parts)
        except ValueError:
            return None, "Часы, минуты и секунды должны быть числами."

        if hours < 0 or minutes < 0 or minutes >= 60 or seconds < 0 or seconds >= 60:
            return None, "Неверное значение времени."

        return timedelta(hours=hours, minutes=minutes, seconds=seconds), None

    def _format_duration(self, value):
        if not value:
            return ""

        total_seconds = int(value.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _duration_seconds(self, value):
        if not value:
            return None

        return int(value.total_seconds())

    def _parse_audio_increment_seconds(self, data):
        duration, duration_error = self._parse_duration(data.get("duration"))
        if duration_error:
            return None, duration_error
        if duration:
            return int(duration.total_seconds()), None

        minutes, minutes_error = self._parse_decimal(data.get("minutes"))
        if minutes_error:
            return None, minutes_error
        if minutes is not None:
            if minutes <= 0:
                return None, "Укажите положительное количество минут."
            seconds = (minutes * Decimal("60")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            return int(seconds), None

        seconds, seconds_error = self._parse_int(data.get("seconds"), minimum=1)
        if seconds_error:
            return None, seconds_error
        if seconds is not None:
            return seconds, None

        return None, "Укажите, сколько времени вы прослушали."

    def _get_medium_code(self, value):
        code = str(value or BookProgress.FORMAT_PAPER).strip()
        valid_codes = {choice[0] for choice in BookProgress.FORMAT_CHOICES}
        return code if code in valid_codes else None

    def _get_media_objects(self, progress):
        media = list(progress.media.all())
        if media:
            return media

        medium = progress.get_medium(progress.format or BookProgress.FORMAT_PAPER)
        return [medium] if medium else []

    def _normalize_page_totals(self, progress):
        progress.normalize_page_totals()

    def _serialize_medium(self, progress, medium, total_pages):
        choices = dict(BookProgress.FORMAT_CHOICES)
        total_for_medium = medium.total_pages_override or total_pages
        equivalent_pages = None
        if total_pages:
            equivalent_pages = progress._medium_equivalent_pages(medium, total_pages)

        payload = {
            "code": medium.medium,
            "label": choices.get(medium.medium, medium.medium),
            "current_page": medium.current_page,
            "total_pages": total_for_medium,
            "equivalent_pages": self._to_float(equivalent_pages),
            "percent": 0,
            "audio_position": None,
            "audio_position_seconds": None,
            "audio_length": None,
            "audio_length_seconds": None,
            "audio_playback_speed": None,
        }

        if medium.medium == BookProgress.FORMAT_AUDIO:
            position = medium.audio_position or progress.audio_position
            length = medium.audio_length or progress.audio_length
            speed = medium.playback_speed or progress.audio_playback_speed
            payload.update(
                {
                    "current_page": None,
                    "audio_position": self._format_duration(position),
                    "audio_position_seconds": self._duration_seconds(position),
                    "audio_length": self._format_duration(length),
                    "audio_length_seconds": self._duration_seconds(length),
                    "audio_playback_speed": self._to_float(speed),
                }
            )
            if position and length and length.total_seconds() > 0:
                percent = Decimal(str(position.total_seconds())) / Decimal(str(length.total_seconds())) * Decimal("100")
                payload["percent"] = self._to_float(percent.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) or 0
            return payload

        if total_for_medium and medium.current_page is not None:
            percent = Decimal(medium.current_page) / Decimal(total_for_medium) * Decimal("100")
            payload["percent"] = self._to_float(percent.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) or 0

        return payload

    def _get_progress(self, request, *, pk=None, progress_id=None, create_for_book=False):
        if progress_id is not None:
            return (
                BookProgress.objects
                .filter(pk=progress_id, user=request.user)
                .select_related("book")
                .prefetch_related("book__authors", "book__genres", "logs", "media", "feed_entries", "character_entries", "annotations")
                .first()
            )

        book = (
            Book.objects.visible_to_user(request.user)
            .filter(pk=pk)
            .prefetch_related("authors", "genres")
            .first()
        )
        if not book:
            return None

        progress = (
            BookProgress.objects
            .filter(user=request.user, book=book, event__isnull=True, is_active=True)
            .select_related("book")
            .prefetch_related("book__authors", "book__genres", "logs", "media", "feed_entries", "character_entries", "annotations")
            .order_by("-updated_at", "-id")
            .first()
        )
        if progress or not create_for_book:
            return progress

        move_book_to_reading_shelf(request.user, book)
        return BookProgress.objects.create(
            event=None,
            user=request.user,
            book=book,
            is_active=True,
            started_at=timezone.localdate(),
            finished_at=None,
            percent=Decimal("0"),
            current_page=0,
            reading_notes="",
        )

    def _publish_feed_entry(self, progress, *, medium_code, reaction, is_public):
        if not is_public or not progress.book.is_publicly_visible:
            return

        combined = progress.get_combined_current_pages()
        current_page = None
        if combined is not None:
            current_page = combined.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        ReadingFeedEntry.objects.create(
            progress=progress,
            user=progress.user,
            book=progress.book,
            medium=medium_code,
            current_page=current_page,
            percent=progress.percent,
            reaction=(reaction or "").strip(),
            is_public=True,
        )

    def _serialize_log(self, log):
        return {
            "id": log.id,
            "log_date": self._format_date(log.log_date),
            "medium": log.medium,
            "pages": self._to_float(log.pages_equivalent),
            "audio_seconds": log.audio_seconds,
        }

    def _serialize_feed_entry(self, entry):
        return {
            "id": entry.id,
            "created_at": self._format_date(entry.created_at),
            "current_page": self._to_float(entry.current_page),
            "percent": self._to_float(entry.percent),
            "reaction": entry.reaction,
            "is_public": entry.is_public,
        }

    def _serialize_character(self, character):
        return {
            "id": character.id,
            "name": character.name,
            "description": character.description,
            "created_at": self._format_date(character.created_at),
        }

    def _serialize_annotation(self, annotation):
        return {
            "id": annotation.id,
            "kind": annotation.kind,
            "body": annotation.body,
            "location": annotation.location,
            "comment": annotation.comment,
            "created_at": self._format_date(annotation.created_at),
            "updated_at": self._format_date(annotation.updated_at),
        }

    def _get_tracker_statistics(self, progress):
        choices = dict(BookProgress.FORMAT_CHOICES)
        tracked_mediums = [
            BookProgress.FORMAT_PAPER,
            BookProgress.FORMAT_EBOOK,
        ]

        daily_rows = OrderedDict()
        for log in progress.logs.order_by("log_date", "medium"):
            if log.medium not in tracked_mediums:
                continue

            row = daily_rows.setdefault(
                log.log_date,
                {
                    "date": self._format_date(log.log_date),
                    "label": log.log_date.strftime("%d.%m.%Y"),
                    "total_pages": Decimal("0"),
                    "mediums": {code: Decimal("0") for code in tracked_mediums},
                },
            )
            pages_value = log.pages_equivalent or Decimal("0")
            row["total_pages"] += pages_value
            row["mediums"][log.medium] += pages_value

        daily_stats = []
        for row in daily_rows.values():
            daily_stats.append(
                {
                    "date": row["date"],
                    "label": row["label"],
                    "total_pages": self._to_float(row["total_pages"]) or 0,
                    "mediums": {
                        code: self._to_float(value) or 0
                        for code, value in row["mediums"].items()
                    },
                }
            )

        format_totals = {
            code: Decimal("0")
            for code, _ in BookProgress.FORMAT_CHOICES
        }
        for row in (
            progress.logs
            .order_by()
            .values("medium")
            .annotate(total_pages=Sum("pages_equivalent"))
            .values("medium", "total_pages")
        ):
            medium_code = row.get("medium")
            if medium_code not in format_totals:
                continue
            total_value = row.get("total_pages") or Decimal("0")
            if not isinstance(total_value, Decimal):
                total_value = Decimal(str(total_value))
            format_totals[medium_code] += total_value

        palette = {
            BookProgress.FORMAT_PAPER: "#9b7d61",
            BookProgress.FORMAT_EBOOK: "#daa38f",
            BookProgress.FORMAT_AUDIO: "#92ada4",
        }
        total_equivalent = sum(format_totals.values(), Decimal("0"))
        format_stats = []
        if total_equivalent > 0:
            for medium_code in (
                BookProgress.FORMAT_PAPER,
                BookProgress.FORMAT_EBOOK,
                BookProgress.FORMAT_AUDIO,
            ):
                pages_value = format_totals.get(medium_code) or Decimal("0")
                if pages_value <= 0:
                    continue
                percent = (pages_value / total_equivalent * Decimal("100")).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
                format_stats.append(
                    {
                        "code": medium_code,
                        "label": choices.get(medium_code, medium_code),
                        "pages": self._to_float(pages_value) or 0,
                        "percent": self._to_float(percent) or 0,
                        "color": palette.get(medium_code, "#4dabf7"),
                    }
                )

        return {
            "daily": daily_stats,
            "formats": format_stats,
        }

    def _serialize_progress(self, request, progress):
        book = progress.book
        total_pages = progress.get_effective_total_pages()
        combined_pages = progress.get_combined_current_pages()
        percent = progress.percent or Decimal("0")
        if total_pages and combined_pages is not None:
            percent = (combined_pages / Decimal(total_pages) * Decimal("100")).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            percent = min(Decimal("100"), percent)
        cover_url = book.get_original_cover_url()
        logs = progress.logs.order_by("-log_date", "-id")[:20]
        feed_entries = progress.feed_entries.order_by("-created_at", "-id")[:10]
        characters = progress.character_entries.order_by("created_at", "id")
        quotes = progress.annotations.filter(kind=ProgressAnnotation.KIND_QUOTE).order_by("-created_at", "-id")
        note_entries = progress.annotations.filter(kind=ProgressAnnotation.KIND_NOTE).order_by("-created_at", "-id")
        media = [self._serialize_medium(progress, medium, total_pages) for medium in self._get_media_objects(progress)]
        statistics = self._get_tracker_statistics(progress)

        return {
            "id": progress.id,
            "book": {
                "id": book.id,
                "title": book.title,
                "author": self._get_author_text(book),
                "cover_url": self._build_absolute_url(request, cover_url),
                "total_pages": book.get_total_pages(),
            },
            "current_page": progress.current_page,
            "combined_current_page": self._to_float(combined_pages),
            "percent": self._to_float(percent) or 0,
            "total_pages": total_pages,
            "pages_left": self._to_float(progress.pages_left),
            "average_pages_per_day": self._to_float(progress.average_pages_per_day),
            "estimated_days_remaining": progress.estimated_days_remaining,
            "started_at": self._format_date(progress.started_at),
            "finished_at": self._format_date(progress.finished_at),
            "updated_at": self._format_date(progress.updated_at),
            "is_active": progress.is_active,
            "reading_notes": progress.reading_notes,
            "format": progress.format,
            "format_label": progress.get_format_display(),
            "format_choices": [
                {"code": code, "label": label}
                for code, label in BookProgress.FORMAT_CHOICES
            ],
            "active_formats": [medium["code"] for medium in media],
            "custom_total_pages": progress.custom_total_pages,
            "media": media,
            "tracker_url": f"/tracker/{progress.id}/",
            "logs": [self._serialize_log(log) for log in logs],
            "feed_entries": [self._serialize_feed_entry(entry) for entry in feed_entries],
            "characters": [self._serialize_character(character) for character in characters],
            "quotes": [self._serialize_annotation(quote) for quote in quotes],
            "note_entries": [self._serialize_annotation(note) for note in note_entries],
            "statistics": statistics,
        }

    def _apply_page_update(self, progress, *, medium_code=BookProgress.FORMAT_PAPER, page=None, percent=None, delta=None, reaction="", is_public=True):
        if medium_code == BookProgress.FORMAT_AUDIO:
            return "Для аудиокниги укажите прослушанные минуты или время."

        medium = progress.get_medium(medium_code)
        if not medium:
            return "Сначала активируйте выбранный формат в настройках прогресса."

        book_total_pages = progress.book.get_total_pages() if progress.book else None
        total_pages = medium.total_pages_override or book_total_pages or progress.custom_total_pages
        previous_page = medium.current_page or 0

        if delta is not None:
            new_page = previous_page + int(delta)
        elif percent is not None:
            if percent < 0 or percent > Decimal("100"):
                return "Процент должен быть от 0 до 100."
            if not total_pages:
                return "Для обновления по проценту нужно количество страниц."
            new_page = int((Decimal(total_pages) * percent / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        elif page is not None:
            new_page = int(page)
        else:
            return "Передайте страницу, процент или шаг."

        if total_pages:
            new_page = max(0, min(new_page, int(total_pages)))
        else:
            new_page = max(0, new_page)

        medium.current_page = new_page
        update_fields = ["current_page"]
        if not book_total_pages and medium.total_pages_override is None and progress.custom_total_pages:
            medium.total_pages_override = progress.custom_total_pages
            update_fields.append("total_pages_override")
        medium.save(update_fields=update_fields)

        denominator = medium.total_pages_override or book_total_pages or total_pages or progress.get_effective_total_pages()

        def _percent_from_page(page_value):
            if denominator and denominator > 0:
                return (Decimal(page_value) / Decimal(denominator) * Decimal("100")).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
            return Decimal("0")

        def _equivalent_from_percent(percent_value):
            base_total = progress.get_effective_total_pages()
            if base_total:
                return (Decimal(base_total) * percent_value / Decimal("100")).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
            if denominator:
                return (Decimal(denominator) * percent_value / Decimal("100")).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
            return Decimal("0")

        previous_percent = _percent_from_page(previous_page)
        new_percent = percent if percent is not None else _percent_from_page(new_page)
        previous_equivalent = _equivalent_from_percent(previous_percent)
        new_equivalent = _equivalent_from_percent(new_percent)
        delta_equivalent = max(Decimal("0"), new_equivalent - previous_equivalent)
        progress_changed = delta_equivalent > 0 or new_percent > previous_percent

        if delta_equivalent > 0:
            progress.record_pages(delta_equivalent, medium=medium_code)

        if new_percent > previous_percent:
            progress.sync_media_equivalents(
                source_medium=medium_code,
                percent_complete=new_percent,
            )

        progress.refresh_current_page()
        progress.recalc_percent()

        if progress_changed:
            self._publish_feed_entry(
                progress,
                medium_code=medium_code,
                reaction=reaction,
                is_public=is_public,
            )

        return None

    def _apply_audio_update(self, progress, *, seconds, reaction="", is_public=True):
        medium = progress.get_medium(BookProgress.FORMAT_AUDIO)
        if not medium:
            return "Сначала активируйте аудиоформат в настройках прогресса."

        previous_position = medium.audio_position or progress.audio_position or timedelta()
        previous_seconds = int(previous_position.total_seconds())
        playback_speed = progress.get_effective_playback_speed(medium)
        adjusted_seconds = (Decimal(seconds) * playback_speed).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        new_seconds = previous_seconds + int(adjusted_seconds)
        audio_length = medium.audio_length or progress.audio_length
        if audio_length:
            new_seconds = min(new_seconds, int(audio_length.total_seconds()))

        medium.audio_position = timedelta(seconds=new_seconds)
        medium.audio_length = audio_length
        update_fields = ["audio_position", "audio_length"]
        if not medium.playback_speed and progress.audio_playback_speed:
            medium.playback_speed = progress.audio_playback_speed
            update_fields.append("playback_speed")
        medium.save(update_fields=update_fields)

        progress.audio_position = medium.audio_position
        progress.save(update_fields=["audio_position"])

        total_base = progress.get_effective_total_pages()

        def _percent_from_seconds(value_seconds):
            if not audio_length:
                return Decimal("0")
            length_decimal = Decimal(str(audio_length.total_seconds()))
            if length_decimal <= 0:
                return Decimal("0")
            return (Decimal(value_seconds) / length_decimal * Decimal("100")).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

        def _equivalent_from_percent(percent_value):
            if total_base:
                return (Decimal(total_base) * percent_value / Decimal("100")).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
            return Decimal("0")

        previous_percent = _percent_from_seconds(previous_seconds)
        new_percent = _percent_from_seconds(new_seconds)
        previous_equivalent = _equivalent_from_percent(previous_percent)
        new_equivalent = _equivalent_from_percent(new_percent)
        delta_pages = max(Decimal("0"), new_equivalent - previous_equivalent)
        delta_seconds = max(0, new_seconds - previous_seconds)
        progress_changed = False

        if delta_pages > 0 and delta_seconds > 0:
            progress.record_pages(delta_pages, medium=BookProgress.FORMAT_AUDIO, audio_seconds=delta_seconds)

        if new_percent > previous_percent:
            progress.sync_media_equivalents(
                source_medium=BookProgress.FORMAT_AUDIO,
                percent_complete=new_percent,
            )
            progress_changed = True

        progress.refresh_current_page()
        progress.recalc_percent()

        if progress_changed:
            self._publish_feed_entry(
                progress,
                medium_code=BookProgress.FORMAT_AUDIO,
                reaction=reaction,
                is_public=is_public,
            )

        return None

    def _configure_formats(self, progress, data):
        raw_formats = data.get("formats")
        if isinstance(raw_formats, str):
            formats = [raw_formats]
        elif isinstance(raw_formats, (list, tuple)):
            formats = [str(item) for item in raw_formats]
        else:
            formats = []

        valid_codes = {choice[0] for choice in BookProgress.FORMAT_CHOICES}
        formats = [code for code in formats if code in valid_codes]
        if not formats:
            return "Выберите хотя бы один формат."

        custom_total_pages, error = self._parse_int(data.get("custom_total_pages"), minimum=1)
        if error:
            return error
        paper_total, error = self._parse_int(data.get("paper_total_pages"), minimum=1)
        if error:
            return error
        paper_page, error = self._parse_int(data.get("paper_current_page"), minimum=0)
        if error:
            return error
        ebook_total, error = self._parse_int(data.get("ebook_total_pages"), minimum=1)
        if error:
            return error
        ebook_page, error = self._parse_int(data.get("ebook_current_page"), minimum=0)
        if error:
            return error

        audio_length, error = self._parse_duration(data.get("audio_length"))
        if error:
            return error
        audio_position, error = self._parse_duration(data.get("audio_position"))
        if error:
            return error
        audio_speed, error = self._parse_decimal(data.get("audio_playback_speed"))
        if error:
            return error
        if audio_speed is not None and (audio_speed < Decimal("0.5") or audio_speed > Decimal("3.0")):
            return "Скорость аудио должна быть от 0.5 до 3.0."
        if audio_position and audio_length and audio_position > audio_length:
            return "Прогресс аудио не может превышать длительность."
        if audio_position and not audio_length:
            return "Укажите длительность, если задан прогресс аудио."

        book_total_pages = progress.book.get_total_pages() if progress.book else None
        if book_total_pages:
            progress.custom_total_pages = None
        elif custom_total_pages:
            progress.custom_total_pages = custom_total_pages
        else:
            progress.custom_total_pages = paper_total or ebook_total or progress.custom_total_pages

        progress.format = formats[0]
        if BookProgress.FORMAT_AUDIO in formats:
            progress.audio_length = audio_length
            progress.audio_position = audio_position
            progress.audio_playback_speed = audio_speed or Decimal("1.0")
        else:
            progress.audio_length = None
            progress.audio_position = None
            progress.audio_playback_speed = None
        progress.save()

        existing = {medium.medium: medium for medium in progress.media.all()}
        for medium_code, medium in list(existing.items()):
            if medium_code not in formats:
                medium.delete()
                existing.pop(medium_code, None)

        for medium_code in formats:
            medium = existing.get(medium_code) or BookProgressMedium(progress=progress, medium=medium_code)
            if medium_code == BookProgress.FORMAT_PAPER:
                medium.current_page = paper_page
                medium.total_pages_override = None if book_total_pages else paper_total or progress.custom_total_pages
                medium.audio_position = None
                medium.audio_length = None
                medium.playback_speed = None
            elif medium_code == BookProgress.FORMAT_EBOOK:
                medium.current_page = ebook_page
                medium.total_pages_override = ebook_total or progress.custom_total_pages
                medium.audio_position = None
                medium.audio_length = None
                medium.playback_speed = None
            elif medium_code == BookProgress.FORMAT_AUDIO:
                medium.current_page = None
                medium.total_pages_override = None
                medium.audio_length = audio_length
                medium.audio_position = audio_position
                medium.playback_speed = audio_speed or Decimal("1.0")
            medium.save()

        combined = progress.get_combined_current_pages()
        progress.current_page = (
            int(combined.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if combined is not None
            else None
        )
        progress.save(update_fields=["current_page"])
        progress.normalize_page_totals()
        progress.recalc_percent()
        return None

    def get(self, request, pk=None, progress_id=None, *args, **kwargs):
        progress = self._get_progress(request, pk=pk, progress_id=progress_id, create_for_book=True)
        if not progress:
            return Response({"detail": "Трекер не найден."}, status=status.HTTP_404_NOT_FOUND)

        self._normalize_page_totals(progress)
        return Response(self._serialize_progress(request, progress))

    def post(self, request, pk=None, progress_id=None, *args, **kwargs):
        progress = self._get_progress(request, pk=pk, progress_id=progress_id, create_for_book=True)
        if not progress:
            return Response({"detail": "Трекер не найден."}, status=status.HTTP_404_NOT_FOUND)

        self._normalize_page_totals(progress)
        action = str(request.data.get("action") or "set_page").strip()
        reaction = str(request.data.get("reaction") or "").strip()
        is_public = self._to_bool(request.data.get("is_public", True))
        medium_code = self._get_medium_code(request.data.get("medium"))
        if not medium_code:
            return Response({"medium": ["Неизвестный формат."]}, status=status.HTTP_400_BAD_REQUEST)
        error = None
        completion_reward = None

        with transaction.atomic():
            if action == "set_page":
                if medium_code == BookProgress.FORMAT_AUDIO:
                    return Response({"medium": ["Для аудио используйте добавление прослушанного времени."]}, status=status.HTTP_400_BAD_REQUEST)

                percent_value, percent_error = self._parse_decimal(request.data.get("percent"))
                if percent_error:
                    return Response({"percent": [percent_error]}, status=status.HTTP_400_BAD_REQUEST)

                raw_page = request.data.get("page")
                page = None
                if raw_page not in (None, ""):
                    try:
                        page = int(raw_page)
                    except (TypeError, ValueError):
                        return Response({"page": ["Передайте корректную страницу."]}, status=status.HTTP_400_BAD_REQUEST)

                error = self._apply_page_update(
                    progress,
                    medium_code=medium_code,
                    page=page,
                    percent=percent_value,
                    reaction=reaction,
                    is_public=is_public,
                )

            elif action == "increment":
                if medium_code == BookProgress.FORMAT_AUDIO:
                    seconds, seconds_error = self._parse_audio_increment_seconds(request.data)
                    if seconds_error:
                        return Response({"duration": [seconds_error]}, status=status.HTTP_400_BAD_REQUEST)

                    error = self._apply_audio_update(
                        progress,
                        seconds=seconds,
                        reaction=reaction,
                        is_public=is_public,
                    )
                else:
                    try:
                        delta = int(request.data.get("delta", 0))
                    except (TypeError, ValueError):
                        return Response({"delta": ["Передайте корректный шаг."]}, status=status.HTTP_400_BAD_REQUEST)

                    error = self._apply_page_update(
                        progress,
                        medium_code=medium_code,
                        delta=delta,
                        reaction=reaction,
                        is_public=is_public,
                    )

            elif action in {"formats", "configure_formats"}:
                error = self._configure_formats(progress, request.data)

            elif action == "notes":
                progress.reading_notes = str(request.data.get("reading_notes") or "")
                progress.save(update_fields=["reading_notes", "updated_at"])

            elif action == "add_character":
                name = str(request.data.get("name") or "").strip()
                description = str(request.data.get("description") or "").strip()
                if not name:
                    return Response({"name": ["Укажите имя героя."]}, status=status.HTTP_400_BAD_REQUEST)
                CharacterNote.objects.create(
                    progress=progress,
                    name=name,
                    description=description,
                )

            elif action == "update_character":
                character_id = request.data.get("character_id")
                try:
                    character_id = int(character_id)
                except (TypeError, ValueError):
                    return Response(
                        {"character_id": ["Передайте корректного героя."]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                character = progress.character_entries.filter(pk=character_id).first()
                if character is None:
                    return Response(
                        {"character_id": ["Герой не найден в этом трекере."]},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                name = str(request.data.get("name") or "").strip()
                description = str(request.data.get("description") or "").strip()
                if not name:
                    return Response({"name": ["Укажите имя героя."]}, status=status.HTTP_400_BAD_REQUEST)

                character.name = name
                character.description = description
                character.save(update_fields=["name", "description"])

            elif action == "add_quote":
                body = str(request.data.get("body") or "").strip()
                location = str(request.data.get("location") or "").strip()
                comment = str(request.data.get("comment") or "").strip()
                if not body:
                    return Response({"body": ["Введите текст цитаты."]}, status=status.HTTP_400_BAD_REQUEST)
                ProgressAnnotation.objects.create(
                    progress=progress,
                    kind=ProgressAnnotation.KIND_QUOTE,
                    body=body,
                    location=location,
                    comment=comment,
                )

            elif action == "add_note_entry":
                body = str(request.data.get("body") or "").strip()
                location = str(request.data.get("location") or "").strip()
                comment = str(request.data.get("comment") or "").strip()
                if not body:
                    return Response({"body": ["Введите текст заметки."]}, status=status.HTTP_400_BAD_REQUEST)
                ProgressAnnotation.objects.create(
                    progress=progress,
                    kind=ProgressAnnotation.KIND_NOTE,
                    body=body,
                    location=location,
                    comment=comment,
                )

            elif action == "finish":
                for medium in self._get_media_objects(progress):
                    if medium.medium == BookProgress.FORMAT_AUDIO:
                        audio_length = medium.audio_length or progress.audio_length
                        if audio_length:
                            medium.audio_length = audio_length
                            medium.audio_position = audio_length
                            update_fields = ["audio_length", "audio_position"]
                            if not medium.playback_speed and progress.audio_playback_speed:
                                medium.playback_speed = progress.audio_playback_speed
                                update_fields.append("playback_speed")
                            medium.save(update_fields=update_fields)
                            progress.audio_position = audio_length
                            progress.save(update_fields=["audio_position"])
                        continue

                    total_pages = (
                        medium.total_pages_override
                        or (progress.book.get_total_pages() if progress.book else None)
                        or progress.custom_total_pages
                        or progress.get_effective_total_pages()
                    )
                    if total_pages:
                        error = self._apply_page_update(
                            progress,
                            medium_code=medium.medium,
                            page=int(total_pages),
                            reaction=reaction,
                            is_public=is_public,
                        )
                if not error:
                    if progress.percent < Decimal("100"):
                        progress.percent = Decimal("100")
                    if progress.finished_at is None:
                        progress.finished_at = timezone.localdate()
                    if progress.started_at is None:
                        progress.started_at = timezone.localdate()
                    progress.save(update_fields=["percent", "finished_at", "started_at", "updated_at"])
                    move_book_to_read_shelf(request.user, progress.book, read_date=timezone.localdate())
                    completion_event = award_for_book_completion(request.user, progress.book)
                    if completion_event is not None:
                        completion_reward = self._serialize_completion_reward(completion_event, awarded=True)
                    else:
                        existing_event = self._get_completion_reward_event(request.user, progress.book)
                        completion_reward = self._serialize_completion_reward(
                            existing_event,
                            awarded=False,
                            already_awarded=existing_event is not None,
                            limit_reached=existing_event is None,
                        )
            elif action == "unfinished":
                move_book_to_unfinished_shelf(request.user, progress.book)

            else:
                return Response({"action": ["Неизвестное действие."]}, status=status.HTTP_400_BAD_REQUEST)

        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        progress.refresh_from_db()
        data = self._serialize_progress(request, progress)
        if completion_reward is not None:
            data["completion_reward"] = completion_reward
        return Response(data)









