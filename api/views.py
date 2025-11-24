from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from books.models import Book
from reading_clubs.models import ReadingClub
from reading_marathons.models import MarathonParticipant, MarathonTheme, ReadingMarathon
from shelves.models import BookProgress, Shelf, ShelfItem

from .pagination import StandardResultsSetPagination
from .serializers import (
    BookDetailSerializer,
    BookListSerializer,
    ReadingClubSerializer,
    ReadingShelfItemSerializer,
    ReadingMarathonSerializer,
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


class BookListView(generics.ListAPIView):
    """Lightweight list of books for the new mobile client."""

    serializer_class = BookListSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return (
            Book.objects.select_related("primary_isbn")
            .prefetch_related("authors", "genres", "isbn")
            .order_by("-created_at", "-id")
        )


class BookDetailView(generics.RetrieveAPIView):
    """Detailed book card with authors and edition data."""

    serializer_class = BookDetailSerializer
    queryset = (
        Book.objects.select_related("primary_isbn")
        .prefetch_related("authors", "genres", "isbn")
        .order_by("-created_at", "-id")
    )


class ReadingClubListView(generics.ListAPIView):
    """Active and upcoming reading clubs for communities tab."""

    serializer_class = ReadingClubSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return (
            ReadingClub.objects.with_message_count()
            .select_related("book", "book__primary_isbn")
            .prefetch_related("book__authors", "book__genres")
            .order_by("-start_date", "-created_at")
        )


class ReadingMarathonListView(generics.ListAPIView):
    """Reading marathons for the community feed."""

    serializer_class = ReadingMarathonSerializer
    pagination_class = StandardResultsSetPagination
    queryset = ReadingMarathon.objects.select_related(None).order_by(
        "-start_date", "-created_at"
    )


class HomeFeedView(APIView):
    """Aggregate data for the mobile home screen."""

    def get(self, request, *args, **kwargs):
        today = timezone.localdate()

        clubs_qs = (
            ReadingClub.objects.select_related("book", "book__primary_isbn", "creator")
            .with_message_count()
            .prefetch_related("participants", "book__authors", "book__genres", "book__isbn")
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
        if request.user.is_authenticated:
            reading_shelf = Shelf.objects.filter(user=request.user, name="Читаю").first()
            if reading_shelf:
                reading_items = list(
                    ShelfItem.objects.filter(shelf=reading_shelf)
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

                    if not progress:
                        continue

                    item.progress = progress
                    item.progress_percent = float(progress.percent or 0)
                    item.progress_label = progress.get_format_display()
                    item.progress_total_pages = progress.get_effective_total_pages()
                    item.progress_current_page = progress.current_page
                    item.progress_updated_at = progress.updated_at

        payload = {
            "hero": {
                "headline": "Калейдоскоп книг",
                "subtitle": "Сообщества, марафоны и личные подборки в одном экране.",
                "timestamp": timezone.now(),
            },
            "active_clubs": ReadingClubSerializer(active_clubs, many=True).data,
            "active_marathons": ReadingMarathonSerializer(active_marathons, many=True).data,
            "reading_items": ReadingShelfItemSerializer(reading_items, many=True).data,
        }

        return Response(payload)