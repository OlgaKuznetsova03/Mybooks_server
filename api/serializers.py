from rest_framework import serializers

from books.models import Author, Book, Genre
from shelves.models import ReadingLog
from reading_clubs.models import (
    DiscussionPost,
    DiscussionPostReport,
    ReadingClub,
    ReadingNorm,
    ReadingParticipant,
)
from reading_marathons.models import MarathonEntry, MarathonParticipant, MarathonTheme, ReadingMarathon
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
    publisher = serializers.SerializerMethodField()
    publishers = serializers.SerializerMethodField()
    total_pages = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()
    reader_count = serializers.SerializerMethodField()
    added_at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = Book
        fields = [
            "id",
            "title",
            "synopsis",
            "series",
            "series_order",
            "language",
            "visibility",
            "is_hidden_by_admin",
            "publisher",
            "publishers",
            "cover_url",
            "total_pages",
            "average_rating",
            "reader_count",
            "added_at",
            "authors",
            "genres",
        ]

    def get_cover_url(self, obj: Book) -> str:
        cover_url = obj.get_cover_url()
        request = self.context.get("request")

        if not cover_url or not request:
            return cover_url

        if cover_url.startswith(("http://", "https://", "//")):
            return cover_url

        return request.build_absolute_uri(cover_url)

    def get_publishers(self, obj: Book) -> list[str]:
        names = list(obj.publisher.order_by("name").values_list("name", flat=True))

        if names:
            return names

        primary_isbn = getattr(obj, "primary_isbn", None)
        publisher = str(getattr(primary_isbn, "publisher", "") or "").strip()
        return [publisher] if publisher else []

    def get_publisher(self, obj: Book) -> str:
        return ", ".join(self.get_publishers(obj))

    def get_total_pages(self, obj: Book):
        return obj.get_total_pages()

    def get_average_rating(self, obj: Book):
        return obj.get_average_rating()

    def get_reader_count(self, obj: Book) -> int:
        return int(getattr(obj, "recent_reader_count", 0) or 0)


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
        
    def get_cover_url(self, obj: Book) -> str:
        cover_url = obj.get_original_cover_url()
        request = self.context.get("request")

        if not cover_url or not request:
            return cover_url

        if cover_url.startswith(("http://", "https://", "//")):
            return cover_url

        return request.build_absolute_uri(cover_url)

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
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            validated_data.setdefault("owner", user)
            if not getattr(user, "is_staff", False):
                validated_data.setdefault("visibility", Book.Visibility.PRIVATE)

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


class ReadingClubCreateSerializer(serializers.ModelSerializer):
    book = serializers.PrimaryKeyRelatedField(
        queryset=Book.objects.public().filter(is_hidden_by_admin=False)
    )

    class Meta:
        model = ReadingClub
        fields = [
            "title",
            "book",
            "description",
            "start_date",
            "end_date",
            "join_policy",
        ]

    def validate(self, attrs):
        start_date = attrs.get("start_date")
        end_date = attrs.get("end_date")

        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError(
                {"end_date": "Дата окончания не может быть раньше даты начала."}
            )

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if not getattr(user, "is_authenticated", False):
            raise serializers.ValidationError("Для создания совместного чтения нужно войти в аккаунт.")

        return ReadingClub.objects.create(creator=user, **validated_data)


class CommunityUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    name = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()

    def get_name(self, obj):
        full_name = obj.get_full_name()
        return full_name or obj.username

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username

    def get_avatar_url(self, obj):
        try:
            profile = obj.profile
        except Exception:
            profile = None
        avatar = getattr(profile, "avatar", None)
        if not avatar:
            return None

        try:
            url = avatar.url
        except ValueError:
            return None

        request = self.context.get("request")
        if request and url and not url.startswith(("http://", "https://", "//")):
            return request.build_absolute_uri(url)
        return url


class ReadingClubTopicSerializer(serializers.ModelSerializer):
    is_open = serializers.SerializerMethodField()
    post_count = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = ReadingNorm
        fields = [
            "id",
            "title",
            "description",
            "order",
            "discussion_opens_at",
            "is_open",
            "post_count",
            "unread_count",
        ]

    def get_is_open(self, obj: ReadingNorm) -> bool:
        return obj.is_open()

    def get_post_count(self, obj: ReadingNorm) -> int:
        annotated_value = getattr(obj, "post_count", None)
        if annotated_value is not None:
            return annotated_value
        return obj.posts.count()

    def get_unread_count(self, obj: ReadingNorm) -> int:
        return int(getattr(obj, "unread_count", 0) or 0)


class ReadingClubTopicCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReadingNorm
        fields = [
            "title",
            "description",
            "order",
            "discussion_opens_at",
        ]

    def validate_order(self, value):
        if value < 1:
            raise serializers.ValidationError("Порядок должен быть положительным числом.")
        return value


class DiscussionPostSerializer(serializers.ModelSerializer):
    author = CommunityUserSerializer(read_only=True)
    parent = serializers.SerializerMethodField()
    is_unread = serializers.SerializerMethodField()
    is_own = serializers.SerializerMethodField()
    is_reported_by_me = serializers.SerializerMethodField()

    class Meta:
        model = DiscussionPost
        fields = [
            "id",
            "content",
            "created_at",
            "updated_at",
            "author",
            "parent",
            "is_unread",
            "is_own",
            "is_reported_by_me",
        ]

    def get_parent(self, obj: DiscussionPost):
        parent = obj.parent
        if not parent:
            return None

        author = parent.author
        author_name = author.get_full_name() or author.username
        return {
            "id": parent.id,
            "content": parent.content,
            "author_name": author_name,
        }

    def get_is_unread(self, obj: DiscussionPost) -> bool:
        return bool(getattr(obj, "is_unread", False))

    def get_is_own(self, obj: DiscussionPost) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return bool(getattr(user, "is_authenticated", False) and obj.author_id == user.id)

    def get_is_reported_by_me(self, obj: DiscussionPost) -> bool:
        annotated_value = getattr(obj, "is_reported_by_me", None)
        if annotated_value is not None:
            return bool(annotated_value)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            return False
        return obj.reports.filter(reporter=user).exists()


class DiscussionPostReportCreateSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=DiscussionPostReport.Reason.choices)
    details = serializers.CharField(required=False, allow_blank=True, max_length=1000, trim_whitespace=True)


class ReadingClubTopicDetailSerializer(ReadingClubTopicSerializer):
    reading = serializers.SerializerMethodField()
    posts = DiscussionPostSerializer(many=True, read_only=True)
    is_participant = serializers.SerializerMethodField()
    can_post = serializers.SerializerMethodField()
    first_unread_post_id = serializers.SerializerMethodField()

    class Meta(ReadingClubTopicSerializer.Meta):
        fields = ReadingClubTopicSerializer.Meta.fields + [
            "reading",
            "posts",
            "is_participant",
            "can_post",
            "first_unread_post_id",
        ]

    def get_reading(self, obj: ReadingNorm):
        return ReadingClubSerializer(obj.reading, context=self.context).data

    def get_is_participant(self, obj: ReadingNorm) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            return False

        return obj.reading.participants.filter(
            user=user,
            status=ReadingParticipant.Status.APPROVED,
        ).exists()

    def get_can_post(self, obj: ReadingNorm) -> bool:
        return obj.is_open() and self.get_is_participant(obj)

    def get_first_unread_post_id(self, obj: ReadingNorm):
        return getattr(obj, "first_unread_post_id", None)


class ReadingClubParticipantSerializer(serializers.ModelSerializer):
    user = CommunityUserSerializer(read_only=True)
    reading_progress_percent = serializers.SerializerMethodField()
    reading_progress_current_page = serializers.SerializerMethodField()
    reading_progress_updated_at = serializers.SerializerMethodField()

    class Meta:
        model = ReadingParticipant
        fields = [
            "id",
            "status",
            "joined_at",
            "user",
            "reading_progress_percent",
            "reading_progress_current_page",
            "reading_progress_updated_at",
        ]

    def get_reading_progress_percent(self, obj: ReadingParticipant):
        value = getattr(obj, "reading_progress_percent", None)
        if value is None:
            return None
        return value

    def get_reading_progress_current_page(self, obj: ReadingParticipant):
        progress = getattr(obj, "reading_progress", None)
        if not progress:
            return None
        return progress.current_page

    def get_reading_progress_updated_at(self, obj: ReadingParticipant):
        progress = getattr(obj, "reading_progress", None)
        if not progress:
            return None
        return progress.updated_at


