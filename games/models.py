from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.urls import reverse

from user_ratings.services import award_for_game_stage_completion


class ForgottenBookEntry(models.Model):
    """Книга, выбранная пользователем для челленджа «12 забытых книг»."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="forgotten_book_entries",
    )
    book = models.ForeignKey(
        "books.Book",
        on_delete=models.CASCADE,
        related_name="forgotten_book_entries",
    )
    added_at = models.DateTimeField(auto_now_add=True)
    selected_month = models.DateField(null=True, blank=True)
    selected_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    review_submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "book")
        ordering = ["added_at"]

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return f"{self.book.title} — {self.user.username}"

    @property
    def is_selected(self) -> bool:
        return self.selected_month is not None

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None

    def get_deadline(self):
        """Вернуть крайний срок чтения для выбранного месяца."""

        if not self.selected_month:
            return None
        from calendar import monthrange

        last_day = monthrange(self.selected_month.year, self.selected_month.month)[1]
        return self.selected_month.replace(day=last_day)

    def apply_status_updates(
        self,
        *,
        finished_at,
        review_at,
        timestamp,
    ) -> None:
        """Сохранить новые данные о прочтении и отзыве."""

        updates = {}
        if self.finished_at != finished_at:
            updates["finished_at"] = finished_at
        if self.review_submitted_at != review_at:
            updates["review_submitted_at"] = review_at
        completed_at = None
        if finished_at and review_at:
            completed_at = max(finished_at, review_at)
        if self.completed_at != completed_at:
            updates["completed_at"] = completed_at
        if updates:
            updates["updated_at"] = timestamp
            for field, value in updates.items():
                setattr(self, field, value)
            self.save(update_fields=list(updates.keys()))

    @classmethod
    def sync_for_user_book(cls, user, book) -> None:
        """Обновить статус челленджа для конкретной книги пользователя."""

        entries = list(cls.objects.filter(user=user, book=book))
        if not entries:
            return

        from shelves.models import BookProgress
        from books.models import Rating

        progress = (
            BookProgress.objects.filter(user=user, book=book)
            .order_by("-updated_at")
            .first()
        )
        finished_at = None
        if progress and progress.percent is not None:
            try:
                finished = Decimal(progress.percent) >= Decimal("99.99")
            except Exception:  # pragma: no cover - fallback на некорректные значения
                finished = False
            if finished:
                finished_at = getattr(progress, "updated_at", None) or timezone.now()

        review = (
            Rating.objects.filter(user=user, book=book)
            .order_by("-created_at")
            .first()
        )
        review_at = getattr(review, "created_at", None)
        timestamp = timezone.now()

        for entry in entries:
            entry.apply_status_updates(
                finished_at=finished_at,
                review_at=review_at,
                timestamp=timestamp,
            )


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
        award_for_game_stage_completion(self)

    def apply_completion_state(self, *, finished: bool, has_review: bool) -> bool:
        """Пометить задание выполненным, если выполнены условия."""

        if not finished or not has_review:
            return False
        if self.status == self.Status.COMPLETED:
            return False
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])
        award_for_game_stage_completion(self)
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


class BookExchangeChallenge(models.Model):
    """Индивидуальный раунд игры обмена книгами."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Активный"
        COMPLETED = "completed", "Завершён"

    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="book_exchange_challenges",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="book_exchange_challenges",
    )
    round_number = models.PositiveIntegerField()
    target_books = models.PositiveIntegerField()
    shelf = models.ForeignKey(
        "shelves.Shelf",
        on_delete=models.CASCADE,
        related_name="book_exchange_challenges",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    deadline_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    genres = models.ManyToManyField(
        "books.Genre",
        related_name="book_exchange_challenges",
        blank=True,
    )

    class Meta:
        unique_together = ("user", "round_number")
        ordering = ["-started_at"]

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return f"Раунд {self.round_number} — {self.user.username}"

    def get_absolute_url(self) -> str:
        return reverse(
            "games:book_exchange_detail",
            args=[self.user.username, self.round_number],
        )

    @property
    def accepted_count(self) -> int:
        return self.accepted_books.count()

    @property
    def declined_count(self) -> int:
        return self.offers.filter(status=BookExchangeOffer.Status.DECLINED).count()

    @property
    def pending_offers_count(self) -> int:
        return self.offers.filter(status=BookExchangeOffer.Status.PENDING).count()

    def can_accept_more(self) -> bool:
        return self.status == self.Status.ACTIVE and self.accepted_count < self.target_books

    def ensure_deadline(self) -> None:
        """Зафиксировать срок чтения после набора целевого количества книг."""

        if self.locked_at or self.accepted_count < self.target_books:
            return
        now = timezone.now()
        deadline = now + timedelta(days=365)
        self.locked_at = now
        self.deadline_at = deadline
        self.save(update_fields=["locked_at", "deadline_at", "updated_at"])

    def mark_completed(self) -> None:
        if self.status == self.Status.COMPLETED:
            return
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])

    def refresh_completion_status(self) -> None:
        """Пересчитать статус завершения раунда."""

        if self.status == self.Status.COMPLETED:
            return
        accepted = list(self.accepted_books.all())
        if len(accepted) < self.target_books:
            return
        if not all(entry.is_completed for entry in accepted):
            return
        self.mark_completed()


