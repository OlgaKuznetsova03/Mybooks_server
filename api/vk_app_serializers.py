import json
from datetime import date, datetime

from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from rest_framework import serializers

from accounts.forms import ROLE_CHOICES
from accounts.models import Profile
from books.api_clients import transliterate_to_cyrillic
from books.models import AudioBook, Author, Book, Genre, ISBNModel, Publisher
from reading_clubs.models import ReadingClub
from books.services import register_book_edition
from books.utils import normalize_genre_name, normalize_isbn
from shelves.models import BookProgress, ShelfItem
from shelves.services import DEFAULT_HOME_LIBRARY_SHELF, DEFAULT_READING_SHELF, get_default_shelf_status_map

from .serializers import BookDetailSerializer, ReadingClubSerializer


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
            raise serializers.ValidationError("Ð˜Ð¼Ñ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ Ð¾Ð±ÑÐ·Ð°Ñ‚ÐµÐ»ÑŒÐ½Ð¾.")
        user_model = get_user_model()
        if user_model.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError("ÐŸÐ¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑŒ Ñ Ñ‚Ð°ÐºÐ¸Ð¼ Ð¸Ð¼ÐµÐ½ÐµÐ¼ ÑƒÐ¶Ðµ ÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÐµÑ‚.")
        return username

    def validate_email(self, value: str) -> str:
        normalized = value.strip().lower()
        user_model = get_user_model()
        if user_model.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("ÐŸÐ¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑŒ Ñ Ñ‚Ð°ÐºÐ¸Ð¼ email ÑƒÐ¶Ðµ Ð·Ð°Ñ€ÐµÐ³Ð¸ÑÑ‚Ñ€Ð¸Ñ€Ð¾Ð²Ð°Ð½.")
        return normalized

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password2": "ÐŸÐ°Ñ€Ð¾Ð»Ð¸ Ð½Ðµ ÑÐ¾Ð²Ð¿Ð°Ð´Ð°ÑŽÑ‚."})
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
            "coin_balance",
            "has_active_premium",
            "has_unlimited_coins",
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


