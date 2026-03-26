import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import serializers

from accounts.forms import ROLE_CHOICES
from accounts.models import Profile
from books.api_clients import transliterate_to_cyrillic
from books.models import AudioBook, Author, Book, Genre, ISBNModel, Publisher
from books.services import register_book_edition
from books.utils import normalize_genre_name, normalize_isbn

from .serializers import BookDetailSerializer


def _is_valid_isbn13(value: str) -> bool:
    if len(value) != 13 or not value.isdigit():
        return False
    checksum = sum((int(digit) * (1 if index % 2 == 0 else 3)) for index, digit in enumerate(value[:12]))
    check_digit = (10 - (checksum % 10)) % 10
    return check_digit == int(value[-1])


class VKAppLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class VKAppRegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False)
    password2 = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False)
    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=[name for name, _ in ROLE_CHOICES]),
        required=False,
        allow_empty=True,
    )

    def validate_username(self, value: str) -> str:
        username = value.strip()
        if not username:
            raise serializers.ValidationError("Имя пользователя обязательно.")
        user_model = get_user_model()
        if user_model.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError("Пользователь с таким именем уже существует.")
        return username

    def validate_email(self, value: str) -> str:
        normalized = value.strip().lower()
        user_model = get_user_model()
        if user_model.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("Пользователь с таким email уже зарегистрирован.")
        return normalized

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password2": "Пароли не совпадают."})
        return attrs

    def create(self, validated_data):
        roles = set(validated_data.pop("roles", []))
        validated_data.pop("password2", None)

        user_model = get_user_model()
        user = user_model.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
        )

        for role_name, _ in ROLE_CHOICES:
            Group.objects.get_or_create(name=role_name)

        if roles:
            user.groups.set(Group.objects.filter(name__in=roles))

        return user


class VKAppProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    roles = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    links = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "bio",
            "website",
            "is_private",
            "avatar_url",
            "roles",
            "links",
            "coins",
            "has_active_premium",
            "premium_expires_at",
        ]

    def get_avatar_url(self, obj: Profile) -> str:
        avatar = getattr(obj, "avatar", None)
        if not avatar:
            return ""

        try:
            url = avatar.url
        except Exception:
            return ""

        request = self.context.get("request")
        if request and not url.startswith(("http://", "https://", "//")):
            return request.build_absolute_uri(url)
        return url

    def get_roles(self, obj: Profile):
        return list(obj.user.groups.values_list("name", flat=True))

    def get_links(self, obj: Profile):
        return {
            "link1": obj.link1 or "",
            "link2": obj.link2 or "",
            "link3": obj.link3 or "",
            "link4": obj.link4 or "",
        }


class VKAppBookCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    authors = serializers.CharField()
    isbn = serializers.CharField(required=False, allow_blank=True)
    synopsis = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    series = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    series_order = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    genres = serializers.CharField()
    age_rating = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    language = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    cover = serializers.ImageField(required=False, allow_null=True)
    audio = serializers.PrimaryKeyRelatedField(queryset=AudioBook.objects.all(), required=False, allow_null=True)
    publisher = serializers.CharField(required=False, allow_blank=True)
    page_count = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    confirm_authorship = serializers.BooleanField(required=False, default=False)
    isbn_metadata = serializers.JSONField(required=False)

    def _split_list(self, value: str):
        if not value:
            return []
        parts = [part.strip() for part in value.replace("\n", ",").split(",")]
        return [part for part in parts if part]

    def validate_authors(self, value: str):
        names = self._split_list(value)
        if not names:
            raise serializers.ValidationError("Укажите хотя бы одного автора.")
        authors = []
        for name in names:
            author, _ = Author.objects.get_or_create(name=name)
            authors.append(author)
        return authors

    def validate_genres(self, value: str):
        names = self._split_list(value)
        if not names:
            raise serializers.ValidationError("Укажите хотя бы один жанр.")
        genres = []
        for name in names:
            normalized = normalize_genre_name(name)
            if not normalized:
                continue
            genre, _ = Genre.objects.get_or_create(name=normalized)
            genres.append(genre)
        if not genres:
            raise serializers.ValidationError("Укажите хотя бы один жанр.")
        return genres

    def validate_publisher(self, value: str):
        names = self._split_list(value)
        seen = set()
        publishers = []
        for name in names:
            normalized = transliterate_to_cyrillic(name).strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            publisher, _ = Publisher.objects.get_or_create(name=normalized)
            publishers.append(publisher)
        return publishers

    def validate_isbn(self, value: str):
        numbers = self._split_list(value)
        isbn_objects = []
        errors = []
        seen = set()
        for raw in numbers:
            digits = normalize_isbn(raw)
            if len(digits) != 13:
                errors.append(f"ISBN '{raw}' должен содержать 13 цифр.")
                continue
            if not _is_valid_isbn13(digits):
                errors.append(f"ISBN-13 '{raw}' некорректен.")
                continue
            if digits in seen:
                continue
            seen.add(digits)
            isbn_obj, _ = ISBNModel.objects.get_or_create(
                isbn=digits,
                defaults={"isbn13": digits},
            )
            if not isbn_obj.isbn13:
                isbn_obj.isbn13 = digits
                isbn_obj.save(update_fields=["isbn13"])
            isbn_objects.append(isbn_obj)
        if errors:
            raise serializers.ValidationError(errors)
        return isbn_objects

    def validate_isbn_metadata(self, value):
        if not value:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (TypeError, json.JSONDecodeError):
                raise serializers.ValidationError("Не удалось обработать данные об издании из API.")
            if not isinstance(parsed, dict):
                raise serializers.ValidationError("Получены некорректные данные из API.")
            return parsed
        raise serializers.ValidationError("Получены некорректные данные из API.")

    def create(self, validated_data):
        user = self.context["request"].user
        is_author_user = user.groups.filter(name="author").exists()
        submitted_by_user = user if is_author_user and validated_data.get("confirm_authorship") else None

        result = register_book_edition(
            title=validated_data["title"],
            authors=validated_data["authors"],
            genres=validated_data["genres"],
            publishers=validated_data.get("publisher", []),
            isbn_entries=validated_data.get("isbn", []),
            synopsis=validated_data.get("synopsis"),
            series=validated_data.get("series"),
            series_order=validated_data.get("series_order"),
            page_count=validated_data.get("page_count"),
            age_rating=validated_data.get("age_rating"),
            language=validated_data.get("language"),
            audio=validated_data.get("audio"),
            cover_file=validated_data.get("cover"),
            isbn_metadata=validated_data.get("isbn_metadata") or {},
            submitted_by=submitted_by_user,
        )
        return result.book


class VKAppBookDetailSerializer(BookDetailSerializer):
    class Meta(BookDetailSerializer.Meta):
        model = Book
        fields = BookDetailSerializer.Meta.fields + ["created_at"]