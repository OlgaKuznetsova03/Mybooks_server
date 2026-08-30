import logging
import traceback
from collections import OrderedDict
from datetime import timedelta

from django.core.exceptions import ObjectDoesNotExist
from django.db import DataError, DatabaseError, IntegrityError, transaction
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from books.models import Book
from shelves.models import BookProgress, BookProgressReaction, ReadingLog, ShelfItem
from shelves.services import (
    ALL_DEFAULT_READ_SHELF_NAMES,
    DEFAULT_HOME_LIBRARY_SHELF,
    DEFAULT_READING_SHELF,
    DEFAULT_UNFINISHED_SHELF,
    DEFAULT_WANT_SHELF,
    ensure_default_shelves,
)

from .models import VKAccount
from .authentication import issue_mobile_token
from .serializers import BookListSerializer
from .vk_serializers import (
    VKAccountSerializer,
    VKBookSerializer,
    VKConnectSerializer,
    VKUserSerializer,
)

logger = logging.getLogger(__name__)

HOME_REACTION_CHOICES = [
    "\U0001f44d",
    "\u2764\ufe0f",
    "\U0001f525",
    "\U0001f44f",
    "\U0001f60d",
    "\U0001f62e",
    "\U0001f602",
    "\U0001f622",
]


def _normalize_progress_reaction(emoji):
    return str(emoji or "").strip().replace("\ufe0f", "")


ALLOWED_PROGRESS_REACTIONS = {
    _normalize_progress_reaction(emoji) for emoji in HOME_REACTION_CHOICES
}