class ReadingClubDetailSerializer(ReadingClubSerializer):
    creator = CommunityUserSerializer(read_only=True)
    topics = ReadingClubTopicSerializer(many=True, read_only=True)
    approved_participants = serializers.SerializerMethodField()
    pending_participants = serializers.SerializerMethodField()
    current_participant = serializers.SerializerMethodField()
    is_participant = serializers.SerializerMethodField()
    can_join = serializers.SerializerMethodField()
    can_manage_topics = serializers.SerializerMethodField()

    class Meta(ReadingClubSerializer.Meta):
        fields = ReadingClubSerializer.Meta.fields + [
            "creator",
            "topics",
            "approved_participants",
            "pending_participants",
            "current_participant",
            "is_participant",
            "can_join",
            "can_manage_topics",
        ]

    def _participants_by_status(self, obj: ReadingClub, status_value: str):
        participants = getattr(obj, "prefetched_participants", None)
        if participants is None:
            participants = list(obj.participants.select_related("user", "user__profile"))
        return [
            participant
            for participant in participants
            if participant.status == status_value
        ]

    def get_approved_participants(self, obj: ReadingClub):
        participants = self._participants_by_status(
            obj,
            ReadingParticipant.Status.APPROVED,
        )
        return ReadingClubParticipantSerializer(
            participants,
            many=True,
            context=self.context,
        ).data

    def get_pending_participants(self, obj: ReadingClub):
        participants = self._participants_by_status(
            obj,
            ReadingParticipant.Status.PENDING,
        )
        return ReadingClubParticipantSerializer(
            participants,
            many=True,
            context=self.context,
        ).data

    def _get_current_participant(self, obj: ReadingClub):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            return None

        participants = getattr(obj, "prefetched_participants", None)
        if participants is not None:
            return next((participant for participant in participants if participant.user_id == user.id), None)

        return (
            obj.participants.select_related("user", "user__profile")
            .filter(user=user)
            .first()
        )

    def get_current_participant(self, obj: ReadingClub):
        participant = self._get_current_participant(obj)
        if participant is None:
            return None

        return ReadingClubParticipantSerializer(participant, context=self.context).data

    def get_is_participant(self, obj: ReadingClub) -> bool:
        participant = self._get_current_participant(obj)
        return bool(participant and participant.status == ReadingParticipant.Status.APPROVED)

    def get_can_join(self, obj: ReadingClub) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return bool(getattr(user, "is_authenticated", False) and self._get_current_participant(obj) is None)

    def get_can_manage_topics(self, obj: ReadingClub) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return bool(getattr(user, "is_authenticated", False) and obj.creator_id == user.id)


class ReadingMarathonSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    participant_count = serializers.SerializerMethodField()
    theme_count = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    cover = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ReadingMarathon
        fields = [
            "id",
            "title",
            "description",
            "cover",
            "cover_url",
            "image_url",
            "start_date",
            "end_date",
            "join_policy",
            "book_submission_policy",
            "completion_policy",
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

    def get_cover_url(self, obj: ReadingMarathon):
        if not obj.cover:
            return None

        try:
            url = obj.cover.url
        except ValueError:
            return None

        request = self.context.get("request")
        if request and url and not url.startswith(("http://", "https://", "//")):
            return request.build_absolute_uri(url)
        return url

    def get_cover(self, obj: ReadingMarathon):
        return self.get_cover_url(obj)

    def get_image_url(self, obj: ReadingMarathon):
        return self.get_cover_url(obj)


class ReadingMarathonCreateSerializer(serializers.ModelSerializer):
    topic_titles = serializers.ListField(
        child=serializers.CharField(max_length=255, allow_blank=False, trim_whitespace=True),
        min_length=1,
        max_length=30,
        write_only=True,
    )

    class Meta:
        model = ReadingMarathon
        fields = [
            "title",
            "description",
            "start_date",
            "end_date",
            "join_policy",
            "book_submission_policy",
            "completion_policy",
            "topic_titles",
        ]

    def validate(self, attrs):
        start_date = attrs.get("start_date")
        end_date = attrs.get("end_date")

        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError(
                {"end_date": "Дата окончания не может быть раньше даты начала."}
            )

        topic_titles = [
            title.strip()
            for title in attrs.get("topic_titles", [])
            if str(title).strip()
        ]
        if not topic_titles:
            raise serializers.ValidationError({"topic_titles": "Добавьте хотя бы одно задание марафона."})

        attrs["topic_titles"] = topic_titles
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if not getattr(user, "is_authenticated", False):
            raise serializers.ValidationError("Для создания марафона нужно войти в аккаунт.")

        topic_titles = validated_data.pop("topic_titles", [])
        marathon = ReadingMarathon.objects.create(creator=user, **validated_data)

        MarathonTheme.objects.bulk_create(
            [
                MarathonTheme(marathon=marathon, title=title, order=order)
                for order, title in enumerate(topic_titles, start=1)
            ]
        )

        return marathon


class MarathonThemeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarathonTheme
        fields = [
            "id",
            "title",
            "description",
            "order",
        ]


class MarathonParticipantSerializer(serializers.ModelSerializer):
    user = CommunityUserSerializer(read_only=True)

    class Meta:
        model = MarathonParticipant
        fields = [
            "id",
            "status",
            "joined_at",
            "user",
        ]


class MarathonEntrySerializer(serializers.ModelSerializer):
    participant = MarathonParticipantSerializer(read_only=True)
    theme = MarathonThemeSerializer(read_only=True)
    book = BookListSerializer(read_only=True)

    class Meta:
        model = MarathonEntry
        fields = [
            "id",
            "participant",
            "theme",
            "book",
            "status",
            "progress",
            "book_approved",
            "completion_status",
            "notes",
            "created_at",
            "updated_at",
        ]


class MarathonEntryCreateSerializer(serializers.Serializer):
    theme = serializers.PrimaryKeyRelatedField(queryset=MarathonTheme.objects.none())
    book = serializers.PrimaryKeyRelatedField(
        queryset=Book.objects.public().select_related("primary_isbn").prefetch_related("authors", "genres", "isbn")
    )
    status = serializers.ChoiceField(choices=MarathonEntry.Status.choices, default=MarathonEntry.Status.PLANNED)
    progress = serializers.IntegerField(min_value=0, max_value=100, default=0)
    notes = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        marathon = self.context.get("marathon")
        if marathon is not None:
            self.fields["theme"].queryset = marathon.themes.all()
        self.fields["book"].queryset = (
            Book.objects.public()
            .select_related("primary_isbn")
            .prefetch_related("authors", "genres", "isbn")
        )

    def validate(self, attrs):
        participant = self.context.get("participant")
        if participant is None:
            raise serializers.ValidationError("Участник марафона не найден.")

        if MarathonEntry.objects.filter(
            participant=participant,
            theme=attrs["theme"],
        ).exists():
            raise serializers.ValidationError("В это задание уже добавлена книга.")

        return attrs

    def create(self, validated_data):
        marathon = self.context["marathon"]
        participant = self.context["participant"]
        book_approved = marathon.book_submission_policy != ReadingMarathon.BookSubmissionPolicy.APPROVAL

        return MarathonEntry.objects.create(
            participant=participant,
            theme=validated_data["theme"],
            book=validated_data["book"],
            status=validated_data.get("status", MarathonEntry.Status.PLANNED),
            progress=validated_data.get("progress", 0),
            notes=validated_data.get("notes", ""),
            book_approved=book_approved,
        )


class MarathonEntryUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarathonEntry
        fields = ["status", "progress", "notes"]

    def validate_progress(self, value):
        if not 0 <= value <= 100:
            raise serializers.ValidationError("Прогресс должен быть в пределах от 0 до 100.")
        return value


class ReadingMarathonDetailSerializer(ReadingMarathonSerializer):
    creator = CommunityUserSerializer(read_only=True)
    themes = MarathonThemeSerializer(many=True, read_only=True)
    participants = serializers.SerializerMethodField()
    entries = serializers.SerializerMethodField()
    marathon_books = serializers.SerializerMethodField()
    current_participant = serializers.SerializerMethodField()
    is_participant = serializers.SerializerMethodField()
    can_join = serializers.SerializerMethodField()
    can_add_entries = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()

    class Meta(ReadingMarathonSerializer.Meta):
        fields = ReadingMarathonSerializer.Meta.fields + [
            "creator",
            "themes",
            "participants",
            "entries",
            "marathon_books",
            "current_participant",
            "is_participant",
            "can_join",
            "can_add_entries",
            "can_manage",
        ]

    def _get_participants(self, obj: ReadingMarathon):
        participants = getattr(obj, "prefetched_participants", None)
        if participants is not None:
            return participants
        return list(obj.participants.select_related("user", "user__profile").order_by("joined_at", "id"))

    def _get_entries(self, obj: ReadingMarathon):
        entries = getattr(obj, "prefetched_entries", None)
        if entries is not None:
            return entries
        return list(
            MarathonEntry.objects.filter(participant__marathon=obj)
            .select_related(
                "participant",
                "participant__user",
                "participant__user__profile",
                "theme",
                "book",
                "book__primary_isbn",
            )
            .prefetch_related("book__authors", "book__genres", "book__isbn")
            .order_by("participant__user__username", "theme__order", "created_at")
        )

    def get_participants(self, obj: ReadingMarathon):
        return MarathonParticipantSerializer(
            self._get_participants(obj),
            many=True,
            context=self.context,
        ).data

    def get_entries(self, obj: ReadingMarathon):
        return MarathonEntrySerializer(
            self._get_entries(obj),
            many=True,
            context=self.context,
        ).data

    def get_marathon_books(self, obj: ReadingMarathon):
        unique_books = []
        seen_book_ids = set()

        for entry in self._get_entries(obj):
            book = entry.book
            if not book or book.pk in seen_book_ids:
                continue
            seen_book_ids.add(book.pk)
            unique_books.append(book)

        return BookListSerializer(unique_books, many=True, context=self.context).data

    def get_current_participant(self, obj: ReadingMarathon):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            return None

        participant = next(
            (item for item in self._get_participants(obj) if item.user_id == user.id),
            None,
        )
        if participant is None:
            return None
        return MarathonParticipantSerializer(participant, context=self.context).data

    def get_is_participant(self, obj: ReadingMarathon) -> bool:
        return self.get_current_participant(obj) is not None

    def get_can_join(self, obj: ReadingMarathon) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return bool(getattr(user, "is_authenticated", False) and self.get_current_participant(obj) is None)

    def get_can_add_entries(self, obj: ReadingMarathon) -> bool:
        current_participant = self.get_current_participant(obj)
        return bool(
            current_participant
            and current_participant.get("status") == MarathonParticipant.Status.APPROVED
        )

    def get_can_manage(self, obj: ReadingMarathon) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return bool(getattr(user, "is_authenticated", False) and obj.creator_id == user.id)



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
    progress_id = serializers.IntegerField(allow_null=True)
    tracker_url = serializers.CharField(allow_null=True)

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
            "progress_id",
            "tracker_url",
        ]


