from datetime import timedelta

from django.db import DataError, IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from shelves.models import BookProgress, ReadingLog, ShelfItem
from shelves.services import ALL_DEFAULT_READ_SHELF_NAMES

from .models import VKAccount
from .authentication import issue_mobile_token
from .vk_serializers import (
    VKAccountSerializer,
    VKBookSerializer,
    VKConnectSerializer,
    VKUserSerializer,
)


class VKLoginView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        vk_user_id = request.data.get("vk_user_id")

        if not vk_user_id:
            return Response(
                {"error": "vk_user_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            vk_user_id = int(vk_user_id)
        except (TypeError, ValueError):
            return Response(
                {"error": "vk_user_id must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if vk_user_id < 1 or vk_user_id > 9223372036854775807:
            return Response(
                {"error": "vk_user_id out of range"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            vk_account = (
                VKAccount.objects.select_related("user")
                .filter(vk_user_id=vk_user_id)
                .first()
            )
        except DataError:
            return Response(
                {"error": "vk_user_id out of range"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not vk_account:
            return Response(
                {
                    "error": "vk_not_linked",
                    "message": "VK аккаунт не привязан. Сначала войдите с email/паролем.",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user = vk_account.user
        if not user.is_active:
            return Response(
                {"error": "user_inactive"},
                status=status.HTTP_403_FORBIDDEN,
            )

        token = issue_mobile_token(user)
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])

        return Response(
            {
                "token": token,
                "user": VKUserSerializer(user).data,
                "vk_account": VKAccountSerializer(vk_account).data,
            }
        )


def _get_bookshelf_payload(user, request=None, recent_limit=5):
    progress_qs = (
        BookProgress.objects.filter(user=user)
        .select_related("book")
        .prefetch_related("book__authors")
        .order_by("-updated_at")
    )
    current_progress = progress_qs.filter(is_active=True).first() or progress_qs.first()

    recent_items = (
        ShelfItem.objects.filter(shelf__user=user)
        .select_related("book")
        .prefetch_related("book__authors")
        .order_by("-added_at")[:recent_limit]
    )

    today = timezone.localdate()
    this_month_start = today.replace(day=1)
    next_month_start = (this_month_start + timedelta(days=32)).replace(day=1)

    month_logs = ReadingLog.objects.filter(
        progress__user=user,
        log_date__gte=this_month_start,
        log_date__lt=next_month_start,
    )

    month_pages = (
        month_logs.exclude(medium=BookProgress.FORMAT_AUDIO).aggregate(total=Sum("pages_equivalent"))["total"]
        or 0
    )
    month_audio_seconds = month_logs.aggregate(total=Sum("audio_seconds"))["total"] or 0
    month_read_items = ShelfItem.objects.filter(
        shelf__user=user,
        shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
        added_at__date__gte=this_month_start,
        added_at__date__lt=next_month_start,
    )
    read_books_this_month = month_read_items.values("book_id").distinct().count()

    # Keep monthly pages in VK aligned with /accounts/statistics/:
    # for books moved to "read" this month but without explicit reading logs,
    # add fallback pages from book/progress metadata.
    month_logged_book_ids = set(
        month_logs.exclude(medium=BookProgress.FORMAT_AUDIO)
        .values_list("progress__book_id", flat=True)
    )
    if month_read_items.exists():
        progress_map = {
            progress.book_id: progress
            for progress in BookProgress.objects.filter(
                user=user,
                event__isnull=True,
                book_id__in=month_read_items.values_list("book_id", flat=True),
            )
        }
        for item in month_read_items.select_related("book"):
            if item.book_id in month_logged_book_ids:
                continue
            progress = progress_map.get(item.book_id)
            if progress and progress.is_audiobook:
                continue
            pages = (
                progress.get_effective_total_pages()
                if progress
                else item.book.get_total_pages()
            ) or 0
            if pages:
                month_pages += pages

    stats = {
        "books_this_month": read_books_this_month,
        "pages_this_month": float(month_pages),
        "audio_minutes_this_month": float(month_audio_seconds) / 60,
    }

    serializer_context = {"request": request} if request else {}

    current_book_data = None
    if current_progress:
        current_book_data = VKBookSerializer(
            current_progress.book,
            context=serializer_context,
        ).data
        current_book_data["progress_percent"] = float(current_progress.percent or 0)

    return {
        "current_book": current_book_data,
        "recent_books": VKBookSerializer(
            [item.book for item in recent_items],
            many=True,
            context=serializer_context,
        ).data,
        "stats": stats,
    }


class VKConnectView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = VKConnectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        vk_user_id = serializer.validated_data["vk_user_id"]
        defaults = {
            "vk_user_id": vk_user_id,
            "first_name": serializer.validated_data.get("first_name", ""),
            "last_name": serializer.validated_data.get("last_name", ""),
            "photo_100": serializer.validated_data.get("photo_100", ""),
            "screen_name": serializer.validated_data.get("screen_name", ""),
        }

        try:
            with transaction.atomic():
                current_account = (
                    VKAccount.objects.select_for_update()
                    .filter(user=request.user)
                    .first()
                )
                existing_vk_account = (
                    VKAccount.objects.select_for_update()
                    .filter(vk_user_id=vk_user_id)
                    .first()
                )

                if existing_vk_account:
                    if current_account and current_account.pk != existing_vk_account.pk:
                        current_account.delete()

                    existing_vk_account.user = request.user
                    for field, value in defaults.items():
                        setattr(existing_vk_account, field, value)
                    existing_vk_account.save()
                elif current_account:
                    for field, value in defaults.items():
                        setattr(current_account, field, value)
                    current_account.save()
                else:
                    VKAccount.objects.create(user=request.user, **defaults)
        except IntegrityError:
            return Response(
                {"detail": "Этот VK аккаунт уже привязан к другому пользователю."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"linked": True})


class VKMeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        vk_account = VKAccount.objects.filter(user=request.user).first()
        return Response(
            {
                "user": VKUserSerializer(request.user).data,
                "vk_account": VKAccountSerializer(vk_account).data if vk_account else None,
                "linked": vk_account is not None,
            }
        )


class VKShelfView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        payload = _get_bookshelf_payload(request.user, request=request, recent_limit=5)
        return Response(
            {
                "profile": VKUserSerializer(request.user).data,
                "current_book": payload["current_book"],
                "recent_books": payload["recent_books"],
                "stats": payload["stats"],
            }
        )


class VKPublicShelfView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, vk_user_id, *args, **kwargs):
        vk_account = VKAccount.objects.select_related("user").filter(vk_user_id=vk_user_id).first()
        if not vk_account:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        payload = _get_bookshelf_payload(vk_account.user, request=request, recent_limit=5)
        return Response(
            {
                "name": f"{vk_account.first_name} {vk_account.last_name}".strip() or vk_account.user.username,
                "avatar": vk_account.photo_100,
                "current_book": payload["current_book"],
                "recent_books": payload["recent_books"],
                "books_this_month": payload["stats"]["books_this_month"],
            }
        )


class VKWidgetView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, vk_user_id, *args, **kwargs):
        vk_account = VKAccount.objects.select_related("user").filter(vk_user_id=vk_user_id).first()
        if not vk_account:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        payload = _get_bookshelf_payload(vk_account.user, request=request, recent_limit=5)
        return Response(payload)