class VKLoginView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        try:
            print("=== VK LOGIN REQUEST ===")
            print("Request data:", request.data)
            
            vk_user_id = request.data.get("vk_user_id")
            vk_access_token = request.data.get("vk_access_token", "")

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
            try:
                user.last_login = timezone.now()
                user.save(update_fields=["last_login"])
            except DatabaseError:
                pass

            return Response(
                {
                    "token": token,
                    "user": VKUserSerializer(user).data,
                    "vk_account": VKAccountSerializer(vk_account).data,
                }
            )
        except Exception as e:
            print("=== VK LOGIN ERROR ===")
            traceback.print_exc()
            logger.exception("VKLoginView error")
            return Response(
                {"error": str(e), "trace": traceback.format_exc()},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


def _get_bookshelf_payload(user, request=None, recent_limit=5, public_only=False):
    progress_qs = (
        BookProgress.objects.filter(user=user)
        .select_related("book")
        .prefetch_related("book__authors")
        .order_by("-updated_at")
    )
    if public_only:
        progress_qs = progress_qs.filter(
            book__visibility=Book.Visibility.PUBLIC,
            book__is_hidden_by_admin=False,
        )
    current_progress = progress_qs.filter(is_active=True).first() or progress_qs.first()

    recent_items_qs = (
        ShelfItem.objects.filter(shelf__user=user)
        .select_related("book")
        .prefetch_related("book__authors")
        .order_by("-added_at")
    )
    if public_only:
        recent_items_qs = recent_items_qs.filter(
            book__visibility=Book.Visibility.PUBLIC,
            book__is_hidden_by_admin=False,
        )
    recent_items = recent_items_qs[:recent_limit]

    today = timezone.localdate()
    this_month_start = today.replace(day=1)
    next_month_start = (this_month_start + timedelta(days=32)).replace(day=1)

    month_logs = ReadingLog.objects.filter(
        progress__user=user,
        log_date__gte=this_month_start,
        log_date__lt=next_month_start,
    )
    if public_only:
        month_logs = month_logs.filter(
            progress__book__visibility=Book.Visibility.PUBLIC,
            progress__book__is_hidden_by_admin=False,
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
    if public_only:
        month_read_items = month_read_items.filter(
            book__visibility=Book.Visibility.PUBLIC,
            book__is_hidden_by_admin=False,
        )
    read_books_this_month = month_read_items.values("book_id").distinct().count()

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


VK_APP_SHELF_DEFINITIONS = (
    ("want_to_read", DEFAULT_WANT_SHELF, (DEFAULT_WANT_SHELF,)),
    ("reading", DEFAULT_READING_SHELF, (DEFAULT_READING_SHELF,)),
    ("library", DEFAULT_HOME_LIBRARY_SHELF, (DEFAULT_HOME_LIBRARY_SHELF,)),
    ("read", "Прочитал", ALL_DEFAULT_READ_SHELF_NAMES),
    ("unfinished", DEFAULT_UNFINISHED_SHELF, (DEFAULT_UNFINISHED_SHELF,)),
)
VK_APP_SHELF_NAMES = tuple(
    OrderedDict.fromkeys(
        shelf_name
        for _, _, shelf_names in VK_APP_SHELF_DEFINITIONS
        for shelf_name in shelf_names
    )
)
VK_APP_SHELF_CODE_BY_NAME = {
    shelf_name: code
    for code, _, shelf_names in VK_APP_SHELF_DEFINITIONS
    for shelf_name in shelf_names
}


def _get_total_pages_read(user, read_items, progress_map, public_only=False) -> float:
    logs_qs = ReadingLog.objects.filter(progress__user=user)
    if public_only:
        logs_qs = logs_qs.filter(
            progress__book__visibility=Book.Visibility.PUBLIC,
            progress__book__is_hidden_by_admin=False,
        )
    logged_pages = (
        logs_qs.exclude(medium=BookProgress.FORMAT_AUDIO)
        .aggregate(total=Sum("pages_equivalent"))["total"]
        or 0
    )
    logged_book_ids = set(
        logs_qs.filter(pages_equivalent__gt=0)
        .exclude(medium=BookProgress.FORMAT_AUDIO)
        .values_list("progress__book_id", flat=True)
    )

    total = logged_pages
    for item in read_items:
        if item.book_id in logged_book_ids:
            continue
        progress = progress_map.get(item.book_id)
        if progress and progress.is_audiobook:
            continue
        pages = (
            progress.get_effective_total_pages()
            if progress
            else item.book.get_total_pages()
        ) or 0
        total += pages

    return float(total)


def build_user_shelves_payload(user, request=None, public_only=False):
    ensure_default_shelves(user)
    serializer_context = {"request": request} if request else {}
    shelves = {code: [] for code, _, _ in VK_APP_SHELF_DEFINITIONS}

    items_qs = (
        ShelfItem.objects.filter(
            shelf__user=user,
            shelf__name__in=VK_APP_SHELF_NAMES,
        )
        .select_related("shelf", "book", "selected_edition", "home_entry")
        .prefetch_related("book__authors", "book__genres", "book__isbn", "home_entry__custom_genres")
        .order_by("-added_at", "-id")
    )
    if public_only:
        items_qs = items_qs.filter(
            book__visibility=Book.Visibility.PUBLIC,
            book__is_hidden_by_admin=False,
        )
    items = list(items_qs)
    book_ids = [item.book_id for item in items]
    progress_map = {}

    if book_ids:
        progresses = (
            BookProgress.objects.filter(
                user=user,
                event__isnull=True,
                book_id__in=book_ids,
            )
            .select_related("book")
            .order_by("book_id", "-is_active", "-updated_at")
        )
        for progress in progresses:
            progress_map.setdefault(progress.book_id, progress)

    read_dates_by_book_id = {}
    for shelf_item in items:
        if VK_APP_SHELF_CODE_BY_NAME.get(shelf_item.shelf.name) != "read":
            continue
        if not shelf_item.added_at:
            continue

        added_date = timezone.localtime(shelf_item.added_at).date()
        previous_date = read_dates_by_book_id.get(shelf_item.book_id)
        read_dates_by_book_id[shelf_item.book_id] = min(previous_date, added_date) if previous_date else added_date

    read_items = []
    for item in items:
        status_code = VK_APP_SHELF_CODE_BY_NAME.get(item.shelf.name)
        if not status_code:
            continue

        if status_code == "read":
            read_items.append(item)

        book_data = dict(BookListSerializer(item.book, context=serializer_context).data)
        progress = progress_map.get(item.book_id)
        try:
            home_entry = item.home_entry
        except ObjectDoesNotExist:
            home_entry = None
        total_pages = progress.get_effective_total_pages() if progress else None

        book_data.update(
            {
                "status": status_code,
                "shelf": status_code,
                "shelf_label": item.shelf.name,
                "added_at": item.added_at,
                "selected_edition_id": item.selected_edition_id,
            }
        )
        if progress:
            book_data["progress_percent"] = float(progress.percent or 0)
            book_data["current_page"] = progress.current_page
            book_data["progress_id"] = progress.id
            book_data["tracker_url"] = f"/tracker/{progress.id}/"
        if total_pages:
            book_data["total_pages"] = total_pages
            book_data["pages_count"] = total_pages
        if home_entry:
            custom_genres = [
                {
                    "id": genre.id,
                    "name": genre.name,
                    "slug": genre.slug,
                }
                for genre in home_entry.custom_genres.all()
            ]
            home_library_data = {
                "format": home_entry.get_format_display(),
                "format_code": home_entry.format,
                "status": home_entry.status,
                "location": home_entry.location,
                "shelf_section": home_entry.shelf_section,
                "acquired_at": home_entry.acquired_at,
                "read_at": home_entry.read_at,
                "condition": home_entry.condition,
                "edition": home_entry.edition,
                "language": home_entry.language,
                "series_name": home_entry.series_name,
                "notes": home_entry.notes,
                "custom_genres": custom_genres,
                "is_classic": home_entry.is_classic,
                "is_disposed": home_entry.is_disposed,
                "disposition_note": home_entry.disposition_note,
            }
            book_data["home_library"] = home_library_data
            book_data["home_entry"] = home_library_data
            book_data["acquired_at"] = home_entry.acquired_at
            book_data["purchase_date"] = home_entry.acquired_at
            book_data["home_library_format"] = home_entry.get_format_display()
            book_data["home_library_format_code"] = home_entry.format
            book_data["home_library_status"] = home_entry.status
            book_data["location"] = home_entry.location
            book_data["shelf_section"] = home_entry.shelf_section
            book_data["condition"] = home_entry.condition
            book_data["edition"] = home_entry.edition
            book_data["language"] = home_entry.language
            book_data["home_library_language"] = home_entry.language
            book_data["series_name"] = home_entry.series_name
            book_data["home_library_notes"] = home_entry.notes
            book_data["disposition_note"] = home_entry.disposition_note
            book_data["home_library_disposition_note"] = home_entry.disposition_note
            book_data["custom_genres"] = custom_genres
            book_data["is_classic"] = home_entry.is_classic
            book_data["is_disposed"] = home_entry.is_disposed
        if home_entry and home_entry.read_at:
            book_data["read_at"] = home_entry.read_at
            book_data["read_date"] = home_entry.read_at
        elif status_code == "library":
            read_at = read_dates_by_book_id.get(item.book_id)
            if not read_at and progress and progress.finished_at:
                read_at = progress.finished_at
            if read_at:
                book_data["read_at"] = read_at
                book_data["read_date"] = read_at
        elif status_code == "read":
            read_at = progress.finished_at if progress and progress.finished_at else timezone.localtime(item.added_at).date()
            book_data["read_at"] = read_at
            book_data["read_date"] = read_at

        shelves[status_code].append(book_data)

    all_books = [book for code, _, _ in VK_APP_SHELF_DEFINITIONS for book in shelves[code]]
    shelf_counts = {code: len(shelves[code]) for code, _, _ in VK_APP_SHELF_DEFINITIONS}
    unique_book_ids = {item.book_id for item in items}
    pages_read = _get_total_pages_read(user, read_items, progress_map, public_only=public_only)

    return {
        "books": all_books,
        "shelves": shelves,
        "shelf_counts": shelf_counts,
        "stats": {
            "books_count": len(unique_book_ids),
            "library_books_count": shelf_counts["library"],
            "pages_read": pages_read,
            "total_pages": pages_read,
        },
    }

class VKConnectView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        try:
            print("=== VK CONNECT VIEW ===")
            print("Request user:", request.user.id, request.user.username)
            print("Request data:", request.data)
            
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
            
            print("Defaults to save:", defaults)

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
                    print("Existing VK account found")
                    if current_account and current_account.pk != existing_vk_account.pk:
                        current_account.delete()

                    existing_vk_account.user = request.user
                    for field, value in defaults.items():
                        setattr(existing_vk_account, field, value)
                    existing_vk_account.save()
                elif current_account:
                    print("Current account exists, updating")
                    for field, value in defaults.items():
                        setattr(current_account, field, value)
                    current_account.save()
                else:
                    print("Creating NEW VK account for user:", request.user.id)
                    VKAccount.objects.create(user=request.user, **defaults)
                    
            print("VK Connect successful")
            return Response({"linked": True})
            
        except Exception as e:
            print("=== VK CONNECT ERROR ===")
            traceback.print_exc()
            logger.exception("VKConnectView error")
            return Response(
                {"error": str(e), "trace": traceback.format_exc()},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


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
        shelves_payload = build_user_shelves_payload(request.user, request=request)
        requested_status = request.query_params.get("status") or request.query_params.get("shelf")
        status_books = shelves_payload["shelves"].get(requested_status)
        books = status_books if status_books is not None else shelves_payload["books"]

        return Response(
            {
                "profile": VKUserSerializer(request.user).data,
                "current_book": payload["current_book"],
                "recent_books": payload["recent_books"],
                "stats": {
                    **payload["stats"],
                    **shelves_payload["stats"],
                },
                "books": books,
                "count": len(books),
                "shelves": shelves_payload["shelves"],
                "shelf_counts": shelves_payload["shelf_counts"],
            }
        )


class VKProgressFeedView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _build_absolute_url(self, request, url):
        if not url:
            return ""

        if str(url).startswith(("http://", "https://")):
            return url

        return request.build_absolute_uri(url)

    def _get_user_avatar(self, request, user):
        try:
            profile = user.profile
        except ObjectDoesNotExist:
            profile = None

        avatar = getattr(profile, "avatar", None)
        if not avatar:
            return ""

        return self._build_absolute_url(request, avatar.url)

    def _get_user_reactions(self, progress, user):
        if not user or not user.is_authenticated:
            return []

        return sorted({
            reaction.emoji
            for reaction in progress.emoji_reactions.all()
            if reaction.user_id == user.id
        })

    def _get_reactions(self, progress, user=None):
        counts = {}
        active_emojis = set(self._get_user_reactions(progress, user))

        for reaction in progress.emoji_reactions.all():
            counts[reaction.emoji] = counts.get(reaction.emoji, 0) + 1

        return [
            {"label": emoji, "count": count, "active": emoji in active_emojis}
            for emoji, count in sorted(counts.items(), key=lambda item: item[0])
        ]

    def _serialize_progress(self, request, progress):
        total_pages = progress.get_effective_total_pages()
        cover_url = progress.book.get_cover_url()

        return {
            "id": progress.id,
            "book_id": progress.book_id,
            "book_title": progress.book.title,
            "cover_url": self._build_absolute_url(request, cover_url),
            "user_id": progress.user_id,
            "user_username": progress.user.username,
            "user_name": progress.user.get_full_name() or progress.user.username,
            "user_avatar": self._get_user_avatar(request, progress.user),
            "updated_at": progress.updated_at.isoformat(),
            "log_date": progress.updated_at.date().isoformat(),
            "current_page": progress.current_page,
            "progress_percent": float(progress.percent or 0),
            "total_pages": total_pages,
            "tracker_url": f"/tracker/{progress.id}/",
            "reactions": self._get_reactions(progress, request.user),
            "user_reactions": self._get_user_reactions(progress, request.user),
        }

    def get(self, request, *args, **kwargs):
        try:
            limit = int(request.query_params.get("limit", 15))
        except (TypeError, ValueError):
            limit = 15

        limit = max(1, min(limit, 50))
        progresses = list(
            BookProgress.objects.filter(
                event__isnull=True,
                book__visibility=Book.Visibility.PUBLIC,
                book__is_hidden_by_admin=False,
            )
            .select_related(
                "user",
                "user__profile",
                "book",
                "book__primary_isbn",
            )
            .prefetch_related("book__isbn", "emoji_reactions")
            .order_by("-updated_at", "-id")[:limit]
        )

        return Response(
            {
                "reading_updates": [
                    self._serialize_progress(request, progress)
                    for progress in progresses
                ],
                "count": len(progresses),
            }
        )



class VKProgressReactionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _serialize_reactions(self, progress, user):
        counts = (
            BookProgressReaction.objects.filter(progress=progress)
            .values("emoji")
            .annotate(count=Count("id"))
            .order_by("emoji")
        )
        user_reactions = set(
            BookProgressReaction.objects.filter(progress=progress, user=user)
            .values_list("emoji", flat=True)
        )
        return [
            {
                "label": item["emoji"],
                "count": item["count"],
                "active": item["emoji"] in user_reactions,
            }
            for item in counts
        ], sorted(user_reactions)

    def post(self, request, progress_id, *args, **kwargs):
        emoji = _normalize_progress_reaction(request.data.get("emoji") or request.POST.get("emoji") or "")
        if emoji not in ALLOWED_PROGRESS_REACTIONS:
            return Response(
                {"detail": "Недоступная реакция."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        progress = BookProgress.objects.filter(
            pk=progress_id,
            event__isnull=True,
            book__visibility=Book.Visibility.PUBLIC,
            book__is_hidden_by_admin=False,
        ).first()
        if not progress:
            return Response(
                {"detail": "Запись прогресса не найдена."},
                status=status.HTTP_404_NOT_FOUND,
            )

        reaction, created = BookProgressReaction.objects.get_or_create(
            progress=progress,
            user=request.user,
            emoji=emoji,
        )
        if not created:
            reaction.delete()

        reactions, user_reactions = self._serialize_reactions(progress, request.user)
        return Response(
            {
                "ok": True,
                "active": created,
                "emoji": emoji,
                "reactions": reactions,
                "user_reactions": user_reactions,
            }
        )


class VKPublicShelfView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, vk_user_id, *args, **kwargs):
        vk_account = VKAccount.objects.select_related("user").filter(vk_user_id=vk_user_id).first()
        if not vk_account:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        is_owner = request.user.is_authenticated and request.user.pk == vk_account.user_id
        public_only = not is_owner
        payload = _get_bookshelf_payload(
            vk_account.user,
            request=request,
            recent_limit=5,
            public_only=public_only,
        )
        shelves_payload = build_user_shelves_payload(
            vk_account.user,
            request=request,
            public_only=public_only,
        )
        return Response(
            {
                "name": f"{vk_account.first_name} {vk_account.last_name}".strip() or vk_account.user.username,
                "avatar": vk_account.photo_100,
                "current_book": payload["current_book"],
                "recent_books": payload["recent_books"],
                "books_this_month": payload["stats"]["books_this_month"],
                "books": shelves_payload["books"],
                "shelves": shelves_payload["shelves"],
                "shelf_counts": shelves_payload["shelf_counts"],
                "stats": shelves_payload["stats"],
            }
        )


class VKWidgetView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, vk_user_id, *args, **kwargs):
        vk_account = VKAccount.objects.select_related("user").filter(vk_user_id=vk_user_id).first()
        if not vk_account:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        payload = _get_bookshelf_payload(vk_account.user, request=request, recent_limit=5, public_only=True)
        return Response(payload)
