from datetime import datetime, timedelta, time
from decimal import Decimal, ROUND_HALF_UP
from math import ceil

from django.db.models import Sum, F, Count
from django.core.validators import MinValueValidator
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.timezone import localdate
from books.models import Book, Genre

class Shelf(models.Model):
    """Полка пользователя"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="shelves")
    name = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)
    is_public  = models.BooleanField(default=True)

    class Meta:
        unique_together = ("user", "name")
        ordering = ["-is_default", "name"]

    def __str__(self):
        return f"{self.user.username} – {self.name}"

class ShelfItem(models.Model):
    """Книга в полке"""
    shelf = models.ForeignKey(Shelf, on_delete=models.CASCADE, related_name="items")
    book  = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="shelf_items")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("shelf", "book")
        ordering = ["-added_at"]

    def __str__(self):
        return f"{self.book.title} в {self.shelf.name}"


class Event(models.Model):
    KIND_CHOICES = [
        ("readathon", "Марафон"),
        ("challenge", "Челлендж"),
        ("game", "Игра"),
    ]
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name="created_events")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default="readathon")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField(null=True, blank=True)
    is_public = models.BooleanField(default=True)

    # опционально: список книг события через полку
    shelf = models.ForeignKey(Shelf, on_delete=models.SET_NULL, null=True, blank=True, related_name="events")

    class Meta:
        ordering = ["-start_at"]

    def __str__(self):
        return self.title

    @property
    def is_active(self):
        now = timezone.now()
        return self.start_at <= now and (self.end_at is None or now <= self.end_at)

class EventParticipant(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="participants")
    user  = models.ForeignKey(User, on_delete=models.CASCADE, related_name="event_participations")
    joined_at = models.DateTimeField(auto_now_add=True)
    is_moderator = models.BooleanField(default=False)

    class Meta:
        unique_together = ("event", "user")

# shelves/models.py
class BookProgress(models.Model):
    FORMAT_PAPER = "paper"
    FORMAT_EBOOK = "ebook"
    FORMAT_AUDIO = "audiobook"
    FORMAT_CHOICES = [
        (FORMAT_PAPER, "Бумажная книга"),
        (FORMAT_EBOOK, "Электронная книга"),
        (FORMAT_AUDIO, "Аудиокнига"),
    ]

    event  = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="book_progress",
                               null=True, blank=True)
    user   = models.ForeignKey(User, on_delete=models.CASCADE)
    book   = models.ForeignKey(Book, on_delete=models.CASCADE)
    percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    current_page = models.PositiveIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    reading_notes = models.TextField(blank=True, default="")
    format = models.CharField(
        max_length=20,
        choices=FORMAT_CHOICES,
        default=FORMAT_PAPER,
        help_text="Формат, в котором пользователь читает книгу",
    )
    custom_total_pages = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Количество страниц, указанное пользователем, если нет данных об издании",
    )
    audio_length = models.DurationField(
        null=True,
        blank=True,
        help_text="Полная длительность аудиокниги",
    )
    audio_playback_speed = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Скорость прослушивания аудиокниги",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['event', 'user', 'book'], name='uniq_progress_per_event'),
            models.UniqueConstraint(fields=['user', 'book'],
                                    condition=models.Q(event__isnull=True),
                                    name='uniq_progress_no_event'),
        ]

    def get_effective_total_pages(self):
        """Количество страниц для расчёта прогресса с учётом пользовательских данных."""
        if self.format == self.FORMAT_AUDIO:
            return None
        if self.custom_total_pages:
            return self.custom_total_pages
        return self.book.get_total_pages()

    def recalc_percent(self):
        total = self.get_effective_total_pages()
        if total and self.current_page is not None:
            total_decimal = Decimal(total)
            current_decimal = Decimal(self.current_page)
            percent = current_decimal / (total_decimal / Decimal(100))
            percent = percent.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            self.percent = min(Decimal("100"), percent)
        else:
            self.percent = Decimal("0")
        self.save(update_fields=["percent", "updated_at"])

    @property
    def pages_left(self):
        total = self.get_effective_total_pages()
        if not total or self.current_page is None:
            return None
        return max(0, total - self.current_page)

    @property
    def avg_sec_per_page(self):
        qs = self.sessions.filter(
            end_page__isnull=False,
            start_page__isnull=False,
            duration_seconds__gt=0,
        )
        agg = qs.aggregate(
            total_secs=Sum("duration_seconds"),
            total_pages=Sum(F("end_page") - F("start_page")),
        )
        if not agg["total_secs"] or not agg["total_pages"]:
            return None
        return agg["total_secs"] / max(1, agg["total_pages"])

    @property
    def is_audiobook(self):
        return self.format == self.FORMAT_AUDIO

    def get_audio_adjusted_length(self):
        if not self.audio_length:
            return None
        speed = self.audio_playback_speed or Decimal("1.0")
        if speed <= 0:
            return self.audio_length
        total_seconds = Decimal(self.audio_length.total_seconds())
        adjusted_seconds = total_seconds / speed
        return timedelta(seconds=float(adjusted_seconds))
    
    @property
    def eta_seconds(self):
        if self.pages_left is None:
            return None
        spp = self.avg_sec_per_page
        if spp is None:
            return None
        return int(self.pages_left * spp)

    def record_pages(self, pages_read, log_date=None):
        """Зафиксировать количество прочитанных страниц за конкретный день."""
        if self.is_audiobook:
            return
        if not pages_read or pages_read <= 0:
            return
        log_date = log_date or localdate()
        log, created = self.logs.get_or_create(
            log_date=log_date,
            defaults={"pages_read": pages_read},
        )
        if not created:
            log.pages_read += pages_read
            log.save(update_fields=["pages_read"])
        if pages_read > 0:
            from games.services.read_before_buy import ReadBeforeBuyGame

            occurred_at = datetime.combine(log_date, time.max)
            if timezone.is_naive(occurred_at):
                occurred_at = timezone.make_aware(occurred_at)
            ReadBeforeBuyGame.award_pages(
                self.user,
                self.book,
                pages_read,
                occurred_at=occurred_at,
            )
    @property
    def average_pages_per_day(self):
        stats = self.logs.filter(pages_read__gt=0).aggregate(
            total_pages=Sum("pages_read"),
            days=Count("id"),
        )
        if not stats["total_pages"] or not stats["days"]:
            return None
        avg = Decimal(stats["total_pages"]) / Decimal(stats["days"])
        return avg.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def estimated_days_remaining(self):
        pages_left = self.pages_left
        avg = self.average_pages_per_day
        if pages_left is None or avg is None or avg <= 0:
            return None
        return max(1, ceil(Decimal(pages_left) / avg))


class ReadingLog(models.Model):
    progress = models.ForeignKey(
        BookProgress,
        on_delete=models.CASCADE,
        related_name="logs",
    )
    log_date = models.DateField(default=localdate)
    pages_read = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("progress", "log_date")
        ordering = ["-log_date"]

    def __str__(self):
        return f"{self.log_date}: {self.pages_read} стр."
   

class CharacterNote(models.Model):
    progress = models.ForeignKey(
        BookProgress,
        on_delete=models.CASCADE,
        related_name="character_entries",
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.name} — {self.progress.book.title}"


class HomeLibraryEntry(models.Model):
    """Дополнительные сведения о книге на полке «Моя домашняя библиотека».

    Пользователь может фиксировать информацию о конкретном экземпляре книги.
    """

    class Format(models.TextChoices):
        PAPER = "paper", "Бумажная"
        EBOOK = "ebook", "Электронная"
        AUDIO = "audio", "Аудио"
        OTHER = "other", "Другое"

    shelf_item = models.OneToOneField(
        ShelfItem,
        on_delete=models.CASCADE,
        related_name="home_entry",
    )
    edition = models.CharField(
        max_length=200,
        blank=True,
        help_text="Издание, тираж или дополнительная информация",
    )
    language = models.CharField(
        max_length=50,
        blank=True,
        help_text="Язык конкретного экземпляра",
    )
    format = models.CharField(
        max_length=20,
        choices=Format.choices,
        default=Format.PAPER,
    )
    status = models.CharField(
        max_length=100,
        blank=True,
        help_text="Например: в коллекции, отдана другу, зарезервирована",
    )
    location = models.CharField(
        max_length=100,
        blank=True,
        help_text="Где хранится книга: комната, шкаф, полка",
    )
    shelf_section = models.CharField(
        max_length=100,
        blank=True,
        help_text="Дополнительная пометка: ряд, коробка, секция",
    )
    acquired_at = models.DateField(
        null=True,
        blank=True,
        help_text="Дата покупки или получения",
    )
    condition = models.CharField(
        max_length=100,
        blank=True,
        help_text="Состояние экземпляра, например «как новая»",
    )
    is_classic = models.BooleanField(
        default=False,
        help_text="Отметьте, если книга относится к классике",
    )
    series_name = models.CharField(
        max_length=150,
        blank=True,
        help_text="Серия, к которой относится экземпляр",
    )
    custom_genres = models.ManyToManyField(
        Genre,
        blank=True,
        related_name="home_library_entries",
        help_text="Жанры именно этого экземпляра",
    )
    is_disposed = models.BooleanField(
        default=False,
        help_text="Пометка, что книга продана или отдана",
    )
    disposition_note = models.TextField(
        blank=True,
        help_text="Комментарий, почему книга выбыла",
    )
    notes = models.TextField(
        blank=True,
        help_text="Особые пометки: автограф, кому дать почитать и т.д.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-shelf_item__added_at", "shelf_item__id"]

    def __str__(self):
        return f"Домашняя библиотека: {self.shelf_item.book.title}"

    @property
    def book(self):
        return self.shelf_item.book