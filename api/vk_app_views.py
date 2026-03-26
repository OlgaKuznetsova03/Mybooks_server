from django.contrib.auth import authenticate, get_user_model
from django.db.models import Q
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Profile
from books.models import Book

from .authentication import issue_mobile_token
from .pagination import StandardResultsSetPagination
from .serializers import BookListSerializer
from .vk_app_serializers import (
    VKAppBookCreateSerializer,
    VKAppBookDetailSerializer,
    VKAppLoginSerializer,
    VKAppProfileSerializer,
    VKAppRegisterSerializer,
)


class VKAppLoginView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = VKAppLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].lower()
        password = serializer.validated_data["password"]

        user_model = get_user_model()
        candidate = user_model.objects.filter(email__iexact=email).first()
        user = None
        if candidate:
            user = authenticate(request, username=candidate.username, password=password)
        if not user:
            return Response(
                {"detail": "Неверный email или пароль."},
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


class VKAppRegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = VKAppRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.save()
        token = issue_mobile_token(user)

        return Response(
            {
                "token": token,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "roles": list(user.groups.values_list("name", flat=True)),
                },
            },
            status=status.HTTP_201_CREATED,
        )


class VKAppProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        serializer = VKAppProfileSerializer(profile, context={"request": request})

        books_added_count = request.user.contributed_books.count()

        return Response(
            {
                "profile": serializer.data,
                "stats": {
                    "books_added": books_added_count,
                },
            }
        )


class VKAppBookListCreateView(generics.ListCreateAPIView):
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return VKAppBookCreateSerializer
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
                    | Q(isbn__isbn__icontains=cleaned)
                    | Q(isbn__isbn13__icontains=cleaned)
                ).distinct()

        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        book = serializer.save()
        detail = VKAppBookDetailSerializer(book, context={"request": request})
        headers = self.get_success_headers(detail.data)
        return Response(detail.data, status=status.HTTP_201_CREATED, headers=headers)


class VKAppBookDetailView(generics.RetrieveAPIView):
    serializer_class = VKAppBookDetailSerializer
    queryset = (
        Book.objects.select_related("primary_isbn")
        .prefetch_related("authors", "genres", "isbn")
        .order_by("-created_at", "-id")
    )