class VKAppProfileUpdateSerializer(serializers.ModelSerializer):
    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=[name for name, _ in ROLE_CHOICES]),
        required=False,
        allow_empty=True,
    )
    roles_payload = serializers.CharField(required=False, allow_blank=True, write_only=True)
    avatar = serializers.ImageField(required=False, allow_null=True)
    clear_avatar = serializers.BooleanField(required=False, default=False)
    link1 = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    link2 = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    link3 = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    link4 = serializers.URLField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Profile
        fields = [
            "avatar",
            "clear_avatar",
            "bio",
            "website",
            "is_private",
            "link1",
            "link2",
            "link3",
            "link4",
            "roles",
            "roles_payload",
        ]

    def validate(self, attrs):
        roles_payload = attrs.pop("roles_payload", None)
        if "roles" not in attrs and roles_payload is not None:
            try:
                roles = json.loads(roles_payload or "[]")
            except (TypeError, ValueError):
                raise serializers.ValidationError({"roles": "ÐÐµÐºÐ¾Ñ€Ñ€ÐµÐºÑ‚Ð½Ñ‹Ð¹ ÑÐ¿Ð¸ÑÐ¾Ðº Ñ€Ð¾Ð»ÐµÐ¹."})
            allowed = {name for name, _ in ROLE_CHOICES}
            if not isinstance(roles, list) or any(role not in allowed for role in roles):
                raise serializers.ValidationError({"roles": "ÐÐµÐºÐ¾Ñ€Ñ€ÐµÐºÑ‚Ð½Ñ‹Ð¹ ÑÐ¿Ð¸ÑÐ¾Ðº Ñ€Ð¾Ð»ÐµÐ¹."})
            attrs["roles"] = roles
        return attrs

    def _normalize_url_value(self, value):
        if value is None:
            return ""
        return str(value).strip()

    def update(self, instance: Profile, validated_data):
        roles = validated_data.pop("roles", None)
        clear_avatar = validated_data.pop("clear_avatar", False)

        if clear_avatar and instance.avatar:
            instance.avatar.delete(save=False)
            instance.avatar = None

        for field in ["bio", "website", "is_private", "link1", "link2", "link3", "link4", "avatar"]:
            if field not in validated_data:
                continue
            value = validated_data[field]
            if field in {"website", "link1", "link2", "link3", "link4"}:
                value = self._normalize_url_value(value)
            setattr(instance, field, value)

        instance.save()

        if roles is not None:
            for role_name, _ in ROLE_CHOICES:
                Group.objects.get_or_create(name=role_name)
            instance.user.groups.set(Group.objects.filter(name__in=roles))

        return instance


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
    cover_url = serializers.URLField(required=False, allow_blank=True, allow_null=True)
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
            raise serializers.ValidationError("Ð£ÐºÐ°Ð¶Ð¸Ñ‚Ðµ Ñ…Ð¾Ñ‚Ñ Ð±Ñ‹ Ð¾Ð´Ð½Ð¾Ð³Ð¾ Ð°Ð²Ñ‚Ð¾Ñ€Ð°.")
        authors = []
        for name in names:
            author, _ = Author.objects.get_or_create(name=name)
            authors.append(author)
        return authors

    def validate_genres(self, value: str):
        names = self._split_list(value)
        if not names:
            raise serializers.ValidationError("Ð£ÐºÐ°Ð¶Ð¸Ñ‚Ðµ Ñ…Ð¾Ñ‚Ñ Ð±Ñ‹ Ð¾Ð´Ð¸Ð½ Ð¶Ð°Ð½Ñ€.")
        genres = []
        for name in names:
            normalized = normalize_genre_name(name)
            if not normalized:
                continue
            genre, _ = Genre.objects.get_or_create(name=normalized)
            genres.append(genre)
        if not genres:
            raise serializers.ValidationError("Ð£ÐºÐ°Ð¶Ð¸Ñ‚Ðµ Ñ…Ð¾Ñ‚Ñ Ð±Ñ‹ Ð¾Ð´Ð¸Ð½ Ð¶Ð°Ð½Ñ€.")
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
                errors.append(f"ISBN '{raw}' Ð´Ð¾Ð»Ð¶ÐµÐ½ ÑÐ¾Ð´ÐµÑ€Ð¶Ð°Ñ‚ÑŒ 13 Ñ†Ð¸Ñ„Ñ€.")
                continue
            if not _is_valid_isbn13(digits):
                errors.append(f"ISBN-13 '{raw}' Ð½ÐµÐºÐ¾Ñ€Ñ€ÐµÐºÑ‚ÐµÐ½.")
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
                raise serializers.ValidationError("ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚Ð°Ñ‚ÑŒ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð¾Ð± Ð¸Ð·Ð´Ð°Ð½Ð¸Ð¸ Ð¸Ð· API.")
            if not isinstance(parsed, dict):
                raise serializers.ValidationError("ÐŸÐ¾Ð»ÑƒÑ‡ÐµÐ½Ñ‹ Ð½ÐµÐºÐ¾Ñ€Ñ€ÐµÐºÑ‚Ð½Ñ‹Ðµ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð¸Ð· API.")
            return parsed
        raise serializers.ValidationError("ÐŸÐ¾Ð»ÑƒÑ‡ÐµÐ½Ñ‹ Ð½ÐµÐºÐ¾Ñ€Ñ€ÐµÐºÑ‚Ð½Ñ‹Ðµ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð¸Ð· API.")

    def create(self, validated_data):
        user = self.context["request"].user
        is_author_user = user.groups.filter(name="author").exists()
        submitted_by_user = user if is_author_user and validated_data.get("confirm_authorship") else None
        cover_url = str(validated_data.get("cover_url") or "").strip()
        isbn_metadata = dict(validated_data.get("isbn_metadata") or {})

        if cover_url:
            if isbn_metadata:
                for details in isbn_metadata.values():
                    if isinstance(details, dict) and not details.get("cover_url"):
                        details["cover_url"] = cover_url
            else:
                isbn_metadata = {"external": {"cover_url": cover_url}}

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
            isbn_metadata=isbn_metadata,
            submitted_by=submitted_by_user,
            owner=user,
            visibility=Book.Visibility.PRIVATE,
        )
        return result.book


