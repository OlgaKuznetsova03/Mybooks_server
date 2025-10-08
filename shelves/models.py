from datetime import datetime, timedelta, time
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
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

    audio_position = models.DurationField(
        null=True,
        blank=True,
        help_text="Текущее время прослушивания аудиокниги",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['event', 'user', 'book'], name='uniq_progress_per_event'),
            models.UniqueConstraint(fields=['user', 'book'],
                                    condition=models.Q(event__isnull=True),
                                    name='uniq_progress_no_event'),
        ]

    def get_effective_total_pages(self):
        """Количество страниц для расчёта прогресса с учётом пользовательских данных.

        Для гибридных прогрессов используем базовое количество страниц,
        указанное пользователем или взятое из книги.
        """
        total = self.custom_total_pages or self.book.get_total_pages()
        if not total or total <= 0:
            return None
        return total

    def _iter_active_media(self):
        media = list(self.media.all())
        if media:
            return media
        # Поддержка старых записей без связанных носителей
        legacy = BookProgressMedium(
            progress=self,
            medium=self.format,
            current_page=self.current_page,
            total_pages_override=self.custom_total_pages if self.format != self.FORMAT_AUDIO else None,
            audio_position=getattr(self, "audio_position", None),
            audio_length=self.audio_length,
            playback_speed=self.audio_playback_speed,
        )
        return [legacy]

    def get_medium(self, medium_code):
        medium = self.media.filter(medium=medium_code).first()
        if medium:
            return medium
        if self.media.exists() or self.format != medium_code:
            return None
        defaults = {}
        if medium_code == self.FORMAT_AUDIO:
            defaults.update(
                {
                    "audio_position": getattr(self, "audio_position", None),
                    "audio_length": self.audio_length,
                    "playback_speed": self.audio_playback_speed,
                }
            )
        else:
            defaults.update(
                {
                    "current_page": self.current_page,
                    "total_pages_override": self.custom_total_pages,
                }
            )
        return self.media.create(medium=medium_code, **defaults)

    def _get_audio_position_seconds(self, medium):
        position = medium.audio_position or getattr(self, "audio_position", None)
        if not position:
            return None
        return Decimal(position.total_seconds())

    def _get_audio_length_seconds(self, medium):
        length = medium.audio_length or self.audio_length
        if not length:
            return None
        return Decimal(length.total_seconds())

    def get_effective_playback_speed(self, medium=None):
        """Возвращает скорость прослушивания для вычислений прогресса."""
        speed = None
        if medium and medium.playback_speed is not None:
            speed = medium.playback_speed
        elif self.audio_playback_speed is not None:
            speed = self.audio_playback_speed
        if not speed or speed <= 0:
            return Decimal("1.0")
        return Decimal(speed)
    
    def _medium_equivalent_pages(self, medium, total_pages):
        if total_pages is None:
            return None
        if medium.medium == self.FORMAT_AUDIO:
            length_seconds = self._get_audio_length_seconds(medium)
            position_seconds = self._get_audio_position_seconds(medium)
            if not length_seconds or length_seconds <= 0 or position_seconds is None:
                return None
            ratio = position_seconds / length_seconds
            if ratio < 0:
                return Decimal("0")
            ratio = min(Decimal("1"), ratio)
            return (Decimal(total_pages) * ratio).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if medium.current_page is None:
            return None
        medium_total = medium.total_pages_override or total_pages
        if not medium_total or medium_total <= 0:
            return Decimal(medium.current_page)
        ratio = Decimal(medium.current_page) / Decimal(medium_total)
        ratio = min(Decimal("1"), max(Decimal("0"), ratio))
        return (Decimal(total_pages) * ratio).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def sync_media_equivalents(self, *, source_medium, percent_complete):
        """Синхронизировать прогресс между активными форматами по проценту."""

        try:
            percent_decimal = Decimal(percent_complete)
        except (InvalidOperation, TypeError):
            return
        percent_decimal = max(Decimal("0"), min(Decimal("100"), percent_decimal))
        ratio = percent_decimal / Decimal("100")
        total = self.get_effective_total_pages()
        equivalent_decimal = None
        if total:
            total_decimal = Decimal(total)
            if total_decimal > 0:
                equivalent_decimal = (
                    total_decimal * ratio
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        updated_audio_positions = []
        for medium in self._iter_active_media():
            if medium.medium == source_medium or medium.pk is None:
                continue
            if medium.medium == self.FORMAT_AUDIO:
                position = self._sync_audio_medium_from_equivalent(
                    medium, ratio
                )
                if position is not None:
                    updated_audio_positions.append(position)
            else:
                desired_override = medium.total_pages_override or self.custom_total_pages
                if not desired_override and not total:
                    continue
                self._sync_text_medium_from_equivalent(
                    medium,
                    total,
                    desired_override,
                    ratio=ratio,
                    equivalent=equivalent_decimal or Decimal("0"),
                )
        if updated_audio_positions:
            max_position = max(
                updated_audio_positions, key=lambda value: value.total_seconds()
            )
            current_seconds = int((self.audio_position or timedelta()).total_seconds())
            max_seconds = int(max_position.total_seconds())
            if max_seconds != current_seconds:
                self.audio_position = timedelta(seconds=max_seconds)
                self.save(update_fields=["audio_position"])

    def _sync_text_medium_from_pages(
        self,
        medium,
        total_pages,
        desired_override,
        *,
        ratio,
        equivalent,
    ):
        medium_total = medium.total_pages_override or desired_override or total_pages
        if medium_total:
            target_decimal = Decimal(medium_total) * ratio
        else:
            target_decimal = equivalent
        target_page = int(
            target_decimal.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        if medium_total:
            medium_total_int = int(medium_total)
            target_page = min(target_page, medium_total_int)
        target_page = max(0, target_page)
        fields = []
        if medium.current_page != target_page:
            medium.current_page = target_page
            fields.append("current_page")
        if medium.total_pages_override != desired_override:
            medium.total_pages_override = desired_override
            fields.append("total_pages_override")
        if fields:
            medium.save(update_fields=fields)

    def _sync_text_medium_from_equivalent(
        self,
        medium,
        total_pages,
        desired_override,
        *,
        ratio,
        equivalent,
    ):
        self._sync_text_medium_from_pages(
            medium,
            total_pages,
            desired_override,
            ratio=ratio,
            equivalent=equivalent,
        )
        if medium.medium != self.FORMAT_AUDIO and medium.medium == self.format:
            fields = []
            if self.current_page != medium.current_page:
                self.current_page = medium.current_page
                fields.append("current_page")
            if desired_override and self.custom_total_pages != desired_override:
                self.custom_total_pages = desired_override
                fields.append("custom_total_pages")
            if fields:
                self.save(update_fields=fields)

    def _sync_audio_medium_from_equivalent(self, medium, ratio):
        audio_length = medium.audio_length or self.audio_length
        if not audio_length:
            return None
        total_seconds = Decimal(str(audio_length.total_seconds()))
        if total_seconds <= 0:
            return None
        ratio = min(Decimal("1"), max(Decimal("0"), ratio))
        target_seconds = int(
            (total_seconds * ratio).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        new_position = timedelta(seconds=target_seconds)
        fields = []
        if medium.audio_position != new_position:
            medium.audio_position = new_position
            fields.append("audio_position")
        if medium.audio_length != audio_length:
            medium.audio_length = audio_length
            fields.append("audio_length")
        if not medium.playback_speed and self.audio_playback_speed:
            medium.playback_speed = self.audio_playback_speed
            fields.append("playback_speed")
        if fields:
            medium.save(update_fields=fields)
        return new_position
    
    def get_combined_current_pages(self):
        total = self.get_effective_total_pages()
        if total is None:
            return None
        equivalents = [
            eq
            for eq in (
                self._medium_equivalent_pages(medium, total)
                for medium in self._iter_active_media()
            )
            if eq is not None
        ]
        if equivalents:
            return max(equivalents)
        if self.current_page is not None:
            return Decimal(self.current_page)
        return None

    def refresh_current_page(self):
        """Пересчитать текущую страницу на основе данных всех активных форматов."""

        combined = self.get_combined_current_pages()
        if combined is None:
            if self.current_page is not None:
                self.current_page = None
                self.save(update_fields=["current_page"])
            return None
        rounded = int(
            combined.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        if self.current_page != rounded:
            self.current_page = rounded
            self.save(update_fields=["current_page"])
        return combined
    
    def recalc_percent(self):
        total = self.get_effective_total_pages()
        current_decimal = self.get_combined_current_pages()
        if total and current_decimal is not None:
            total_decimal = Decimal(total)
            percent = current_decimal / (total_decimal / Decimal(100))
            percent = percent.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            self.percent = min(Decimal("100"), percent)
        else:
            self.percent = Decimal("0")
        self.save(update_fields=["percent", "updated_at"])

    @property
    def pages_left(self):
        total = self.get_effective_total_pages()
        current = self.get_combined_current_pages()
        if not total or current is None:
            return None
        return max(Decimal("0"), Decimal(total) - current)

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
        media = list(self.media.values_list("medium", flat=True))
        if media:
            return set(media) == {self.FORMAT_AUDIO}
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

    def record_pages(self, pages_read, log_date=None, medium=None, audio_seconds=None):
        """Зафиксировать количество прочитанных страниц за конкретный день."""
        if not pages_read or pages_read <= 0:
            return
        log_date = log_date or localdate()
        pages_value = Decimal(pages_read)
        log, created = self.logs.get_or_create(
            log_date=log_date,
            medium=medium or self.format,
            defaults={
                "pages_equivalent": pages_value,
                "audio_seconds": audio_seconds or 0,
            },
        )
        if not created:
            log.pages_equivalent += pages_value
            if audio_seconds:
                log.audio_seconds += int(audio_seconds)
            log.save(update_fields=["pages_equivalent", "audio_seconds"])
        if pages_read > 0:
            from games.services.read_before_buy import ReadBeforeBuyGame

            occurred_at = datetime.combine(log_date, time.max)
            if timezone.is_naive(occurred_at):
                occurred_at = timezone.make_aware(occurred_at)
            award_pages = pages_value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            ReadBeforeBuyGame.award_pages(
                self.user,
                self.book,
                int(award_pages),
                occurred_at=occurred_at,
            )
    @property
    def average_pages_per_day(self):
        stats = self.logs.filter(pages_equivalent__gt=0).aggregate(
            total_pages=Sum("pages_equivalent"),
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


class BookProgressMedium(models.Model):
    progress = models.ForeignKey(
        BookProgress,
        on_delete=models.CASCADE,
        related_name="media",
    )
    medium = models.CharField(
        max_length=20,
        choices=BookProgress.FORMAT_CHOICES,
    )
    current_page = models.PositiveIntegerField(null=True, blank=True)
    total_pages_override = models.PositiveIntegerField(null=True, blank=True)
    audio_position = models.DurationField(null=True, blank=True)
    audio_length = models.DurationField(null=True, blank=True)
    playback_speed = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True,
    )

    class Meta:
        unique_together = ("progress", "medium")

    def __str__(self):
        return f"{self.progress.book.title} – {self.get_medium_display()}"


class ReadingLog(models.Model):
    progress = models.ForeignKey(
        BookProgress,
        on_delete=models.CASCADE,
        related_name="logs",
    )
    log_date = models.DateField(default=localdate)
    medium = models.CharField(
        max_length=20,
        choices=BookProgress.FORMAT_CHOICES,
        default=BookProgress.FORMAT_PAPER,
    )
    pages_equivalent = models.DecimalField(
        max_digits=9,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    audio_seconds = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("progress", "log_date", "medium")
        ordering = ["-log_date"]

    def __str__(self):
        return f"{self.log_date}: {self.pages_equivalent} стр. ({self.get_medium_display()})"
   
    @property
    def audio_duration_display(self):
        if self.medium != BookProgress.FORMAT_AUDIO or not self.audio_seconds:
            return None
        total_seconds = int(self.audio_seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    

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


class ProgressAnnotation(models.Model):
    """Цитаты и краткие заметки, связанные с прогрессом чтения."""

    KIND_QUOTE = "quote"
    KIND_NOTE = "note"
    KIND_CHOICES = [
        (KIND_QUOTE, "Цитата"),
        (KIND_NOTE, "Заметка"),
    ]

    progress = models.ForeignKey(
        BookProgress,
        on_delete=models.CASCADE,
        related_name="annotations",
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    body = models.TextField()
    location = models.CharField(
        max_length=120,
        blank=True,
        help_text="Страница, глава или отметка, где сделана заметка.",
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.progress.book.title}"


class ReadingFeedEntry(models.Model):
    """Публичная запись о прогрессе чтения."""


    progress = models.ForeignKey(
        BookProgress,
        on_delete=models.CASCADE,
        related_name="feed_entries",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="reading_feed_entries",
    )
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name="reading_feed_entries",
    )
    medium = models.CharField(
        max_length=20,
        choices=BookProgress.FORMAT_CHOICES,
    )
    current_page = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Текущая страница или эквивалент страниц в момент обновления.",
    )
    percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    reaction = models.TextField(blank=True)
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username}: {self.book.title} ({self.created_at:%Y-%m-%d %H:%M})"

    @property
    def current_page_display(self):
        if self.current_page is None:
            return None
        if self.current_page == self.current_page.quantize(Decimal("1")):
            return int(self.current_page)
        return self.current_page.normalize()


class ReadingFeedComment(models.Model):
    entry = models.ForeignKey(
        ReadingFeedEntry,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="reading_feed_comments",
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Комментарий {self.user.username} к {self.entry_id}"


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