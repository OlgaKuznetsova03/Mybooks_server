from django.conf import settings
from django.db import models


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