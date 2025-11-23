from rest_framework import serializers

from books.models import Author, Book, Genre
from reading_clubs.models import ReadingClub
from reading_marathons.models import ReadingMarathon


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
        ]

    def get_status(self, obj: ReadingMarathon) -> str:
        return obj.status

    def get_participant_count(self, obj: ReadingMarathon) -> int:
        return obj.participants.count()