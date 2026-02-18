from rest_framework import serializers

from books.models import Author, Book, Genre
from reading_clubs.models import ReadingClub
from reading_marathons.models import ReadingMarathon
from shelves.models import ShelfItem


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ["id", "name"]


class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = ["id", "name", "slug"]


class BookListSerializer(serializers.ModelSerializer):
    authors = AuthorSerializer(many=True, read_only=True)
    genres = GenreSerializer(many=True, read_only=True)
    cover_url = serializers.SerializerMethodField()
    total_pages = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = [
            "id",
            "title",
            "synopsis",
            "series",
            "series_order",
            "language",
            "cover_url",
            "total_pages",
            "average_rating",
            "authors",
            "genres",
        ]

    def get_cover_url(self, obj: Book) -> str:
        return obj.get_cover_url()

    def get_total_pages(self, obj: Book):
        return obj.get_total_pages()

    def get_average_rating(self, obj: Book):
        return obj.get_average_rating()


class IsbnSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    isbn = serializers.CharField()
    isbn13 = serializers.CharField(allow_null=True)
    title = serializers.CharField(allow_null=True)
    publisher = serializers.CharField(allow_null=True)
    publish_date = serializers.CharField(allow_null=True)
    total_pages = serializers.IntegerField(allow_null=True)
    binding = serializers.CharField(allow_null=True)
    synopsis = serializers.CharField(allow_null=True)
    language = serializers.CharField(allow_null=True)
    image = serializers.CharField(allow_null=True)


class BookDetailSerializer(BookListSerializer):
    isbn = IsbnSerializer(source="isbn.all", many=True, read_only=True)
    primary_isbn = serializers.SerializerMethodField()

    class Meta(BookListSerializer.Meta):
        fields = BookListSerializer.Meta.fields + [
            "isbn",
            "primary_isbn",
            "edition_group_key",
            "age_rating",
        ]

    def get_primary_isbn(self, obj: Book):
        primary = getattr(obj, "primary_isbn", None)
        if not primary:
            return None
        return IsbnSerializer(primary).data


class BookCreateSerializer(serializers.ModelSerializer):
    author_names = serializers.ListField(
        child=serializers.CharField(max_length=255),
        allow_empty=True,
        required=False,
        write_only=True,
    )
    genre_names = serializers.ListField(
        child=serializers.CharField(max_length=150),
        allow_empty=True,
        required=False,
        write_only=True,
    )

    class Meta:
        model = Book
        fields = [
            "title",
            "synopsis",
            "series",
            "series_order",
            "language",
            "age_rating",
            "author_names",
            "genre_names",
        ]

    def create(self, validated_data):
        from books.utils import normalize_genre_name

        author_names = validated_data.pop("author_names", []) or []
        genre_names = validated_data.pop("genre_names", []) or []

        book = Book.objects.create(**validated_data)

        authors: list[Author] = []
        for raw_name in author_names:
            name = raw_name.strip()
            if not name:
                continue
            author, _ = Author.objects.get_or_create(name=name)
            authors.append(author)

        genres: list[Genre] = []
        for raw_name in genre_names:
            normalized = normalize_genre_name(raw_name)
            if not normalized:
                continue
            genre, _ = Genre.objects.get_or_create(name=normalized)
            genres.append(genre)

        if authors:
            book.authors.set(authors)
        if genres:
            book.genres.set(genres)

        return book


class ReadingClubSerializer(serializers.ModelSerializer):
    book = BookListSerializer(read_only=True)
    status = serializers.SerializerMethodField()
    message_count = serializers.IntegerField(read_only=True)
    approved_participant_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ReadingClub
        fields = [
            "id",
            "title",
            "description",
            "start_date",
            "end_date",
            "join_policy",
            "slug",
            "status",
            "message_count",
            "approved_participant_count",
            "book",
        ]

    def get_status(self, obj: ReadingClub) -> str:
        return obj.status


class ReadingMarathonSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    participant_count = serializers.SerializerMethodField()
    theme_count = serializers.SerializerMethodField()

    class Meta:
        model = ReadingMarathon
        fields = [
            "id",
            "title",
            "description",
            "start_date",
            "end_date",
            "join_policy",
            "slug",
            "status",
            "participant_count",
            "theme_count",
        ]

    def get_status(self, obj: ReadingMarathon) -> str:
        return obj.status

    def get_participant_count(self, obj: ReadingMarathon) -> int:
        annotated_value = getattr(obj, "participant_count", None)
        if annotated_value is not None:
            return annotated_value
        return obj.participants.count()

    def get_theme_count(self, obj: ReadingMarathon) -> int:
        annotated_value = getattr(obj, "theme_count", None)
        if annotated_value is not None:
            return annotated_value
        return obj.themes.count()



class MobileAuthSerializer(serializers.Serializer):
    login = serializers.CharField(max_length=254, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        login = (
            attrs.get("login")
            or attrs.get("email")
            or attrs.get("username")
            or ""
        ).strip()
        if not login:
            raise serializers.ValidationError(
                {"login": "Передайте login, email или username."}
            )
        attrs["login"] = login
        return attrs


class MobileSignupSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False, min_length=8)

    def validate_username(self, value: str) -> str:
        from django.contrib.auth import get_user_model

        username = value.strip()
        if not username:
            raise serializers.ValidationError("Имя пользователя обязательно.")
        user_model = get_user_model()
        if user_model.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError("Пользователь с таким именем уже существует.")
        return username

    def validate_email(self, value: str) -> str:
        from django.contrib.auth import get_user_model

        normalized = value.lower()
        user_model = get_user_model()
        if user_model.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("Пользователь с таким email уже зарегистрирован.")
        return normalized

class ReadingShelfItemSerializer(serializers.ModelSerializer):
    """Item from the user's reading shelf with lightweight progress info."""

    book = BookListSerializer(read_only=True)
    progress_percent = serializers.FloatField(allow_null=True)
    progress_label = serializers.CharField(allow_null=True)
    progress_current_page = serializers.IntegerField(allow_null=True)
    progress_total_pages = serializers.IntegerField(allow_null=True)
    progress_updated_at = serializers.DateTimeField(allow_null=True)

    class Meta:
        model = ShelfItem
        fields = [
            "id",
            "added_at",
            "book",
            "progress_percent",
            "progress_label",
            "progress_current_page",
            "progress_total_pages",
            "progress_updated_at",
        ]