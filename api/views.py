from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.contrib.auth import authenticate, get_user_model
from datetime import timedelta
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from books.models import Book
from reading_clubs.models import ReadingClub
from reading_marathons.models import MarathonParticipant, MarathonTheme, ReadingMarathon
from shelves.models import BookProgress, ReadingLog, Shelf, ShelfItem
from shelves.services import DEFAULT_READING_SHELF, READING_PROGRESS_LABEL, ensure_default_shelves

from .authentication import issue_mobile_token
from .pagination import StandardResultsSetPagination
from .serializers import (
    BookCreateSerializer,
    BookDetailSerializer,
    BookListSerializer,
    MobileAuthSerializer,
    MobileSignupSerializer,
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

        token = issue_mobile_token(user)
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