class BookExchangeOffer(models.Model):
    """Предложение книги в рамках игры."""

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает решения"
        ACCEPTED = "accepted", "Принято"
        DECLINED = "declined", "Отклонено"

    challenge = models.ForeignKey(
        BookExchangeChallenge,
        on_delete=models.CASCADE,
        related_name="offers",
    )
    offered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="book_exchange_offers",
    )
    book = models.ForeignKey(
        "books.Book",
        on_delete=models.CASCADE,
        related_name="book_exchange_offers",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("challenge", "book", "offered_by")

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return f"{self.book.title} → {self.challenge.user.username}"


class BookExchangeAcceptedBook(models.Model):
    """Книга, принятая в рамках игрового вызова."""

    challenge = models.ForeignKey(
        BookExchangeChallenge,
        on_delete=models.CASCADE,
        related_name="accepted_books",
    )
    offer = models.OneToOneField(
        BookExchangeOffer,
        on_delete=models.CASCADE,
        related_name="accepted_entry",
    )
    book = models.ForeignKey(
        "books.Book",
        on_delete=models.CASCADE,
        related_name="book_exchange_acceptances",
    )
    accepted_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    review_submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("challenge", "book")
        ordering = ["accepted_at"]

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return f"{self.book.title} — {self.challenge}"

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None

    def apply_status_updates(
        self,
        *,
        finished_at,
        review_at,
        timestamp,
    ) -> None:
        updates = {}
        if self.finished_at != finished_at:
            updates["finished_at"] = finished_at
        if self.review_submitted_at != review_at:
            updates["review_submitted_at"] = review_at
        completed = None
        if finished_at and review_at:
            completed = max(finished_at, review_at)
        if self.completed_at != completed:
            updates["completed_at"] = completed
        if updates:
            updates["updated_at"] = timestamp
            for field, value in updates.items():
                setattr(self, field, value)
            self.save(update_fields=list(updates.keys()))

    @classmethod
    def sync_for_user_book(cls, user, book) -> None:
        """Обновить статусы чтения для принятой книги."""

        entries = list(
            cls.objects.filter(challenge__user=user, book=book)
            .select_related("challenge")
            .all()
        )
        if not entries:
            return

        from shelves.models import BookProgress
        from books.models import Rating

        progress = (
            BookProgress.objects.filter(user=user, book=book)
            .order_by("-updated_at")
            .first()
        )
        finished_at = None
        if progress and progress.percent is not None:
            try:
                finished = Decimal(progress.percent) >= Decimal("99.99")
            except Exception:  # pragma: no cover - defensive for invalid data
                finished = False
            if finished:
                finished_at = getattr(progress, "updated_at", None) or timezone.now()

        review = (
            Rating.objects.filter(user=user, book=book)
            .order_by("-created_at")
            .first()
        )
        review_at = getattr(review, "created_at", None)
        timestamp = timezone.now()

        for entry in entries:
            entry.apply_status_updates(
                finished_at=finished_at,
                review_at=review_at,
                timestamp=timestamp,
            )
            entry.challenge.refresh_completion_status()


__all__ = [
    "ForgottenBookEntry",
    "Game",
    "GameShelfState",
    "GameShelfBook",
    "GameShelfPurchase",
    "BookJourneyAssignment",
    "BookExchangeChallenge",
    "BookExchangeOffer",
    "BookExchangeAcceptedBook",
]