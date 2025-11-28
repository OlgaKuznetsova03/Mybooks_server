from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Sum, Value
from datetime import timedelta
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from books.models import Book
from reading_clubs.models import ReadingClub
from reading_marathons.models import MarathonParticipant, MarathonTheme, ReadingMarathon
from shelves.models import BookProgress, ReadingLog, Shelf, ShelfItem

from .pagination import StandardResultsSetPagination
from .serializers import (
    BookCreateSerializer,
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


class BookListView(generics.ListCreateAPIView):
    """Lightweight list of books for the new mobile client."""

    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self):
        if self.request.method == "POST":
            return BookCreateSerializer
        return BookListSerializer

    def get_queryset(self):
        queryset = (
            Book.objects.select_related("primary_isbn")
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
                queryset = queryset.filter(
                    Q(title__icontains=cleaned)
                    | Q(synopsis__icontains=cleaned)
                    | Q(authors__name__icontains=cleaned)
                    | Q(genres__name__icontains=cleaned)
                ).distinct()

        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        book = serializer.save()
        detail = BookDetailSerializer(book, context={"request": request})
        headers = self.get_success_headers(detail.data)
        return Response(detail.data, status=status.HTTP_201_CREATED, headers=headers)


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
        weekly_start = today - timedelta(days=6)

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
                .annotate(pages=Coalesce(Sum("pages_equivalent"), Value(0)))
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
            "active_marathons": ReadingMarathonSerializer(active_marathons, many=True).data,
            "reading_items": ReadingShelfItemSerializer(reading_items, many=True).data,
            "reading_metrics": reading_metrics,
        }

        return Response(payload)