class VKAppBookDetailSerializer(BookDetailSerializer):
    user_shelf = serializers.SerializerMethodField()
    shelf = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    shelf_status = serializers.SerializerMethodField()
    in_library = serializers.SerializerMethodField()
    is_in_library = serializers.SerializerMethodField()
    read_at = serializers.SerializerMethodField()
    read_date = serializers.SerializerMethodField()
    acquired_at = serializers.SerializerMethodField()
    purchase_date = serializers.SerializerMethodField()
    progress_id = serializers.SerializerMethodField()
    progress_percent = serializers.SerializerMethodField()
    current_page = serializers.SerializerMethodField()
    tracker_url = serializers.SerializerMethodField()
    reading_clubs = serializers.SerializerMethodField()

    class Meta(BookDetailSerializer.Meta):
        model = Book
        fields = BookDetailSerializer.Meta.fields + [
            "created_at",
            "user_shelf",
            "shelf",
            "status",
            "shelf_status",
            "in_library",
            "is_in_library",
            "read_at",
            "read_date",
            "acquired_at",
            "purchase_date",
            "progress_id",
            "progress_percent",
            "current_page",
            "tracker_url",
            "reading_clubs",
        ]

    def get_reading_clubs(self, obj):
        clubs = (
            ReadingClub.objects.with_message_count()
            .filter(book=obj)
            .select_related("book", "book__primary_isbn", "creator")
            .prefetch_related("book__authors", "book__genres", "book__isbn")
            .order_by("start_date", "id")
        )
        return ReadingClubSerializer(clubs, many=True, context=self.context).data

    def _request_user(self):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            return None
        return user

    def _format_date(self, value):
        if not value:
            return None

        if isinstance(value, datetime):
            if timezone.is_aware(value):
                value = timezone.localtime(value)
            return value.date().isoformat()

        if isinstance(value, date):
            return value.isoformat()

        return str(value)

    def _get_state(self, obj):
        cache = getattr(self, "_vk_app_book_state_cache", None)
        if cache is None:
            cache = {}
            self._vk_app_book_state_cache = cache

        if obj.pk in cache:
            return cache[obj.pk]

        state = {
            "status": None,
            "label": None,
            "read_at": None,
            "acquired_at": None,
            "in_library": False,
            "progress": None,
        }
        user = self._request_user()

        if not user:
            cache[obj.pk] = state
            return state

        shelf_status = get_default_shelf_status_map(user, [obj.pk]).get(obj.pk)
        if shelf_status:
            state["status"] = shelf_status.get("code")
            state["label"] = shelf_status.get("label")
            if state["status"] == "read":
                state["read_at"] = shelf_status.get("added_at")

        reading_item_exists = ShelfItem.objects.filter(
            shelf__user=user,
            shelf__name=DEFAULT_READING_SHELF,
            book=obj,
        ).exists()

        home_item = (
            ShelfItem.objects
            .filter(shelf__user=user, shelf__name=DEFAULT_HOME_LIBRARY_SHELF, book=obj)
            .select_related("home_entry")
            .first()
        )
        if home_item:
            state["in_library"] = True
            if not state["status"]:
                state["status"] = "library"
                state["label"] = DEFAULT_HOME_LIBRARY_SHELF

            try:
                home_entry = home_item.home_entry
            except ObjectDoesNotExist:
                home_entry = None

            if home_entry:
                state["acquired_at"] = home_entry.acquired_at
                if home_entry.read_at:
                    state["read_at"] = home_entry.read_at

        progress = (
            BookProgress.objects
            .filter(user=user, book=obj, event__isnull=True, is_active=True)
            .order_by("-updated_at", "-id")
            .first()
        )
        if progress:
            state["progress"] = progress
            if reading_item_exists:
                state["status"] = "reading"
                state["label"] = DEFAULT_READING_SHELF

        cache[obj.pk] = state
        return state

    def get_user_shelf(self, obj):
        state = self._get_state(obj)
        status = state["status"]
        if not status:
            return None

        progress = state["progress"]
        payload = {
            "status": status,
            "shelf": status,
            "state": status,
            "label": state["label"] or status,
            "in_library": state["in_library"],
            "read_at": self._format_date(state["read_at"]),
            "read_date": self._format_date(state["read_at"]),
            "acquired_at": self._format_date(state["acquired_at"]),
            "purchase_date": self._format_date(state["acquired_at"]),
        }

        if progress:
            payload["progress_id"] = progress.id
            payload["progress_percent"] = float(progress.percent or 0)
            payload["current_page"] = progress.current_page
            payload["tracker_url"] = f"/tracker/{progress.id}/"

        return payload

    def get_shelf(self, obj):
        return self.get_user_shelf(obj)

    def get_status(self, obj):
        return self._get_state(obj)["status"]

    def get_shelf_status(self, obj):
        return self._get_state(obj)["status"]

    def get_in_library(self, obj):
        return self._get_state(obj)["in_library"]

    def get_is_in_library(self, obj):
        return self._get_state(obj)["in_library"]

    def get_read_at(self, obj):
        return self._format_date(self._get_state(obj)["read_at"])

    def get_read_date(self, obj):
        return self.get_read_at(obj)

    def get_acquired_at(self, obj):
        return self._format_date(self._get_state(obj)["acquired_at"])

    def get_purchase_date(self, obj):
        return self.get_acquired_at(obj)

    def get_progress_id(self, obj):
        progress = self._get_state(obj)["progress"]
        return progress.id if progress else None

    def get_progress_percent(self, obj):
        progress = self._get_state(obj)["progress"]
        return float(progress.percent or 0) if progress else None

    def get_current_page(self, obj):
        progress = self._get_state(obj)["progress"]
        return progress.current_page if progress else None

    def get_tracker_url(self, obj):
        progress = self._get_state(obj)["progress"]
        return f"/tracker/{progress.id}/" if progress else None

