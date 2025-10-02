from urllib.parse import urljoin

from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.utils.text import slugify
from django.urls import reverse
from django.db.models import Sum, F, Avg, Count
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from .utils import build_edition_group_key


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
    slug = models.SlugField(
        max_length=150,
        unique=True,
        blank=True,
        allow_unicode=True,
    )

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug and self.name:
            base_slug = slugify(self.name, allow_unicode=True) or "genre"
            slug_candidate = base_slug
            counter = 2
            while (
                Genre.objects.filter(slug=slug_candidate)
                .exclude(pk=self.pk)
                .exists()
            ):
                slug_candidate = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug_candidate
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("genre_detail", args=[self.slug])
    

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

    def get_image_url(self) -> str:
        """Вернуть пригодный для использования URL обложки издания."""

        image_value = self.image
        if not image_value:
            return ""

        # File/ImageField instances expose ``url`` — попробуем использовать его
        try:
            file_url = image_value.url  # type: ignore[attr-defined]
        except (ValueError, AttributeError):
            file_url = None
        else:
            if file_url:
                return file_url

        image_str = str(image_value).strip()
        if not image_str:
            return ""

        if image_str.startswith(("http://", "https://", "//")):
            return image_str

        if image_str.startswith("/"):
            return image_str

        media_url = getattr(settings, "MEDIA_URL", "/media/") or "/media/"
        media_url = str(media_url).strip()
        normalized_path = image_str.lstrip("/")

        if media_url.startswith(("http://", "https://", "//")):
            base = media_url if media_url.endswith("/") else f"{media_url}/"
            return urljoin(base, normalized_path)

        if not media_url:
            media_url = "/media/"
        if not media_url.endswith("/"):
            media_url = f"{media_url}/"
        if not media_url.startswith("/"):
            media_url = f"/{media_url.lstrip('/')}"

        return f"{media_url}{normalized_path}"


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
    edition_group_key = models.CharField(
        max_length=512,
        blank=True,
        default="",
        db_index=True,
        help_text="Служебный ключ для объединения изданий одной книги.",
    )


    # новое поле для обложки
    cover = models.ImageField(upload_to="book_covers/", blank=True, null=True)

    def get_cover_url(self) -> str:
        """Вернуть подходящий URL обложки книги с учётом источника."""

        cover_file = getattr(self, "cover", None)
        if cover_file:
            try:
                url = cover_file.url
            except (ValueError, AttributeError):
                url = ""
            else:
                if url:
                    return url

        primary = getattr(self, "primary_isbn", None)
        if primary:
            cover_url = primary.get_image_url()
            if cover_url:
                return cover_url

        fallback_isbn = (
            self.isbn.exclude(image__isnull=True)
            .exclude(image="")
            .first()
        )
        if fallback_isbn:
            cover_url = fallback_isbn.get_image_url()
            if cover_url:
                return cover_url

        return ""

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
    
    def refresh_edition_group_key(self, save: bool = True) -> str:
        """Recalculate and optionally persist the edition grouping key."""

        author_names = list(
            self.authors.order_by("name").values_list("name", flat=True)
        )
        if author_names:
            new_key = build_edition_group_key(self.title, author_names)
        else:
            new_key = ""
        if self.edition_group_key != new_key:
            self.edition_group_key = new_key
            if save and self.pk:
                type(self).objects.filter(pk=self.pk).update(
                    edition_group_key=new_key
                )
        return new_key

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.pk:
            self.refresh_edition_group_key()
    
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


@receiver(m2m_changed, sender=Book.authors.through)
def _book_authors_changed(sender, instance: Book, action, **kwargs):
    if action in {"post_add", "post_remove", "post_clear"}:
        instance.refresh_edition_group_key()
    

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
