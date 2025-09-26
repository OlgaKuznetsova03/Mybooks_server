from decimal import Decimal, ROUND_HALF_UP
from math import ceil

from django.db.models import Sum, F, Count
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.timezone import localdate
from books.models import Book

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
    event  = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="book_progress",
                               null=True, blank=True)
    user   = models.ForeignKey(User, on_delete=models.CASCADE)
    book   = models.ForeignKey(Book, on_delete=models.CASCADE)
    percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    current_page = models.PositiveIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    reading_notes = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['event', 'user', 'book'], name='uniq_progress_per_event'),
            models.UniqueConstraint(fields=['user', 'book'],
                                    condition=models.Q(event__isnull=True),
                                    name='uniq_progress_no_event'),
        ]

    def recalc_percent(self):
        total = self.book.get_total_pages()
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
        total = self.book.get_total_pages()
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
    def eta_seconds(self):
        if self.pages_left is None:
            return None
        spp = self.avg_sec_per_page
        if spp is None:
            return None
        return int(self.pages_left * spp)

    def record_pages(self, pages_read, log_date=None):
        """Зафиксировать количество прочитанных страниц за конкретный день."""
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