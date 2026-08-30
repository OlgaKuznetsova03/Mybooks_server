import hashlib
import re
import secrets

from django.conf import settings
from django.db import transaction
from django.db.models import Count, DecimalField, IntegerField, Max, Min, OuterRef, Prefetch, Q, Subquery, Sum, Value
from django.contrib.auth import authenticate, get_user_model
from datetime import timedelta
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import services as account_services
from accounts.models import CoinTransaction, Profile
from accounts.services import (
    ANNUAL_GAME_REPORT_GENERATION_COST,
    FEATURE_ACCESS_COST,
    InsufficientCoinsError,
    REVIEW_IMAGE_BACKGROUND_COST,
    REVIEW_IMAGE_GENERATION_COST,
    CURRENT_READING_IMAGE_BACKGROUND_COST,
    CURRENT_READING_IMAGE_GENERATION_COST,
    RANDOM_BOOK_SELECTION_COST,
    TRACKER_STORY_BACKGROUND_COST,
    TRACKER_STORY_GENERATION_COST,
    charge_feature_access,
    get_feature_payment_context,
)
from books.models import Book, Rating
from books.utils import build_book_search_filter
from reading_clubs.models import (
    DiscussionPost,
    DiscussionPostReport,
    DiscussionRead,
    ReadingClub,
    ReadingNorm,
    ReadingParticipant,
)
from reading_clubs.services import mark_topic_read
from reading_marathons.models import MarathonEntry, MarathonParticipant, MarathonTheme, ReadingMarathon
from shelves.models import BookProgress, ReadingLog, Shelf, ShelfItem
from shelves.services import (
    ALL_DEFAULT_READ_SHELF_NAMES,
    DEFAULT_HOME_LIBRARY_SHELF,
    DEFAULT_READING_SHELF,
    DEFAULT_WANT_SHELF,
    READING_PROGRESS_LABEL,
    ensure_default_shelves,
    move_book_to_reading_shelf,
)

from .authentication import issue_mobile_token
from .pagination import StandardResultsSetPagination
from .serializers import (
    BookCreateSerializer,
    BookDetailSerializer,
    BookListSerializer,
    MobileAuthSerializer,
    MobileSignupSerializer,
    ReadingClubCreateSerializer,
    ReadingClubDetailSerializer,
    ReadingClubTopicCreateSerializer,
    ReadingClubTopicDetailSerializer,
    DiscussionPostReportCreateSerializer,
    MarathonEntryCreateSerializer,
    MarathonEntryUpdateSerializer,
    ReadingMarathonCreateSerializer,
    ReadingMarathonDetailSerializer,
    ReadingClubSerializer,
    ReadingMarathonSerializer,
    ReadingShelfItemSerializer,
    ReadingUpdateSerializer,
)
from user_ratings.services import award_for_discussion_post, award_for_marathon_confirmation


MONTHLY_SUMMARY_GENERATION_COST = getattr(
    account_services,
    "MONTHLY_SUMMARY_GENERATION_COST",
    60,
)
MONTHLY_SUMMARY_BACKGROUND_COST = getattr(
    account_services,
    "MONTHLY_SUMMARY_BACKGROUND_COST",
    5,
)
READING_CALENDAR_GENERATION_COST = getattr(
    account_services,
    "READING_CALENDAR_GENERATION_COST",
    50,
)
READING_CALENDAR_BACKGROUND_COST = getattr(
    account_services,
    "READING_CALENDAR_BACKGROUND_COST",
    5,
)
REVIEW_IMAGE_BACKGROUNDS = tuple(
    getattr(
        settings,
        "REVIEW_IMAGE_BACKGROUNDS",
        (
            "https://s3.ru1.storage.beget.cloud/0a648590a767-openhearted-anastasiya/reviews/review1.webp",
            "https://s3.ru1.storage.beget.cloud/0a648590a767-openhearted-anastasiya/reviews/review2.webp",
        ),
    )
)


class HealthView(APIView):
    """Basic liveness probe for the mobile API."""

    def get(self, request, *args, **kwargs):
        return Response(
            {
                "status": "ok",
                "service": "mybooks-api",
                "timestamp": timezone.now(),
            }
        )


class FeatureMapView(APIView):
    """High-level map of available API domains for the new client."""

    def get(self, request, *args, **kwargs):
        return Response(
            {
                "books": {
                    "description": "Каталог книг, карточки и привязанные подборки.",
                    "endpoints": [
                        {"path": "/api/v1/books/", "status": "ready"},
                        {"path": "/api/v1/books/{id}/", "status": "ready"},
                        {"path": "/api/v1/books/{id}/rate/", "status": "planned"},
                    ],
                },
                "communities": {
                    "description": "Читательские клубы, марафоны и коллаборации.",
                    "endpoints": [
                        {"path": "/api/v1/reading-clubs/", "status": "ready"},
                        {"path": "/api/v1/marathons/", "status": "ready"},
                        {"path": "/api/v1/collaborations/", "status": "planned"},
                    ],
                },
                "games": {
                    "description": "Игры, квизы и геймификация.",
                    "endpoints": [
                        {"path": "/api/v1/games/", "status": "planned"},
                        {"path": "/api/v1/games/{id}/start/", "status": "planned"},
                    ],
                },
                "profile": {
                    "description": "Профиль пользователя, подписки и награды.",
                    "endpoints": [
                        {"path": "/api/v1/profile/", "status": "planned"},
                        {"path": "/api/v1/profile/subscription/", "status": "planned"},
                    ],
                },
                "home": {
                    "description": "Данные главной страницы с акцентом на активные сообщества и личный прогресс.",
                    "endpoints": [
                        {"path": "/api/v1/home/", "status": "ready"},
                    ],
                },
            }
        )


