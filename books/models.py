from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.db.models import Sum, F, Avg, Count


class Author(models.Model):
    name = models.CharField(max_length=255)
    bio = models.TextField(max_length=1000, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name


class Publisher(models.Model):
    name = models.CharField(max_length=255, unique=True)
    address = models.CharField(max_length=250, blank=True, null=True)

    def __str__(self):
        return self.name


class Genre(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class ISBNModel(models.Model):
    isbn = models.CharField(max_length=13, unique=True)
    isbn13 = models.CharField(max_length=13, unique=True, blank=True, null=True)
    title = models.CharField(max_length=255, blank=True, null=True)
    authors = models.ManyToManyField(Author, blank=True, related_name='isbn_authors')
    publisher = models.CharField(max_length=255, blank=True, null=True)
    publish_date = models.CharField(max_length=50, blank=True, null=True)
    total_pages = models.PositiveIntegerField(null=True, blank=True)
    binding = models.CharField(max_length=50, blank=True, null=True)
    synopsis = models.TextField(blank=True, null=True)
    language = models.CharField(max_length=10, blank=True, null=True)
    subjects = models.TextField(blank=True, null=True)
    image = models.URLField(blank=True, null=True)

    def __str__(self):
        return f"{self.title} ({self.isbn})"


class AudioBook(models.Model):
    title = models.CharField(max_length=250)
    length = models.DurationField()
    narrator = models.CharField(max_length=100)  # исправил dictor → narrator
    publisher = models.ForeignKey(Publisher, on_delete=models.SET_NULL, null=True, blank=True)
    genre = models.ManyToManyField(Genre, blank=True, related_name='audiobooks')

    def __str__(self):
        return self.title


class Book(models.Model):
    title = models.CharField(max_length=255)
    authors = models.ManyToManyField("Author", related_name="books_author")
    genres = models.ManyToManyField("Genre", related_name="books")
    publisher = models.ManyToManyField("Publisher", related_name="books_publisher")
    synopsis = models.TextField(blank=True, null=True)
    series = models.CharField(max_length=255, blank=True, null=True)
    series_order = models.PositiveIntegerField(blank=True, null=True)
    age_rating = models.CharField(max_length=10, blank=True, null=True)
    language = models.CharField(max_length=50, blank=True, null=True)
    isbn = models.ManyToManyField(ISBNModel, related_name='books', blank=True)
    audio = models.ForeignKey(AudioBook, on_delete=models.CASCADE, blank=True, null=True)
    primary_isbn = models.ForeignKey(
        ISBNModel,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="primary_for_books"
    )


    # новое поле для обложки
    cover = models.ImageField(upload_to="book_covers/", blank=True, null=True)

    def get_total_pages(self):
        """
        Источник приоритетов:
        1. primary_isbn.total_pages, если заполнено.
        2. Первая привязанная запись ISBN с указанием total_pages.
        """
        if self.primary_isbn and self.primary_isbn.total_pages:
            return self.primary_isbn.total_pages
        
        fallback_isbn = (
            self.isbn.filter(total_pages__isnull=False)
            .exclude(total_pages=0)
            .order_by("pk")
            .first()
        )
        if fallback_isbn:
            return fallback_isbn.total_pages
        return None

    def get_rating_summary(self):
        """Средние оценки по каждой категории и общее количество голосов."""

        aggregates = self.ratings.aggregate(
            **{
                f"{field}_avg": Avg(field)
                for field, _ in Rating.get_score_fields()
            },
            **{
                f"{field}_count": Count(field)
                for field, _ in Rating.get_score_fields()
            },
        )

        summary = {}
        for field, label in Rating.get_score_fields():
            summary[field] = {
                "label": label,
                "average": _round_rating(aggregates.get(f"{field}_avg")),
                "count": aggregates.get(f"{field}_count", 0),
            }
        return summary

    def get_average_rating(self):
        """Короткое значение средней оценки для списков и админки."""

        summary = self.get_rating_summary()
        overall = summary.get("score", {})
        return overall.get("average")

    def __str__(self):
        return self.title
    
class ReadingSession(models.Model):
    """Одна сессия чтения книги в рамках события/прогресса"""
    progress = models.ForeignKey(
        "shelves.BookProgress",
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    started_at = models.DateTimeField(default=timezone.now)
    ended_at   = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)  # итоговая длительность
    start_page = models.PositiveIntegerField(null=True, blank=True)
    end_page   = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def pages_read(self):
        if self.start_page is not None and self.end_page is not None:
            return max(0, self.end_page - self.start_page)
        return 0
    

# class BookProgress(models.Model):
#     # event, user, book, percent, current_page, updated_at ...

#     def recalc_percent(self):
#         total = self.book.get_total_pages()
#         if total and self.current_page is not None:
#             self.percent = min(100, round(self.current_page / total * 100, 2))
#         else:
#             self.percent = 0
#         self.save(update_fields=["percent", "updated_at"])

#     @property
#     def pages_left(self):
#         total = self.book.get_total_pages()
#         if not total or self.current_page is None:
#             return None
#         return max(0, total - self.current_page)
    
    
#     @property
#     def avg_sec_per_page(self):
#         qs = self.sessions.exclude(end_page__isnull=True, start_page__isnull=True, duration_seconds=0)
#         agg = qs.aggregate(
#             total_secs=Sum("duration_seconds"),
#             total_pages=Sum(F("end_page") - F("start_page"))
#         )
#         if not agg["total_secs"] or not agg["total_pages"]:
#             return None
#         return agg["total_secs"] / max(1, agg["total_pages"])

#     @property
#     def eta_seconds(self):
#         """оценка оставшегося времени"""
#         if self.pages_left is None:
#             return None
#         spp = self.avg_sec_per_page
#         if spp is None:
#             return None
#         return int(self.pages_left * spp)

def _round_rating(value):
    if value is None:
        return None
    return round(float(value), 1)


class Rating(models.Model):
    """Пользовательский отзыв об основной книге."""

    SCORE_FIELD = ("score", "Общая оценка")
    CATEGORY_FIELDS = [
        ("plot_score", "Сюжет"),
        ("characters_score", "Персонажи"),
        ("atmosphere_score", "Атмосфера"),
        ("art_score", "Художественная ценность"),
    ]
    SCORE_FIELDS = [SCORE_FIELD, *CATEGORY_FIELDS]

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="ratings")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        null=True,
        blank=True,
        help_text="Общая оценка книги от 1 до 10",
    )
    plot_score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        null=True,
        blank=True,
    )
    characters_score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        null=True,
        blank=True,
    )
    atmosphere_score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        null=True,
        blank=True,
    )
    art_score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        null=True,
        blank=True,
    )
    review = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("book", "user")

    @classmethod
    def get_score_fields(cls):
        return cls.SCORE_FIELDS

    @classmethod
    def get_category_fields(cls):
        return cls.CATEGORY_FIELDS

    def iter_category_scores(self):
        for field_name, label in self.CATEGORY_FIELDS:
            value = getattr(self, field_name)
            if value is not None:
                yield label, value

    def has_any_scores(self):
        return any(getattr(self, field, None) is not None for field, _ in self.SCORE_FIELDS)

    def get_category_scores(self):
        return [
            (label, getattr(self, field_name))
            for field_name, label in self.CATEGORY_FIELDS
            if getattr(self, field_name) is not None
        ]
