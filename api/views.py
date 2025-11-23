from django.utils import timezone
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from books.models import Book
from reading_clubs.models import ReadingClub
from reading_marathons.models import ReadingMarathon

from .pagination import StandardResultsSetPagination
from .serializers import (
    BookDetailSerializer,
    BookListSerializer,
    ReadingClubSerializer,
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