class MobileLoginView(APIView):
    """Token login for Flutter app using the same credentials as the website."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = MobileAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request,
            username=serializer.validated_data["login"],
            password=serializer.validated_data["password"],
        )
        if not user:
            return Response(
                {"detail": "Неверный логин или пароль."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token = issue_mobile_token(user, rotate=True)
        return Response(
            {
                "token": token,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                },
            }
        )


class MobileSignupView(APIView):
    """Register account from the app and return auth token for website/app reuse."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = MobileSignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_model = get_user_model()
        user = user_model.objects.create_user(
            username=serializer.validated_data["username"],
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        token = issue_mobile_token(user)

        return Response(
            {
                "token": token,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class BookListView(generics.ListCreateAPIView):
    """Lightweight list of books for the new mobile client."""

    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self):
        if self.request.method == "POST":
            return BookCreateSerializer
        return BookListSerializer

    def get_queryset(self):
        queryset = (
            Book.objects.public()
            .select_related("primary_isbn")
            .prefetch_related("authors", "genres", "isbn")
            .order_by("-created_at", "-id")
        )
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

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        book = serializer.save()
        detail = BookDetailSerializer(book, context={"request": request})
        headers = self.get_success_headers(detail.data)
        return Response(detail.data, status=status.HTTP_201_CREATED, headers=headers)


class CommunityCreationPaymentView(APIView):
    """Return the current price and the user's ability to create a community."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        return Response(
            {
                "feature": "community_creation",
                **get_feature_payment_context(profile),
            }
        )


class TrackerStoryPaymentView(APIView):
    """Quote and charge the two paid tracker story operations."""

    permission_classes = [permissions.IsAuthenticated]

    actions = {
        "generate": {
            "feature": "tracker_story_generation",
            "cost": TRACKER_STORY_GENERATION_COST,
            "description": "Генерация изображения «Для истории»",
        },
        "change_background": {
            "feature": "tracker_story_background",
            "cost": TRACKER_STORY_BACKGROUND_COST,
            "description": "Смена фона изображения «Для истории»",
        },
    }

    def _get_progress(self, request, progress_id):
        return get_object_or_404(
            BookProgress.objects.select_related("book"),
            pk=progress_id,
            user=request.user,
        )

    def _payment_payload(self, profile, action):
        action_config = self.actions[action]
        payment_context = get_feature_payment_context(
            profile,
            cost=action_config["cost"],
        )
        return {
            "action": action,
            "feature": action_config["feature"],
            **payment_context,
            "balance": payment_context["coin_balance"],
            "unlimited": payment_context["has_unlimited_coins"],
        }

    def get(self, request, progress_id, *args, **kwargs):
        self._get_progress(request, progress_id)
        profile, _ = Profile.objects.get_or_create(user=request.user)
        return Response(
            {
                "feature": "tracker_story",
                "generation": self._payment_payload(profile, "generate"),
                "background": self._payment_payload(profile, "change_background"),
            }
        )

    def post(self, request, progress_id, *args, **kwargs):
        progress = self._get_progress(request, progress_id)
        action = str(request.data.get("action") or "").strip()
        if action not in self.actions:
            return Response(
                {"detail": "Неизвестная платная операция."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        operation_id = str(request.data.get("operation_id") or "").strip()
        if not operation_id or len(operation_id) > 64 or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for character in operation_id
        ):
            return Response(
                {"detail": "Передайте корректный идентификатор операции."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        action_config = self.actions[action]
        marker = f"[op:{action}:{operation_id}]"

        with transaction.atomic():
            profile, _ = Profile.objects.get_or_create(user=request.user)
            profile = Profile.objects.select_for_update().get(pk=profile.pk)
            balance_before = profile.coin_balance
            existing_transaction = (
                CoinTransaction.objects
                .filter(
                    profile=profile,
                    transaction_type=CoinTransaction.Type.FEATURE_PURCHASE,
                    description__contains=marker,
                )
                .order_by("-id")
                .first()
            )

            if existing_transaction is None:
                try:
                    charge_result = charge_feature_access(
                        profile,
                        cost=action_config["cost"],
                        description=(
                            f'{marker} {action_config["description"]}: «{progress.book.title}»'
                        )[:255],
                    )
                except InsufficientCoinsError as exc:
                    return Response(
                        {
                            "detail": str(exc),
                            **self._payment_payload(profile, action),
                        },
                        status=status.HTTP_402_PAYMENT_REQUIRED,
                    )
                coin_transaction = charge_result.transaction
                duplicate = False
            else:
                coin_transaction = existing_transaction
                duplicate = True

            profile.refresh_from_db(fields=("coins",))

        payment = self._payment_payload(profile, action)
        return Response(
            {
                **payment,
                "success": True,
                "duplicate": duplicate,
                "charged": not coin_transaction.unlimited,
                "balance_before": balance_before,
                "balance_after": payment["coin_balance"],
                "transaction_id": coin_transaction.pk,
            }
        )


class MonthlySummaryPaymentView(APIView):
    """Quote and charge statistics image generation and background changes."""

    permission_classes = [permissions.IsAuthenticated]

    actions = {
        "generate": {
            "feature": "monthly_summary_generation",
            "cost": MONTHLY_SUMMARY_GENERATION_COST,
        },
        "change_background": {
            "feature": "monthly_summary_background",
            "cost": MONTHLY_SUMMARY_BACKGROUND_COST,
        },
        "generate_calendar": {
            "feature": "reading_calendar_generation",
            "cost": READING_CALENDAR_GENERATION_COST,
        },
        "change_calendar_background": {
            "feature": "reading_calendar_background",
            "cost": READING_CALENDAR_BACKGROUND_COST,
        },
    }

    def _payment_payload(self, profile, action="generate"):
        action_config = self.actions[action]
        payment_context = get_feature_payment_context(
            profile,
            cost=action_config["cost"],
        )
        return {
            "action": action,
            "feature": action_config["feature"],
            **payment_context,
            "balance": payment_context["coin_balance"],
            "unlimited": payment_context["has_unlimited_coins"],
        }

    def get(self, request, *args, **kwargs):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        generation = self._payment_payload(profile, "generate")
        return Response(
            {
                **generation,
                "generation": generation,
                "background": self._payment_payload(profile, "change_background"),
                "calendar_generation": self._payment_payload(
                    profile,
                    "generate_calendar",
                ),
                "calendar_background": self._payment_payload(
                    profile,
                    "change_calendar_background",
                ),
            }
        )

    def post(self, request, *args, **kwargs):
        action = str(request.data.get("action") or "generate").strip()
        if action not in self.actions:
            return Response(
                {"detail": "Неизвестная платная операция."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        operation_id = str(request.data.get("operation_id") or "").strip()
        if not operation_id or len(operation_id) > 64 or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for character in operation_id
        ):
            return Response(
                {"detail": "Передайте корректный идентификатор операции."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            year = int(request.data.get("year"))
            month = int(request.data.get("month"))
        except (TypeError, ValueError):
            return Response(
                {"detail": "Передайте год и месяц итогов."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if year < 2000 or year > 2100 or month < 1 or month > 12:
            return Response(
                {"detail": "Передайте корректный период итогов."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            page_index = int(request.data.get("page_index") or 0)
        except (TypeError, ValueError):
            page_index = -1
        if page_index < 0 or page_index > 99:
            return Response(
                {"detail": "Передайте корректный номер изображения."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        action_config = self.actions[action]
        marker_prefix = {
            "generate": "monthly-summary",
            "change_background": "monthly-summary-background",
            "generate_calendar": "reading-calendar",
            "change_calendar_background": "reading-calendar-background",
        }[action]
        marker = f"[op:{marker_prefix}:{operation_id}]"
        with transaction.atomic():
            profile, _ = Profile.objects.get_or_create(user=request.user)
            profile = Profile.objects.select_for_update().get(pk=profile.pk)
            balance_before = profile.coin_balance
            existing_transaction = (
                CoinTransaction.objects
                .filter(
                    profile=profile,
                    transaction_type=CoinTransaction.Type.FEATURE_PURCHASE,
                    description__contains=marker,
                )
                .order_by("-id")
                .first()
            )

            if existing_transaction is None:
                try:
                    charge_result = charge_feature_access(
                        profile,
                        cost=action_config["cost"],
                        description=(
                            f"{marker} "
                            + {
                                "generate": (
                                    f"Генерация итогов месяца {month:02d}.{year}"
                                ),
                                "change_background": (
                                    "Смена фона итогов месяца "
                                    f"{month:02d}.{year}, изображение {page_index + 1}"
                                ),
                                "generate_calendar": (
                                    f"Генерация календаря чтения {month:02d}.{year}"
                                ),
                                "change_calendar_background": (
                                    "Смена фона календаря чтения "
                                    f"{month:02d}.{year}, изображение {page_index + 1}"
                                ),
                            }[action]
                        )[:255],
                    )
                except InsufficientCoinsError as exc:
                    return Response(
                        {
                            "detail": str(exc),
                            **self._payment_payload(profile, action),
                        },
                        status=status.HTTP_402_PAYMENT_REQUIRED,
                    )
                coin_transaction = charge_result.transaction
                duplicate = False
            else:
                coin_transaction = existing_transaction
                duplicate = True

            profile.refresh_from_db(fields=("coins",))

        payment = self._payment_payload(profile, action)
        return Response(
            {
                **payment,
                "success": True,
                "duplicate": duplicate,
                "charged": not coin_transaction.unlimited,
                "balance_before": balance_before,
                "balance_after": payment["coin_balance"],
                "transaction_id": coin_transaction.pk,
            }
        )


class CurrentReadingImagePaymentView(APIView):
    """Return current-reading cards and charge image operations."""

    permission_classes = [permissions.IsAuthenticated]
    page_size = 3
    actions = {
        "generate": {
            "feature": "current_reading_image_generation",
            "cost": CURRENT_READING_IMAGE_GENERATION_COST,
            "description": "Генерация изображений «Я читаю сейчас»",
        },
        "change_background": {
            "feature": "current_reading_image_background",
            "cost": CURRENT_READING_IMAGE_BACKGROUND_COST,
            "description": "Смена фона изображения «Я читаю сейчас»",
        },
    }

    @staticmethod
    def _absolute_url(request, value):
        if not value:
            return None
        url = str(value).strip()
        if url.startswith("//"):
            return f"{request.scheme}:{url}"
        if url.startswith(("http://", "https://")):
            return url
        return request.build_absolute_uri(url if url.startswith("/") else f"/{url}")

    @staticmethod
    def _duration_payload(value):
        if not value:
            return {"display": None, "seconds": None}
        total_seconds = max(0, int(value.total_seconds()))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return {
            "display": f"{hours:02d}:{minutes:02d}:{seconds:02d}",
            "seconds": total_seconds,
        }

    def _payment_payload(self, profile, action):
        config = self.actions[action]
        payment = get_feature_payment_context(profile, cost=config["cost"])
        return {
            "action": action,
            "feature": config["feature"],
            **payment,
            "balance": payment["coin_balance"],
            "unlimited": payment["has_unlimited_coins"],
        }

    def _serialize_books(self, request):
        ensure_default_shelves(request.user)
        shelf = (
            Shelf.objects.filter(
                user=request.user,
                name__in=(DEFAULT_READING_SHELF, READING_PROGRESS_LABEL),
            )
            .order_by("-is_default", "id")
            .first()
        )
        if shelf is None:
            return []

        items = list(
            ShelfItem.objects.filter(shelf=shelf)
            .filter(book__in=Book.objects.visible_to_user(request.user))
            .select_related("book", "selected_edition")
            .prefetch_related("book__authors")
            .order_by("-added_at", "-id")
        )
        progress_by_book = {}
        progress_queryset = (
            BookProgress.objects.filter(
                user=request.user,
                event__isnull=True,
                is_active=True,
                book_id__in=[item.book_id for item in items],
            )
            .select_related("book")
            .prefetch_related("media")
            .order_by("-updated_at", "-id")
        )
        for progress in progress_queryset:
            progress_by_book.setdefault(progress.book_id, progress)

        labels = dict(BookProgress.FORMAT_CHOICES)
        result = []
        for item in items:
            progress = progress_by_book.get(item.book_id)
            if progress is None:
                continue

            total_pages = progress.get_effective_total_pages()
            combined_pages = progress.get_combined_current_pages()
            if combined_pages is None:
                combined_pages = progress.current_page

            media = list(progress.media.all())
            formats = []
            if media:
                for medium in media:
                    medium_payload = {
                        "code": medium.medium,
                        "label": labels.get(medium.medium, medium.medium),
                    }
                    if medium.medium == BookProgress.FORMAT_AUDIO:
                        position = self._duration_payload(
                            medium.audio_position or progress.audio_position
                        )
                        length = self._duration_payload(
                            medium.audio_length or progress.audio_length
                        )
                        medium_payload.update(
                            {
                                "position": position["display"],
                                "position_seconds": position["seconds"],
                                "total": length["display"],
                                "total_seconds": length["seconds"],
                            }
                        )
                    else:
                        medium_payload.update(
                            {
                                "current_page": medium.current_page,
                                "total_pages": medium.total_pages_override or total_pages,
                            }
                        )
                    formats.append(medium_payload)
            else:
                fallback = {
                    "code": progress.format,
                    "label": labels.get(progress.format, progress.format),
                }
                if progress.format == BookProgress.FORMAT_AUDIO:
                    position = self._duration_payload(progress.audio_position)
                    length = self._duration_payload(progress.audio_length)
                    fallback.update(
                        {
                            "position": position["display"],
                            "position_seconds": position["seconds"],
                            "total": length["display"],
                            "total_seconds": length["seconds"],
                        }
                    )
                else:
                    fallback.update(
                        {
                            "current_page": progress.current_page,
                            "total_pages": total_pages,
                        }
                    )
                formats.append(fallback)

            result.append(
                {
                    "book_id": item.book_id,
                    "progress_id": progress.pk,
                    "title": item.book.title,
                    "authors": [author.name for author in item.book.authors.all()],
                    "cover_url": self._absolute_url(
                        request,
                        item.get_display_cover_url(),
                    ),
                    "percent": float(progress.percent or 0),
                    "current_page": float(combined_pages) if combined_pages is not None else None,
                    "total_pages": total_pages,
                    "formats": formats,
                    "tracker_url": f"/tracker/{progress.pk}/",
                }
            )
        return result

    def get(self, request, *args, **kwargs):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        books = self._serialize_books(request)
        generation = self._payment_payload(profile, "generate")
        return Response(
            {
                "feature": "current_reading_image",
                "page_size": self.page_size,
                "page_count": (len(books) + self.page_size - 1) // self.page_size,
                "books": books,
                "generation": generation,
                "background": self._payment_payload(profile, "change_background"),
            }
        )


    def post(self, request, *args, **kwargs):
        action = str(request.data.get("action") or "generate").strip()
        if action not in self.actions:
            return Response(
                {"detail": "Неизвестная платная операция."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        operation_id = str(request.data.get("operation_id") or "").strip()
        if not operation_id or len(operation_id) > 64 or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for character in operation_id
        ):
            return Response(
                {"detail": "Передайте корректный идентификатор операции."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            page_index = int(request.data.get("page_index") or 0)
        except (TypeError, ValueError):
            page_index = -1
        if page_index < 0 or page_index > 99:
            return Response(
                {"detail": "Передайте корректный номер изображения."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        config = self.actions[action]
        marker = f"[op:current-reading-{action}:{operation_id}]"
        with transaction.atomic():
            profile, _ = Profile.objects.get_or_create(user=request.user)
            profile = Profile.objects.select_for_update().get(pk=profile.pk)
            balance_before = profile.coin_balance
            existing_transaction = (
                CoinTransaction.objects.filter(
                    profile=profile,
                    transaction_type=CoinTransaction.Type.FEATURE_PURCHASE,
                    description__contains=marker,
                )
                .order_by("-id")
                .first()
            )
            if existing_transaction is None:
                try:
                    charge_result = charge_feature_access(
                        profile,
                        cost=config["cost"],
                        description=(
                            f"{marker} {config['description']}, изображение {page_index + 1}"
                        )[:255],
                    )
                except InsufficientCoinsError as exc:
                    return Response(
                        {"detail": str(exc), **self._payment_payload(profile, action)},
                        status=status.HTTP_402_PAYMENT_REQUIRED,
                    )
                transaction_record = charge_result.transaction
                duplicate = False
            else:
                transaction_record = existing_transaction
                duplicate = True
            profile.refresh_from_db(fields=("coins",))

        payment = self._payment_payload(profile, action)
        return Response(
            {
                **payment,
                "success": True,
                "duplicate": duplicate,
                "charged": not transaction_record.unlimited,
                "balance_before": balance_before,
                "balance_after": payment["coin_balance"],
                "transaction_id": transaction_record.pk,
            }
        )


class AnnualGameReportPaymentView(APIView):
    """Charge generation of a user's read-books report for an annual game."""

    permission_classes = [permissions.IsAuthenticated]

    @staticmethod
    def _payment_payload(profile):
        payment = get_feature_payment_context(
            profile,
            cost=ANNUAL_GAME_REPORT_GENERATION_COST,
        )
        return {
            "feature": "annual_game_report_generation",
            **payment,
            "balance": payment["coin_balance"],
            "unlimited": payment["has_unlimited_coins"],
        }

    @staticmethod
    def _annual_game_exists(slug):
        from games.models import Game

        return Game.objects.filter(
            Q(slug=slug),
            Q(year__isnull=False) | Q(slug="yasnaya-polyana-foreign-2026"),
            is_active=True,
        ).exists()

    def get(self, request, slug, *args, **kwargs):
        if not self._annual_game_exists(slug):
            return Response(
                {"detail": "Сезонная игра не найдена."},
                status=status.HTTP_404_NOT_FOUND,
            )
        profile, _ = Profile.objects.get_or_create(user=request.user)
        return Response(self._payment_payload(profile))

    def post(self, request, slug, *args, **kwargs):
        if not self._annual_game_exists(slug):
            return Response(
                {"detail": "Сезонная игра не найдена."},
                status=status.HTTP_404_NOT_FOUND,
            )

        operation_id = str(request.data.get("operation_id") or "").strip()
        if not operation_id or len(operation_id) > 64 or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for character in operation_id
        ):
            return Response(
                {"detail": "Передайте корректный идентификатор операции."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        marker = f"[op:annual-game-report:{slug}:{operation_id}]"
        with transaction.atomic():
            profile, _ = Profile.objects.get_or_create(user=request.user)
            profile = Profile.objects.select_for_update().get(pk=profile.pk)
            balance_before = profile.coin_balance
            existing_transaction = (
                CoinTransaction.objects.filter(
                    profile=profile,
                    transaction_type=CoinTransaction.Type.FEATURE_PURCHASE,
                    description__contains=marker,
                )
                .order_by("-id")
                .first()
            )
            if existing_transaction is None:
                try:
                    charge_result = charge_feature_access(
                        profile,
                        cost=ANNUAL_GAME_REPORT_GENERATION_COST,
                        description=(
                            f"{marker} Генерация отчета по прочитанным книгам сезонной игры"
                        )[:255],
                    )
                except InsufficientCoinsError as exc:
                    return Response(
                        {"detail": str(exc), **self._payment_payload(profile)},
                        status=status.HTTP_402_PAYMENT_REQUIRED,
                    )
                coin_transaction = charge_result.transaction
                duplicate = False
            else:
                coin_transaction = existing_transaction
                duplicate = True
            profile.refresh_from_db(fields=("coins",))

        payment = self._payment_payload(profile)
        return Response(
            {
                **payment,
                "success": True,
                "duplicate": duplicate,
                "charged": not coin_transaction.unlimited,
                "balance_before": balance_before,
                "balance_after": payment["coin_balance"],
                "transaction_id": coin_transaction.pk,
            }
        )


class RandomShelfBookView(APIView):
    """Pick an unread shelf book and charge the shared coin balance once."""

    permission_classes = [permissions.IsAuthenticated]
    preview_limit = 12
    shelves = {
        "want_to_read": {
            "name": DEFAULT_WANT_SHELF,
            "label": "Хочу прочитать",
        },
        "library": {
            "name": DEFAULT_HOME_LIBRARY_SHELF,
            "label": "Моя домашняя библиотека",
        },
    }

    @staticmethod
    def _absolute_url(request, value):
        if not value:
            return None
        url = str(value).strip()
        if url.startswith("//"):
            return f"{request.scheme}:{url}"
        if url.startswith(("http://", "https://")):
            return url
        return request.build_absolute_uri(url if url.startswith("/") else f"/{url}")

    def _payment_payload(self, profile):
        payment = get_feature_payment_context(
            profile,
            cost=RANDOM_BOOK_SELECTION_COST,
        )
        return {
            "feature": "random_book_selection",
            **payment,
            "balance": payment["coin_balance"],
            "unlimited": payment["has_unlimited_coins"],
        }

    def _eligible_items(self, user, shelf_key):
        ensure_default_shelves(user)
        shelf_name = self.shelves[shelf_key]["name"]
        excluded_book_ids = set(
            ShelfItem.objects.filter(
                shelf__user=user,
                shelf__name__in=(
                    DEFAULT_READING_SHELF,
                    READING_PROGRESS_LABEL,
                    *ALL_DEFAULT_READ_SHELF_NAMES,
                ),
            ).values_list("book_id", flat=True)
        )
        excluded_book_ids.update(
            BookProgress.objects.filter(
                user=user,
                event__isnull=True,
                is_active=True,
            ).values_list("book_id", flat=True)
        )

        items = (
            ShelfItem.objects.filter(
                shelf__user=user,
                shelf__name=shelf_name,
                book__in=Book.objects.visible_to_user(user),
            )
            .exclude(book_id__in=excluded_book_ids)
            .select_related("book", "selected_edition")
            .prefetch_related("book__authors")
            .order_by("-added_at", "-id")
        )
        if shelf_key == "library":
            items = items.filter(
                Q(home_entry__isnull=True)
                | Q(
                    home_entry__read_at__isnull=True,
                    home_entry__is_disposed=False,
                )
            )
        return items.distinct()

    def _serialize_book(self, request, book, *, item=None):
        authors = [author.name for author in book.authors.all() if author.name]
        cover_url = item.get_display_cover_url() if item is not None else book.get_cover_url()
        return {
            "id": book.pk,
            "title": book.title,
            "authors": authors,
            "author": ", ".join(authors) or "Автор не указан",
            "cover_url": self._absolute_url(request, cover_url),
            "detail_url": reverse("book_detail", args=[book.pk]),
            "app_detail_url": f"/books/{book.pk}",
        }

    @staticmethod
    def _valid_operation_id(value):
        return bool(
            value
            and len(value) <= 64
            and all(
                character
                in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
                for character in value
            )
        )

    def _selection_marker(self, shelf_key, operation_id):
        return f"[op:random-book:{shelf_key}:{operation_id}]"

    def get(self, request, *args, **kwargs):
        shelf_key = str(request.query_params.get("shelf") or "").strip()
        if shelf_key not in self.shelves:
            return Response(
                {"detail": "Выберите полку для случайного выбора книги."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile, _ = Profile.objects.get_or_create(user=request.user)
        items = self._eligible_items(request.user, shelf_key)
        preview_items = list(items[: self.preview_limit])
        return Response(
            {
                **self._payment_payload(profile),
                "shelf": shelf_key,
                "shelf_label": self.shelves[shelf_key]["label"],
                "candidate_count": items.count(),
                "preview_books": [
                    self._serialize_book(request, item.book, item=item)
                    for item in preview_items
                ],
            }
        )

    def post(self, request, *args, **kwargs):
        shelf_key = str(request.data.get("shelf") or "").strip()
        if shelf_key not in self.shelves:
            return Response(
                {"detail": "Выберите полку для случайного выбора книги."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        operation_id = str(request.data.get("operation_id") or "").strip()
        if not self._valid_operation_id(operation_id):
            return Response(
                {"detail": "Передайте корректный идентификатор операции."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        action = str(request.data.get("action") or "select").strip()
        marker = self._selection_marker(shelf_key, operation_id)
        if action == "start_reading":
            try:
                book_id = int(request.data.get("book_id"))
            except (TypeError, ValueError):
                book_id = 0
            selection = (
                CoinTransaction.objects.filter(
                    Q(description__contains=marker)
                    & Q(description__contains=f"[book:{book_id}]"),
                    profile__user=request.user,
                    transaction_type=CoinTransaction.Type.FEATURE_PURCHASE,
                )
                .order_by("-id")
                .first()
            )
            if not selection:
                return Response(
                    {"detail": "Сначала выполните случайный выбор книги."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            book = Book.objects.visible_to_user(request.user).filter(pk=book_id).first()
            if not book:
                return Response(
                    {"detail": "Выбранная книга больше недоступна."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            move_book_to_reading_shelf(request.user, book)
            progress = (
                BookProgress.objects.filter(
                    user=request.user,
                    book=book,
                    event__isnull=True,
                    is_active=True,
                )
                .order_by("-updated_at", "-id")
                .first()
            )
            if progress is None:
                progress = BookProgress.objects.create(
                    event=None,
                    user=request.user,
                    book=book,
                    is_active=True,
                    started_at=timezone.localdate(),
                    finished_at=None,
                    percent=0,
                    current_page=0,
                    reading_notes="",
                )
            return Response(
                {
                    "success": True,
                    "book": self._serialize_book(request, book),
                    "progress_id": progress.pk,
                    "tracker_url": f"/tracker/{progress.pk}/",
                    "app_tracker_url": f"/books/{book.pk}/tracker",
                }
            )

        if action != "select":
            return Response(
                {"detail": "Неизвестное действие."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            profile, _ = Profile.objects.get_or_create(user=request.user)
            profile = Profile.objects.select_for_update().get(pk=profile.pk)
            balance_before = profile.coin_balance
            existing_transaction = (
                CoinTransaction.objects.filter(
                    profile=profile,
                    transaction_type=CoinTransaction.Type.FEATURE_PURCHASE,
                    description__contains=marker,
                )
                .order_by("-id")
                .first()
            )
            selected_item = None
            if existing_transaction is not None:
                match = re.search(r"\[book:(\d+)\]", existing_transaction.description or "")
                selected_book_id = int(match.group(1)) if match else 0
                selected_book = (
                    Book.objects.visible_to_user(request.user)
                    .prefetch_related("authors")
                    .filter(pk=selected_book_id)
                    .first()
                )
                if selected_book is None:
                    return Response(
                        {"detail": "Выбранная книга больше недоступна."},
                        status=status.HTTP_410_GONE,
                    )
                transaction_record = existing_transaction
                duplicate = True
            else:
                eligible_items = list(self._eligible_items(request.user, shelf_key))
                if not eligible_items:
                    return Response(
                        {"detail": "На этой полке нет непрочитанных книг для выбора."},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                selected_item = secrets.choice(eligible_items)
                selected_book = selected_item.book
                try:
                    charge_result = charge_feature_access(
                        profile,
                        cost=RANDOM_BOOK_SELECTION_COST,
                        description=(
                            f"{marker} [book:{selected_book.pk}] "
                            f"Случайный выбор книги с полки {self.shelves[shelf_key]['label']}"
                        )[:255],
                    )
                except InsufficientCoinsError as exc:
                    return Response(
                        {"detail": str(exc), **self._payment_payload(profile)},
                        status=status.HTTP_402_PAYMENT_REQUIRED,
                    )
                transaction_record = charge_result.transaction
                duplicate = False
            profile.refresh_from_db(fields=("coins",))

        payment = self._payment_payload(profile)
        return Response(
            {
                **payment,
                "success": True,
                "shelf": shelf_key,
                "book": self._serialize_book(
                    request,
                    selected_book,
                    item=selected_item,
                ),
                "duplicate": duplicate,
                "charged": not transaction_record.unlimited,
                "balance_before": balance_before,
                "balance_after": payment["coin_balance"],
                "transaction_id": transaction_record.pk,
            }
        )


class ReviewImagePaymentView(APIView):
    """Return review-image data and charge generation/background actions."""

    permission_classes = [permissions.IsAuthenticated]

    actions = {
        "generate": {
            "feature": "review_image_generation",
            "cost": REVIEW_IMAGE_GENERATION_COST,
            "description": "Генерация изображений с отзывом",
        },
        "change_background": {
            "feature": "review_image_background",
            "cost": REVIEW_IMAGE_BACKGROUND_COST,
            "description": "Смена фона изображения с отзывом",
        },
    }

    def _get_rating(self, request, rating_id):
        return get_object_or_404(
            Rating.objects.select_related("book", "user", "book__primary_isbn")
            .prefetch_related("book__authors", "book__isbn"),
            pk=rating_id,
            user=request.user,
        )

    @staticmethod
    def _absolute_url(request, value):
        if not value:
            return None
        url = str(value).strip()
        if url.startswith("//"):
            return f"{request.scheme}:{url}"
        if url.startswith(("http://", "https://")):
            return url
        return request.build_absolute_uri(url if url.startswith("/") else f"/{url}")

    def _reading_payload(self, rating):
        progress = (
            BookProgress.objects.filter(
                user=rating.user,
                book=rating.book,
                event__isnull=True,
            )
            .prefetch_related("media")
            .order_by("-finished_at", "-updated_at", "-id")
            .first()
        )
        if progress is None:
            progress = (
                BookProgress.objects.filter(user=rating.user, book=rating.book)
                .prefetch_related("media")
                .order_by("-finished_at", "-updated_at", "-id")
                .first()
            )

        reading_start = None
        reading_end = None
        format_labels = []
        total_pages = rating.book.get_total_pages()

        if progress is not None:
            period = progress.logs.aggregate(start=Min("log_date"), end=Max("log_date"))
            reading_start = progress.started_at or period.get("start")
            reading_end = progress.finished_at or period.get("end")
            if reading_start is None and progress.updated_at:
                reading_start = progress.updated_at.date()
            total_pages = total_pages or progress.get_effective_total_pages()

            media = list(progress.media.all())
            if media:
                labels = dict(BookProgress.FORMAT_CHOICES)
                format_labels = list(
                    dict.fromkeys(labels.get(item.medium, item.medium) for item in media)
                )
            else:
                format_labels = [progress.get_format_display()]

        if reading_end is None:
            read_item = (
                ShelfItem.objects.filter(
                    shelf__user=rating.user,
                    shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
                    book=rating.book,
                )
                .order_by("-added_at")
                .first()
            )
            if read_item and read_item.added_at:
                reading_end = timezone.localtime(read_item.added_at).date()

        reading_days = None
        if reading_start and reading_end:
            reading_days = max(1, (reading_end - reading_start).days + 1)

        return {
            "reading_start": reading_start.isoformat() if reading_start else None,
            "reading_start_label": reading_start.strftime("%d.%m.%Y") if reading_start else None,
            "reading_end": reading_end.isoformat() if reading_end else None,
            "reading_end_label": reading_end.strftime("%d.%m.%Y") if reading_end else None,
            "reading_days": reading_days,
            "format_labels": format_labels,
            "total_pages": total_pages,
        }

    def _review_payload(self, request, rating):
        book = rating.book
        return {
            "id": rating.pk,
            "review": rating.review or "",
            "score": rating.score,
            "category_scores": [
                {"label": label, "value": value}
                for label, value in rating.get_category_scores()
            ],
            "created_at": rating.created_at.isoformat() if rating.created_at else None,
            "created_label": rating.created_at.strftime("%d.%m.%Y") if rating.created_at else None,
            "username": rating.user.get_username(),
            "book_id": book.pk,
            "book_title": book.title,
            "book_author": ", ".join(str(author) for author in book.authors.all()),
            "book_cover_url": self._absolute_url(request, book.get_original_cover_url()),
            "logo_url": self._absolute_url(request, "/static/img/logo_1.png"),
            "site_label": "kalejdoskopknig.ru",
            **self._reading_payload(rating),
        }

    def _payment_payload(self, profile, action):
        config = self.actions[action]
        payment = get_feature_payment_context(profile, cost=config["cost"])
        return {
            "action": action,
            "feature": config["feature"],
            **payment,
            "balance": payment["coin_balance"],
            "unlimited": payment["has_unlimited_coins"],
        }

    @staticmethod
    def _operation_id(value):
        operation_id = str(value or "").strip()
        if not operation_id or len(operation_id) > 64 or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for character in operation_id
        ):
            return None
        return operation_id

    @staticmethod
    def _background_index(operation_id, rating_id):
        if not REVIEW_IMAGE_BACKGROUNDS:
            return 0
        digest = hashlib.sha256(f"{operation_id}:{rating_id}".encode("utf-8")).digest()
        return int.from_bytes(digest[:4], "big") % len(REVIEW_IMAGE_BACKGROUNDS)

    def _response_payload(self, request, profile, rating, action="generate", **extra):
        return {
            "feature": "review_image",
            "review": self._review_payload(request, rating),
            "backgrounds": list(REVIEW_IMAGE_BACKGROUNDS),
            "generation": self._payment_payload(profile, "generate"),
            "background": self._payment_payload(profile, "change_background"),
            "payment": self._payment_payload(profile, action),
            **extra,
        }

    def get(self, request, rating_id, *args, **kwargs):
        rating = self._get_rating(request, rating_id)
        if not str(rating.review or "").strip():
            return Response(
                {"detail": "Сначала добавьте текст отзыва."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        profile, _ = Profile.objects.get_or_create(user=request.user)
        return Response(self._response_payload(request, profile, rating))

    def post(self, request, rating_id, *args, **kwargs):
        rating = self._get_rating(request, rating_id)
        if not str(rating.review or "").strip():
            return Response(
                {"detail": "Сначала добавьте текст отзыва."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        action = str(request.data.get("action") or "generate").strip()
        if action not in self.actions:
            return Response(
                {"detail": "Неизвестная платная операция."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        operation_id = self._operation_id(request.data.get("operation_id"))
        if operation_id is None:
            return Response(
                {"detail": "Передайте корректный идентификатор операции."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            page_index = max(0, min(99, int(request.data.get("page_index") or 0)))
        except (TypeError, ValueError):
            page_index = 0
        try:
            current_background_index = int(request.data.get("current_background_index") or 0)
        except (TypeError, ValueError):
            current_background_index = 0

        config = self.actions[action]
        marker = f"[op:review-image:{action}:{operation_id}]"
        with transaction.atomic():
            profile, _ = Profile.objects.get_or_create(user=request.user)
            profile = Profile.objects.select_for_update().get(pk=profile.pk)
            balance_before = profile.coin_balance
            existing_transaction = (
                CoinTransaction.objects.filter(
                    profile=profile,
                    transaction_type=CoinTransaction.Type.FEATURE_PURCHASE,
                    description__contains=marker,
                )
                .order_by("-id")
                .first()
            )

            if existing_transaction is None:
                try:
                    charge_result = charge_feature_access(
                        profile,
                        cost=config["cost"],
                        description=(
                            f"{marker} {config['description']}: «{rating.book.title}»"
                        )[:255],
                    )
                except InsufficientCoinsError as exc:
                    return Response(
                        {
                            "detail": str(exc),
                            **self._response_payload(request, profile, rating, action),
                        },
                        status=status.HTTP_402_PAYMENT_REQUIRED,
                    )
                coin_transaction = charge_result.transaction
                duplicate = False
            else:
                coin_transaction = existing_transaction
                duplicate = True

            profile.refresh_from_db(fields=("coins",))

        if action == "generate":
            background_index = self._background_index(operation_id, rating.pk)
        elif REVIEW_IMAGE_BACKGROUNDS:
            background_index = (current_background_index + 1) % len(REVIEW_IMAGE_BACKGROUNDS)
        else:
            background_index = 0

        return Response(
            self._response_payload(
                request,
                profile,
                rating,
                action,
                success=True,
                duplicate=duplicate,
                charged=not coin_transaction.unlimited,
                balance_before=balance_before,
                balance_after=profile.coin_balance,
                transaction_id=coin_transaction.pk,
                page_index=page_index,
                background_index=background_index,
            )
        )


class BookDetailView(generics.RetrieveAPIView):
    """Detailed book card with authors and edition data."""

    serializer_class = BookDetailSerializer

    def get_queryset(self):
        return (
            Book.objects.visible_to_user(self.request.user)
            .select_related("primary_isbn")
            .prefetch_related("authors", "genres", "isbn")
            .order_by("-created_at", "-id")
        )


class ReadingClubListView(generics.ListCreateAPIView):
    """Active and upcoming reading clubs for communities tab."""

    serializer_class = ReadingClubSerializer
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ReadingClubCreateSerializer
        return ReadingClubSerializer

    def get_queryset(self):
        return (
            ReadingClub.objects.with_message_count()
            .filter(book__visibility=Book.Visibility.PUBLIC, book__is_hidden_by_admin=False)
            .select_related("book", "book__primary_isbn")
            .prefetch_related("book__authors", "book__genres")
            .order_by("-start_date", "-created_at")
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        profile, _ = Profile.objects.get_or_create(user=request.user)
        try:
            with transaction.atomic():
                charge_feature_access(
                    profile,
                    description="Создание совместного чтения",
                )
                reading = serializer.save()
        except InsufficientCoinsError:
            profile.refresh_from_db(fields=["coins"])
            payment = get_feature_payment_context(profile)
            return Response(
                {
                    "detail": f"Недостаточно монет. Для создания совместного чтения нужно {FEATURE_ACCESS_COST} монет.",
                    "payment": payment,
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        detail = ReadingClubDetailSerializer(reading, context={"request": request})
        profile.refresh_from_db(fields=["coins"])
        payload = dict(detail.data)
        payload["payment"] = get_feature_payment_context(profile)
        return Response(payload, status=status.HTTP_201_CREATED)


class ReadingClubDetailView(generics.RetrieveAPIView):
    """Detailed reading club card with topics, participants and progress."""

    serializer_class = ReadingClubDetailSerializer
    lookup_field = "slug"
    lookup_url_kwarg = "slug"

    def get_queryset(self):
        post_count_subquery = Subquery(
            DiscussionPost.objects.filter(topic=OuterRef("pk"))
            .order_by()
            .values("topic")
            .annotate(total=Count("pk"))
            .values("total")[:1],
            output_field=IntegerField(),
        )
        topics_queryset = (
            ReadingNorm.objects.order_by("order", "discussion_opens_at", "id")
            .annotate(post_count=Coalesce(post_count_subquery, Value(0)))
        )
        participants_queryset = (
            ReadingParticipant.objects.select_related("user", "user__profile")
            .order_by("-joined_at", "id")
        )

        return (
            ReadingClub.objects.with_message_count()
            .filter(book__visibility=Book.Visibility.PUBLIC, book__is_hidden_by_admin=False)
            .select_related("book", "book__primary_isbn", "creator", "creator__profile")
            .prefetch_related(
                "book__authors",
                "book__genres",
                Prefetch("topics", queryset=topics_queryset),
                Prefetch(
                    "participants",
                    queryset=participants_queryset,
                    to_attr="prefetched_participants",
                ),
            )
        )

    def get_object(self):
        reading = super().get_object()
        participants = list(getattr(reading, "prefetched_participants", []))
        self._attach_participant_progress(reading, participants)
        self._attach_topic_unread_counts(self.request, reading)
        return reading

    def _attach_topic_unread_counts(self, request, reading: ReadingClub) -> None:
        topics = list(reading.topics.all())

        for topic in topics:
            topic.unread_count = 0
            topic.first_unread_post_id = None

        user = getattr(request, "user", None)
        if not topics or not getattr(user, "is_authenticated", False):
            return

        topic_ids = [topic.id for topic in topics]
        read_map = {
            topic_id: last_read_at
            for topic_id, last_read_at in DiscussionRead.objects.filter(
                user=user,
                topic_id__in=topic_ids,
            ).values_list("topic_id", "last_read_at")
        }
        unread_counts: dict[int, int] = {}
        first_unread_post_ids: dict[int, int] = {}

        unread_posts = (
            DiscussionPost.objects.filter(topic_id__in=topic_ids)
            .exclude(author_id=user.id)
            .only("id", "topic_id", "created_at")
            .order_by("created_at", "id")
        )

        for post in unread_posts:
            last_read_at = read_map.get(post.topic_id)
            if last_read_at is not None and post.created_at <= last_read_at:
                continue

            unread_counts[post.topic_id] = unread_counts.get(post.topic_id, 0) + 1
            first_unread_post_ids.setdefault(post.topic_id, post.id)

        for topic in topics:
            topic.unread_count = unread_counts.get(topic.id, 0)
            topic.first_unread_post_id = first_unread_post_ids.get(topic.id)

    def _attach_participant_progress(self, reading: ReadingClub, participants: list[ReadingParticipant]) -> None:
        if not participants:
            return

        user_ids = [participant.user_id for participant in participants]
        progress_map = {
            progress.user_id: progress
            for progress in BookProgress.objects.filter(
                user_id__in=user_ids,
                book=reading.book,
                event__isnull=True,
                is_active=True,
            )
        }
        read_users = set(
            ShelfItem.objects.filter(
                shelf__user_id__in=user_ids,
                shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
                book=reading.book,
            ).values_list("shelf__user_id", flat=True)
        )

        for participant in participants:
            participant.reading_progress = progress_map.get(participant.user_id)
            participant.reading_progress_percent = None

            percent = None
            if participant.reading_progress and participant.reading_progress.percent is not None:
                try:
                    percent = float(participant.reading_progress.percent)
                except (TypeError, ValueError):
                    percent = None

            if participant.user_id in read_users and (percent is None or percent < 100.0):
                percent = 100.0

            if percent is not None:
                participant.reading_progress_percent = round(max(0.0, min(percent, 100.0)))


class ReadingClubJoinView(APIView):
    """Join a reading club or send a participation request."""

    permission_classes = [permissions.IsAuthenticated]

    def get_reading(self, slug: str) -> ReadingClub:
        detail_view = ReadingClubDetailView()
        detail_view.request = self.request
        return get_object_or_404(detail_view.get_queryset(), slug=slug)

    def serialize_reading(self, request, slug: str):
        detail_view = ReadingClubDetailView()
        detail_view.request = request
        reading = get_object_or_404(detail_view.get_queryset(), slug=slug)
        participants = list(getattr(reading, "prefetched_participants", []))
        detail_view._attach_participant_progress(reading, participants)
        detail_view._attach_topic_unread_counts(request, reading)
        return ReadingClubDetailSerializer(reading, context={"request": request})

    def post(self, request, slug: str, *args, **kwargs):
        reading = self.get_reading(slug)
        participant, created = ReadingParticipant.objects.get_or_create(
            reading=reading,
            user=request.user,
            defaults={
                "status": ReadingParticipant.Status.APPROVED
                if reading.join_policy == ReadingClub.JoinPolicy.OPEN
                else ReadingParticipant.Status.PENDING
            },
        )

        detail = self.serialize_reading(request, slug)
        return Response(detail.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ReadingClubTopicDetailView(APIView):
    """Reading club norm detail with discussion posts."""

    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_topic(self, slug: str, pk: int) -> ReadingNorm:
        return get_object_or_404(
            ReadingNorm.objects.select_related(
                "reading",
                "reading__book",
                "reading__book__primary_isbn",
                "reading__creator",
                "reading__creator__profile",
            ).prefetch_related(
                "reading__book__authors",
                "reading__book__genres",
                Prefetch(
                    "posts",
                    queryset=DiscussionPost.objects.select_related(
                        "author",
                        "author__profile",
                        "parent",
                        "parent__author",
                    ).order_by("created_at", "id"),
                ),
            ),
            pk=pk,
            reading__slug=slug,
            reading__book__visibility=Book.Visibility.PUBLIC,
            reading__book__is_hidden_by_admin=False,
        )

    def attach_unread_state(self, request, topic: ReadingNorm) -> None:
        posts = list(topic.posts.all())
        topic.unread_count = 0
        topic.first_unread_post_id = None

        for post in posts:
            post.is_unread = False

        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            return

        reported_post_ids = set(
            DiscussionPostReport.objects.filter(
                reporter=user,
                post_id__in=[post.id for post in posts],
            ).values_list("post_id", flat=True)
        )
        for post in posts:
            post.is_reported_by_me = post.id in reported_post_ids

        last_read_at = (
            DiscussionRead.objects.filter(user=user, topic=topic)
            .values_list("last_read_at", flat=True)
            .first()
        )
        unread_posts = [
            post
            for post in posts
            if post.author_id != user.id and (last_read_at is None or post.created_at > last_read_at)
        ]

        for post in unread_posts:
            post.is_unread = True

        topic.unread_count = len(unread_posts)
        topic.first_unread_post_id = unread_posts[0].id if unread_posts else None

    def can_manage_topic(self, request, topic: ReadingNorm) -> bool:
        user = getattr(request, "user", None)
        return bool(getattr(user, "is_authenticated", False) and topic.reading.creator_id == user.id)

    def reject_topic_management(self):
        return Response(
            {"detail": "Редактировать нормы может только создатель совместного чтения."},
            status=status.HTTP_403_FORBIDDEN,
        )

    def serialize_topic(self, request, slug: str, pk: int):
        refreshed_topic = self.get_topic(slug, pk)
        self.attach_unread_state(request, refreshed_topic)
        return ReadingClubTopicDetailSerializer(refreshed_topic, context={"request": request})

    def get(self, request, slug: str, pk: int, *args, **kwargs):
        topic = self.get_topic(slug, pk)
        if getattr(request.user, "is_authenticated", False):
            is_participant = topic.reading.participants.filter(
                user=request.user,
                status=ReadingParticipant.Status.APPROVED,
            ).exists()
            self.attach_unread_state(request, topic)
            if is_participant:
                mark_topic_read(request.user, topic)
        else:
            self.attach_unread_state(request, topic)

        serializer = ReadingClubTopicDetailSerializer(topic, context={"request": request})
        return Response(serializer.data)

    def put(self, request, slug: str, pk: int, *args, **kwargs):
        return self.update(request, slug, pk, partial=False)

    def patch(self, request, slug: str, pk: int, *args, **kwargs):
        return self.update(request, slug, pk, partial=True)

    def update(self, request, slug: str, pk: int, partial: bool):
        topic = self.get_topic(slug, pk)

        if not self.can_manage_topic(request, topic):
            return self.reject_topic_management()

        serializer = ReadingClubTopicCreateSerializer(topic, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        detail = self.serialize_topic(request, slug, pk)
        return Response(detail.data)

    def delete(self, request, slug: str, pk: int, *args, **kwargs):
        topic = self.get_topic(slug, pk)

        if not self.can_manage_topic(request, topic):
            return self.reject_topic_management()

        topic.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def post(self, request, slug: str, pk: int, *args, **kwargs):
        topic = self.get_topic(slug, pk)

        if not topic.is_open():
            return Response(
                {"detail": "Обсуждение этой нормы еще не открыто."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not topic.reading.participants.filter(
            user=request.user,
            status=ReadingParticipant.Status.APPROVED,
        ).exists():
            return Response(
                {"detail": "Только участники могут оставлять сообщения."},
                status=status.HTTP_403_FORBIDDEN,
            )

        content = str(request.data.get("content") or "").strip()
        if not content:
            return Response(
                {"content": ["Введите сообщение."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        parent = None
        parent_id = request.data.get("parent")
        if parent_id:
            try:
                parent = topic.posts.get(pk=int(parent_id))
            except (TypeError, ValueError, DiscussionPost.DoesNotExist):
                parent = None

        post = DiscussionPost.objects.create(
            topic=topic,
            author=request.user,
            parent=parent,
            content=content,
        )
        award_for_discussion_post(post)
        mark_topic_read(request.user, topic)

        refreshed_topic = self.get_topic(slug, pk)
        self.attach_unread_state(request, refreshed_topic)
        serializer = ReadingClubTopicDetailSerializer(refreshed_topic, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class DiscussionPostReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, slug: str, pk: int, post_pk: int, *args, **kwargs):
        post = get_object_or_404(
            DiscussionPost.objects.select_related("author", "topic", "topic__reading"),
            pk=post_pk,
            topic_id=pk,
            topic__reading__slug=slug,
            topic__reading__book__visibility=Book.Visibility.PUBLIC,
            topic__reading__book__is_hidden_by_admin=False,
        )
        if post.author_id == request.user.id:
            return Response(
                {"detail": "Нельзя пожаловаться на собственное сообщение."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = DiscussionPostReportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report, created = DiscussionPostReport.objects.get_or_create(
            post=post,
            reporter=request.user,
            defaults={
                "reason": serializer.validated_data["reason"],
                "details": serializer.validated_data.get("details", ""),
                "reported_user": post.author,
                "content_snapshot": post.content,
                "topic_snapshot": post.topic.title,
            },
        )
        return Response(
            {
                "detail": (
                    "Жалоба отправлена. Спасибо, мы проверим сообщение."
                    if created
                    else "Вы уже пожаловались на это сообщение."
                ),
                "reported": True,
                "report_id": report.pk,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ReadingClubTopicCreateView(APIView):
    """Create a reading club norm from the mobile client."""

    permission_classes = [permissions.IsAuthenticated]

    def get_reading(self, slug: str) -> ReadingClub:
        return get_object_or_404(
            ReadingClub.objects.select_related(
                "book",
                "book__primary_isbn",
                "creator",
                "creator__profile",
            ).prefetch_related(
                "book__authors",
                "book__genres",
            ),
            book__visibility=Book.Visibility.PUBLIC,
            book__is_hidden_by_admin=False,
            slug=slug,
        )

    def post(self, request, slug: str, *args, **kwargs):
        reading = self.get_reading(slug)

        if reading.creator_id != request.user.id:
            return Response(
                {"detail": "Добавлять нормы может только создатель совместного чтения."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ReadingClubTopicCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        topic = serializer.save(reading=reading)
        topic.unread_count = 0
        topic.first_unread_post_id = None

        detail = ReadingClubTopicDetailSerializer(topic, context={"request": request})
        return Response(detail.data, status=status.HTTP_201_CREATED)


class ReadingMarathonListView(generics.ListCreateAPIView):
    """Reading marathons for the community feed."""

    serializer_class = ReadingMarathonSerializer
    pagination_class = StandardResultsSetPagination
    queryset = ReadingMarathon.objects.select_related(None).order_by(
        "-start_date", "-created_at"
    )

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ReadingMarathonCreateSerializer
        return ReadingMarathonSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        profile, _ = Profile.objects.get_or_create(user=request.user)
        try:
            with transaction.atomic():
                charge_feature_access(
                    profile,
                    description="Создание марафона",
                )
                marathon = serializer.save()
        except InsufficientCoinsError:
            profile.refresh_from_db(fields=["coins"])
            payment = get_feature_payment_context(profile)
            return Response(
                {
                    "detail": f"Недостаточно монет. Для создания марафона нужно {FEATURE_ACCESS_COST} монет.",
                    "payment": payment,
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        detail_view = ReadingMarathonDetailView()
        detail_view.request = request
        refreshed = get_object_or_404(detail_view.get_queryset(), pk=marathon.pk)
        detail = ReadingMarathonDetailSerializer(refreshed, context={"request": request})
        profile.refresh_from_db(fields=["coins"])
        payload = dict(detail.data)
        payload["payment"] = get_feature_payment_context(profile)
        return Response(payload, status=status.HTTP_201_CREATED)


class ReadingMarathonDetailView(generics.RetrieveAPIView):
    """Detailed marathon card with themes, participants and books."""

    serializer_class = ReadingMarathonDetailSerializer
    lookup_field = "slug"
    lookup_url_kwarg = "slug"

    def get_queryset(self):
        participants_queryset = (
            MarathonParticipant.objects.select_related("user", "user__profile")
            .order_by("joined_at", "id")
        )

        return (
            ReadingMarathon.objects.select_related("creator", "creator__profile")
            .prefetch_related(
                Prefetch("themes", queryset=MarathonTheme.objects.order_by("order", "id")),
                Prefetch(
                    "participants",
                    queryset=participants_queryset,
                    to_attr="prefetched_participants",
                ),
            )
        )

    def get_object(self):
        marathon = super().get_object()
        marathon.prefetched_entries = list(
            MarathonEntry.objects.filter(participant__marathon=marathon)
            .filter(book__visibility=Book.Visibility.PUBLIC, book__is_hidden_by_admin=False)
            .select_related(
                "participant",
                "participant__user",
                "participant__user__profile",
                "theme",
                "book",
                "book__primary_isbn",
            )
            .prefetch_related("book__authors", "book__genres", "book__isbn")
            .order_by("participant__user__username", "theme__order", "created_at")
        )
        return marathon


class ReadingMarathonJoinView(APIView):
    """Join a marathon or send a participation request."""

    permission_classes = [permissions.IsAuthenticated]

    def get_marathon(self, slug: str) -> ReadingMarathon:
        detail_view = ReadingMarathonDetailView()
        detail_view.request = self.request
        return get_object_or_404(detail_view.get_queryset(), slug=slug)

    def serialize_marathon(self, request, slug: str):
        detail_view = ReadingMarathonDetailView()
        detail_view.request = request
        marathon = get_object_or_404(detail_view.get_queryset(), slug=slug)
        marathon.prefetched_entries = list(
            MarathonEntry.objects.filter(participant__marathon=marathon)
            .filter(book__visibility=Book.Visibility.PUBLIC, book__is_hidden_by_admin=False)
            .select_related(
                "participant",
                "participant__user",
                "participant__user__profile",
                "theme",
                "book",
                "book__primary_isbn",
            )
            .prefetch_related("book__authors", "book__genres", "book__isbn")
            .order_by("participant__user__username", "theme__order", "created_at")
        )
        return ReadingMarathonDetailSerializer(marathon, context={"request": request})

    def post(self, request, slug: str, *args, **kwargs):
        marathon = self.get_marathon(slug)
        participant, created = MarathonParticipant.objects.get_or_create(
            marathon=marathon,
            user=request.user,
            defaults={
                "status": MarathonParticipant.Status.APPROVED
                if marathon.join_policy == ReadingMarathon.JoinPolicy.OPEN
                else MarathonParticipant.Status.PENDING
            },
        )

        detail = self.serialize_marathon(request, slug)
        return Response(detail.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ReadingMarathonParticipantApproveView(ReadingMarathonJoinView):
    """Approve a pending marathon participation request."""

    def post(self, request, slug: str, pk: int, *args, **kwargs):
        marathon = self.get_marathon(slug)

        if marathon.creator_id != request.user.id:
            return Response(
                {"detail": "Одобрять заявки может только создатель марафона."},
                status=status.HTTP_403_FORBIDDEN,
            )

        participant = get_object_or_404(MarathonParticipant, pk=pk, marathon=marathon)

        if participant.status != MarathonParticipant.Status.APPROVED:
            participant.status = MarathonParticipant.Status.APPROVED
            participant.save(update_fields=["status"])

        detail = self.serialize_marathon(request, slug)
        return Response(detail.data, status=status.HTTP_200_OK)


class ReadingMarathonEntryCreateView(APIView):
    """Add a book to a marathon theme from the mobile client."""

    permission_classes = [permissions.IsAuthenticated]

    def get_marathon(self, slug: str) -> ReadingMarathon:
        participants_queryset = (
            MarathonParticipant.objects.select_related("user", "user__profile")
            .order_by("joined_at", "id")
        )

        return get_object_or_404(
            ReadingMarathon.objects.select_related("creator", "creator__profile")
            .prefetch_related(
                Prefetch("themes", queryset=MarathonTheme.objects.order_by("order", "id")),
                Prefetch(
                    "participants",
                    queryset=participants_queryset,
                    to_attr="prefetched_participants",
                ),
            ),
            slug=slug,
        )

    def attach_entries(self, marathon: ReadingMarathon) -> None:
        marathon.prefetched_entries = list(
            MarathonEntry.objects.filter(participant__marathon=marathon)
            .filter(book__visibility=Book.Visibility.PUBLIC, book__is_hidden_by_admin=False)
            .select_related(
                "participant",
                "participant__user",
                "participant__user__profile",
                "theme",
                "book",
                "book__primary_isbn",
            )
            .prefetch_related("book__authors", "book__genres", "book__isbn")
            .order_by("participant__user__username", "theme__order", "created_at")
        )

    def post(self, request, slug: str, *args, **kwargs):
        marathon = self.get_marathon(slug)
        participants = list(getattr(marathon, "prefetched_participants", []))
        participant = next(
            (item for item in participants if item.user_id == request.user.id),
            None,
        )

        if participant is None:
            return Response(
                {"detail": "Чтобы добавить книгу, нужно участвовать в марафоне."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not participant.is_approved:
            return Response(
                {"detail": "Дождитесь подтверждения участия в марафоне."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = MarathonEntryCreateSerializer(
            data=request.data,
            context={
                "request": request,
                "marathon": marathon,
                "participant": participant,
            },
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        refreshed_marathon = self.get_marathon(slug)
        self.attach_entries(refreshed_marathon)
        detail = ReadingMarathonDetailSerializer(refreshed_marathon, context={"request": request})
        return Response(detail.data, status=status.HTTP_201_CREATED)


class ReadingMarathonEntryUpdateView(ReadingMarathonJoinView):
    """Update the current user's marathon entry status and progress."""

    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, slug: str, pk: int, *args, **kwargs):
        entry = get_object_or_404(
            MarathonEntry.objects.filter(
                book__visibility=Book.Visibility.PUBLIC,
                book__is_hidden_by_admin=False,
            ).select_related(
                "participant",
                "participant__marathon",
                "participant__user",
            ),
            pk=pk,
            participant__marathon__slug=slug,
        )

        if entry.participant.user_id != request.user.id:
            return Response(
                {"detail": "Менять статус этой книги может только участник, который ее добавил."},
                status=status.HTTP_403_FORBIDDEN,
            )

        marathon = entry.participant.marathon
        previous_completion = entry.completion_status
        completion_became_confirmed = False

        serializer = MarathonEntryUpdateSerializer(entry, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        entry = serializer.save()

        if (
            entry.status == MarathonEntry.Status.COMPLETED
            and marathon.completion_policy == ReadingMarathon.CompletionPolicy.AUTO
            and entry.has_review()
        ):
            if entry.completion_status != MarathonEntry.CompletionStatus.CONFIRMED:
                entry.completion_status = MarathonEntry.CompletionStatus.CONFIRMED
                entry.save(update_fields=["completion_status", "updated_at"])
                completion_became_confirmed = True
        elif entry.status == MarathonEntry.Status.COMPLETED:
            if entry.completion_status != MarathonEntry.CompletionStatus.AWAITING_REVIEW:
                entry.completion_status = MarathonEntry.CompletionStatus.AWAITING_REVIEW
                entry.save(update_fields=["completion_status", "updated_at"])
        elif entry.status != MarathonEntry.Status.COMPLETED:
            if entry.completion_status != MarathonEntry.CompletionStatus.IN_PROGRESS:
                entry.completion_status = MarathonEntry.CompletionStatus.IN_PROGRESS
                entry.save(update_fields=["completion_status", "updated_at"])

        if (
            entry.completion_status == MarathonEntry.CompletionStatus.CONFIRMED
            and (completion_became_confirmed or previous_completion != MarathonEntry.CompletionStatus.CONFIRMED)
        ):
            award_for_marathon_confirmation(entry)

        detail = self.serialize_marathon(request, slug)
        return Response(detail.data, status=status.HTTP_200_OK)

    def post(self, request, slug: str, pk: int, *args, **kwargs):
        return self.patch(request, slug, pk, *args, **kwargs)


class HomeFeedView(APIView):
    """Aggregate data for the mobile home screen."""

    def get(self, request, *args, **kwargs):
        today = timezone.localdate()
        weekly_start = today - timedelta(days=6)

        clubs_qs = (
            ReadingClub.objects.select_related("book", "book__primary_isbn", "creator")
            .with_message_count()
            .prefetch_related("participants", "book__authors", "book__genres", "book__isbn")
            .filter(book__visibility=Book.Visibility.PUBLIC, book__is_hidden_by_admin=False)
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

        if not active_clubs:
            upcoming_clubs_qs = (
                ReadingClub.objects.select_related("book", "book__primary_isbn", "creator")
                .with_message_count()
                .prefetch_related("participants", "book__authors", "book__genres", "book__isbn")
                .filter(book__visibility=Book.Visibility.PUBLIC, book__is_hidden_by_admin=False)
                .filter(start_date__gt=today)
                .order_by("start_date", "title")[:8]
            )
            for club in upcoming_clubs_qs:
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

        if not active_marathons:
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
                .filter(start_date__gt=today)
                .order_by("start_date", "title", "id")
                [:8]
            )

        reading_items: list[ShelfItem] = []
        if request.user.is_authenticated:
            ensure_default_shelves(request.user)
            reading_shelf = (
                Shelf.objects.filter(
                    user=request.user,
                    name__in=(DEFAULT_READING_SHELF, READING_PROGRESS_LABEL),
                )
                .order_by("-is_default", "id")
                .first()
            )
            if reading_shelf:
                reading_items = list(
                    ShelfItem.objects.filter(shelf=reading_shelf)
                    .filter(book__in=Book.objects.visible_to_user(request.user))
                    .select_related("book")
                    .prefetch_related("book__authors", "book__genres")[:4]
                )

                book_ids = [item.book_id for item in reading_items]
                progress_map = (
                    {
                        progress.book_id: progress
                        for progress in BookProgress.objects.filter(
                            user=request.user,
                            event__isnull=True,
                            book_id__in=book_ids,
                        )
                    }
                    if book_ids
                    else {}
                )

                for item in reading_items:
                    progress = progress_map.get(item.book_id)
                    item.progress = None
                    item.progress_percent = None
                    item.progress_label = None
                    item.progress_total_pages = None
                    item.progress_current_page = None
                    item.progress_updated_at = None
                    item.progress_id = None
                    item.tracker_url = None

                    if not progress:
                        continue

                    item.progress = progress
                    item.progress_percent = float(progress.percent or 0)
                    item.progress_label = progress.get_format_display()
                    item.progress_total_pages = progress.get_effective_total_pages()
                    item.progress_current_page = progress.current_page
                    item.progress_updated_at = progress.updated_at
                    item.progress_id = progress.id
                    item.tracker_url = f"/tracker/{progress.id}/"

        recent_updates = (
            ReadingLog.objects.select_related("progress__user", "progress__book", "progress__user__profile")
            .filter(
                progress__event__isnull=True,
                progress__book__visibility=Book.Visibility.PUBLIC,
                progress__book__is_hidden_by_admin=False,
            )
            .order_by("-log_date", "-id")[:15]
        )

        reading_metrics = None
        greeting = None

        if request.user.is_authenticated:
            name = request.user.first_name or request.user.username or request.user.email
            greeting = f"Привет, {name}!" if name else "Привет!"

            weekly_logs = (
                ReadingLog.objects.filter(
                    progress__user=request.user,
                    log_date__gte=weekly_start,
                    log_date__lte=today,
                )
                .values("log_date")
                .annotate(
                    pages=Coalesce(
                        Sum("pages_equivalent"),
                        Value(0),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    )
                )
            )

            daily_pages = {entry["log_date"]: float(entry["pages"] or 0) for entry in weekly_logs}
            total_pages = sum(daily_pages.values())

            reading_metrics = {
                "week_start": weekly_start,
                "week_end": today,
                "total_pages": float(total_pages),
                "average_pages_per_day": float(total_pages) / 7 if total_pages else 0.0,
                "daily": [
                    {
                        "date": weekly_start + timedelta(days=offset),
                        "pages": daily_pages.get(weekly_start + timedelta(days=offset), 0.0),
                    }
                    for offset in range(7)
                ],
            }

        payload = {
            "hero": {
                "headline": "Калейдоскоп книг",
                "subtitle": "Сообщества, марафоны и личные подборки в одном экране.",
                "timestamp": timezone.now(),
                "greeting": greeting,
            },
            "active_clubs": ReadingClubSerializer(active_clubs, many=True).data,
            "active_marathons": ReadingMarathonSerializer(
                active_marathons,
                many=True,
                context={"request": request},
            ).data,
            "reading_items": ReadingShelfItemSerializer(reading_items, many=True).data,
            "reading_updates": ReadingUpdateSerializer(
                recent_updates,
                many=True,
                context={"request": request},
            ).data,
            "reading_metrics": reading_metrics,
        }

        return Response(payload)


class StatsView(APIView):
    """Reading stats for the mobile client."""

    def get(self, request, *args, **kwargs):
        today = timezone.localdate()
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)

        books_per_month = [0] * 12
        challenge_progress = 0
        calendar = [0] * 7

        if request.user.is_authenticated:
            year_logs = ReadingLog.objects.filter(
                progress__user=request.user,
                log_date__year=today.year,
            )

            month_rows = (
                year_logs.values("log_date__month")
                .annotate(total=Sum("pages_equivalent"))
                .order_by("log_date__month")
            )
            for row in month_rows:
                month = row["log_date__month"]
                if month:
                    books_per_month[month - 1] = int(float(row["total"] or 0) // 300)

            monthly_pages = (
                ReadingLog.objects.filter(
                    progress__user=request.user,
                    log_date__gte=month_start,
                    log_date__lte=today,
                ).aggregate(total=Sum("pages_equivalent")).get("total")
                or 0
            )
            challenge_progress = min(100, int((float(monthly_pages) / 3000) * 100))

            week_start = today - timedelta(days=6)
            week_days = {week_start + timedelta(days=offset): 0 for offset in range(7)}
            week_rows = (
                ReadingLog.objects.filter(
                    progress__user=request.user,
                    log_date__gte=week_start,
                    log_date__lte=today,
                )
                .values("log_date")
                .annotate(total=Sum("pages_equivalent"))
            )
            for row in week_rows:
                day = row["log_date"]
                week_days[day] = float(row["total"] or 0)

            calendar = [1 if week_days[day] > 0 else 0 for day in sorted(week_days.keys())]

        return Response(
            {
                "year": year_start.year,
                "books_per_month": books_per_month,
                "challenge_progress": challenge_progress,
                "calendar": calendar,
            }
        )
