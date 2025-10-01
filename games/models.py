from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class Game(models.Model):
    """Описание игровой механики."""

    slug = models.SlugField(max_length=64, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return self.title


class GameShelfState(models.Model):
    """Текущее состояние игры для конкретной полки пользователя."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="shelf_states")
    shelf = models.ForeignKey("shelves.Shelf", on_delete=models.CASCADE, related_name="game_states")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="game_shelf_states",
    )
    points_balance = models.PositiveIntegerField(default=0)
    total_points_earned = models.PositiveIntegerField(default=0)
    books_purchased = models.PositiveIntegerField(default=0)
    books_reviewed = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("game", "shelf")

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return f"{self.game.title} — {self.shelf.name} ({self.user.username})"


class GameShelfBook(models.Model):
    """Статистика конкретной книги в рамках игры."""

    state = models.ForeignKey(
        GameShelfState,
        on_delete=models.CASCADE,
        related_name="books",
    )
    book = models.ForeignKey("books.Book", on_delete=models.CASCADE, related_name="game_entries")
    pages_logged = models.PositiveIntegerField(default=0)
    bonus_awarded = models.BooleanField(default=False)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    purchased_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("state", "book")

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return f"{self.book.title} — {self.state.shelf.name}"


class GameShelfPurchase(models.Model):
    """Факт приобретения новой книги."""

    state = models.ForeignKey(
        GameShelfState,
        on_delete=models.CASCADE,
        related_name="purchases",
    )
    book = models.ForeignKey(
        "books.Book",
        on_delete=models.CASCADE,
        related_name="game_purchases",
        null=True,
        blank=True,
    )
    points_spent = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - simple representation
        title = self.book.title if self.book else "Покупка"
        return f"{title} — {self.points_spent} баллов"


class BookJourneyAssignment(models.Model):
    """Прикрепление книги к этапу карты путешествия."""

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "В процессе"
        COMPLETED = "completed", "Выполнено"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="book_journey_assignments",
    )
    stage_number = models.PositiveSmallIntegerField()
    book = models.ForeignKey(
        "books.Book",
        on_delete=models.CASCADE,
        related_name="book_journey_assignments",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
    )
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "stage_number")
        ordering = ["stage_number"]

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return f"#{self.stage_number} — {self.book.title} ({self.user.username})"

    @property
    def is_completed(self) -> bool:
        return self.status == self.Status.COMPLETED

    def reset_progress(self, *, book) -> None:
        """Перевести запись в состояние "в процессе" и обновить книгу."""

        updates = []
        if self.book_id != book.id:
            self.book = book
            updates.append("book")
        if self.status != self.Status.IN_PROGRESS:
            self.status = self.Status.IN_PROGRESS
            updates.append("status")
        self.started_at = timezone.now()
        self.completed_at = None
        updates.extend(["started_at", "completed_at", "updated_at"])
        updates = list(dict.fromkeys(updates))
        self.save(update_fields=updates)

    def mark_completed(self) -> None:
        """Отметить задание выполненным."""

        if self.status == self.Status.COMPLETED:
            return
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])

    def apply_completion_state(self, *, finished: bool, has_review: bool) -> bool:
        """Пометить задание выполненным, если выполнены условия."""

        if not finished or not has_review:
            return False
        if self.status == self.Status.COMPLETED:
            return False
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])
        return True

    @classmethod
    def sync_for_user_book(cls, user, book) -> None:
        """Перепроверить выполнение заданий для конкретной книги пользователя."""

        assignments = cls.objects.filter(user=user, book=book)
        if not assignments:
            return

        from shelves.models import BookProgress
        from books.models import Rating

        progress = (
            BookProgress.objects.filter(user=user, book=book)
            .order_by("-updated_at")
            .first()
        )
        percent = getattr(progress, "percent", None)
        finished = False
        if percent is not None:
            try:
                finished = Decimal(percent) >= Decimal("99.99")
            except Exception:  # pragma: no cover - fallback for unexpected values
                finished = False
        review = (
            Rating.objects.filter(user=user, book=book)
            .order_by("-created_at")
            .first()
        )
        has_review = bool(review and str(review.review or "").strip())

        for assignment in assignments:
            assignment.apply_completion_state(finished=finished, has_review=has_review)