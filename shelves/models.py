from django.db.models import Sum, F
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
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
            self.percent = min(100, round(self.current_page / total * 100, 2))
        else:
            self.percent = 0
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