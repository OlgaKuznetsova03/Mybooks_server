"""Сервисы для игры «Читай прежде чем покупать».

Логика вынесена в отдельный модуль, чтобы приложения могли взаимодействовать
через чётко определённый интерфейс.
"""

from __future__ import annotations

from typing import Iterable, Optional, Tuple

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from books.models import Book
from shelves.models import Shelf, ShelfItem

from ..models import Game, GameShelfBook, GameShelfPurchase, GameShelfState


class ReadBeforeBuyGame:
    """Игровая механика «Читай прежде чем покупать» для книжных полок."""

    SLUG = "read-before-buy"
    PURCHASE_COST = 1300
    BONUS_OVER_500 = 50
    BONUS_OVER_750 = 150

    @classmethod
    def get_game(cls) -> Game:
        game, _ = Game.objects.get_or_create(
            slug=cls.SLUG,
            defaults={
                "title": "Читай прежде чем покупать",
                "description": (
                    "Получайте по одному баллу за каждую прочитанную страницу и "
                    "дополнительные бонусы за большие книги. Накапливайте 1300 баллов, "
                    "чтобы добавить новую книгу на полку."
                ),
            },
        )
        return game

    # --- состояния полок ---
    @classmethod
    def enable_for_shelf(cls, user: User, shelf: Shelf) -> GameShelfState:
        if shelf.user_id != user.id:
            raise ValueError("Нельзя подключить к игре чужую полку")
        game = cls.get_game()
        state, created = GameShelfState.objects.get_or_create(
            game=game,
            shelf=shelf,
            defaults={"user": user},
        )
        if created:
            state.user = user
            state.save(update_fields=["user"])
        return state

    @classmethod
    def is_game_shelf(cls, shelf: Shelf) -> bool:
        return GameShelfState.objects.filter(game=cls.get_game(), shelf=shelf).exists()

    @classmethod
    def get_state_for_shelf(
        cls, user: User, shelf: Shelf, *, create: bool = False
    ) -> Optional[GameShelfState]:
        if shelf.user_id != user.id:
            return None
        game = cls.get_game()
        try:
            return GameShelfState.objects.get(game=game, shelf=shelf)
        except GameShelfState.DoesNotExist:
            if create:
                return cls.enable_for_shelf(user, shelf)
            return None

    # --- начисление баллов ---
    @classmethod
    def award_pages(cls, user: User, book: Book, pages_read: int) -> None:
        if pages_read <= 0:
            return
        game = cls.get_game()
        states = (
            GameShelfState.objects.filter(
                game=game,
                user=user,
                shelf__items__book=book,
            )
            .select_related("shelf")
            .distinct()
        )
        for state in states:
            cls._increment_points(state, pages_read)
            entry, _ = GameShelfBook.objects.get_or_create(state=state, book=book)
            GameShelfBook.objects.filter(pk=entry.pk).update(
                pages_logged=F("pages_logged") + pages_read,
                updated_at=timezone.now(),
            )

    @classmethod
    def handle_review(cls, user: User, book: Book, review_text: str) -> None:
        if not review_text or not review_text.strip():
            return
        game = cls.get_game()
        states = (
            GameShelfState.objects.filter(
                game=game,
                user=user,
                shelf__items__book=book,
            )
            .select_related("shelf")
            .distinct()
        )
        if not states:
            return
        bonus = cls._calculate_bonus(book)
        now = timezone.now()
        for state in states:
            entry, _ = GameShelfBook.objects.get_or_create(state=state, book=book)
            updates = {}
            if not entry.reviewed_at:
                updates["reviewed_at"] = now
                GameShelfState.objects.filter(pk=state.pk).update(
                    books_reviewed=F("books_reviewed") + 1,
                    updated_at=now,
                )
            if bonus and not entry.bonus_awarded:
                updates["bonus_awarded"] = True
                cls._increment_points(state, bonus)
            if updates:
                updates["updated_at"] = now
                GameShelfBook.objects.filter(pk=entry.pk).update(**updates)

    @classmethod
    def add_book_to_shelf(
        cls, user: User, shelf: Shelf, book: Book
    ) -> Tuple[bool, str, str]:
        """Попытаться добавить книгу в полку с учётом правил игры."""

        state = cls.get_state_for_shelf(user, shelf)
        if not state:
            _, created = ShelfItem.objects.get_or_create(shelf=shelf, book=book)
            if created:
                message = f"«{book.title}» добавлена в «{shelf.name}»."
            else:
                message = f"«{book.title}» уже есть в «{shelf.name}»."
            return True, message, "success"

        if ShelfItem.objects.filter(shelf=shelf, book=book).exists():
            return True, f"«{book.title}» уже есть в «{shelf.name}».", "info"

        with transaction.atomic():
            locked_state = GameShelfState.objects.select_for_update().get(pk=state.pk)
            if locked_state.points_balance < cls.PURCHASE_COST:
                needed = cls.PURCHASE_COST - locked_state.points_balance
                return (
                    False,
                    f"Недостаточно баллов для покупки. Нужно ещё {needed}.",
                    "error",
                )
            locked_state.points_balance -= cls.PURCHASE_COST
            locked_state.books_purchased += 1
            locked_state.save(
                update_fields=[
                    "points_balance",
                    "books_purchased",
                    "updated_at",
                ]
            )
            ShelfItem.objects.get_or_create(shelf=shelf, book=book)
            entry, _ = GameShelfBook.objects.get_or_create(state=locked_state, book=book)
            entry.purchased_at = timezone.now()
            entry.save(update_fields=["purchased_at", "updated_at"])
            GameShelfPurchase.objects.create(
                state=locked_state,
                book=book,
                points_spent=cls.PURCHASE_COST,
            )
        return True, (
            f"Книга «{book.title}» куплена за {cls.PURCHASE_COST} баллов и добавлена в «{shelf.name}»."
        ), "success"

    # --- внутренние утилиты ---
    @classmethod
    def _increment_points(cls, state: GameShelfState, amount: int) -> None:
        if amount <= 0:
            return
        now = timezone.now()
        GameShelfState.objects.filter(pk=state.pk).update(
            points_balance=F("points_balance") + amount,
            total_points_earned=F("total_points_earned") + amount,
            updated_at=now,
        )

    @staticmethod
    def _calculate_bonus(book: Book) -> int:
        total_pages = book.get_total_pages()
        if not total_pages:
            return 0
        if total_pages > 750:
            return ReadBeforeBuyGame.BONUS_OVER_750
        if total_pages > 500:
            return ReadBeforeBuyGame.BONUS_OVER_500
        return 0

    @classmethod
    def iter_participating_shelves(cls, user: User) -> Iterable[GameShelfState]:
        game = cls.get_game()
        return GameShelfState.objects.filter(game=game, user=user).select_related("shelf")