class ReadingUpdateSerializer(serializers.ModelSerializer):
    book_id = serializers.IntegerField(source="progress.book_id", read_only=True)
    user_id = serializers.IntegerField(source="progress.user_id", read_only=True)
    user_username = serializers.CharField(source="progress.user.username", read_only=True)
    user_name = serializers.CharField(source="progress.user.username", read_only=True)
    user_avatar = serializers.SerializerMethodField()
    book_title = serializers.CharField(source="progress.book.title", read_only=True)
    cover_url = serializers.SerializerMethodField()
    pages_read = serializers.SerializerMethodField()
    current_page = serializers.IntegerField(source="progress.current_page", read_only=True)
    progress_percent = serializers.FloatField(source="progress.percent", read_only=True)
    total_pages = serializers.SerializerMethodField()
    progress_id = serializers.IntegerField(source="progress.id", read_only=True)
    tracker_url = serializers.SerializerMethodField()

    class Meta:
        model = ReadingLog
        fields = [
            "id",
            "log_date",
            "book_id",
            "user_id",
            "user_username",
            "user_name",
            "user_avatar",
            "book_title",
            "cover_url",
            "pages_read",
            "current_page",
            "progress_percent",
            "total_pages",
            "progress_id",
            "tracker_url",
        ]

    def _build_absolute_url(self, url: str | None) -> str:
        if not url:
            return ""

        request = self.context.get("request")
        if not request or url.startswith(("http://", "https://", "//")):
            return url

        return request.build_absolute_uri(url)

    def get_user_avatar(self, obj: ReadingLog) -> str:
        avatar = getattr(getattr(obj.progress.user, "profile", None), "avatar", None)
        if not avatar:
            return ""
        return self._build_absolute_url(avatar.url)

    def get_cover_url(self, obj: ReadingLog) -> str:
        return self._build_absolute_url(obj.progress.book.get_cover_url())

    def get_pages_read(self, obj: ReadingLog) -> int:
        return int(float(obj.pages_equivalent or 0))

    def get_total_pages(self, obj: ReadingLog):
        return obj.progress.get_effective_total_pages()

    def get_tracker_url(self, obj: ReadingLog) -> str:
        return f"/tracker/{obj.progress_id}/"
