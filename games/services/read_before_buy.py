"""Сервисы для игры «Читай прежде чем покупать».

Логика вынесена в отдельный модуль, чтобы приложения могли взаимодействовать
через чётко определённый интерфейс.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Iterable, Optional, Tuple

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from books.models import Book
from shelves.models import Shelf, ShelfItem
from shelves.services import get_home_library_shelf

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
        home_shelf = get_home_library_shelf(user)
        if shelf.pk != home_shelf.pk:
            raise ValueError(
                f"К игре можно подключить только полку «{home_shelf.name}»."
            )
        game = cls.get_game()
        state, created = GameShelfState.objects.get_or_create(
            game=game,
            shelf=home_shelf,
            defaults={"user": user},
        )
        if created:
            state.user = user
            state.save(update_fields=["user"])
        return state

    @classmethod
    def is_game_shelf(cls, shelf: Shelf) -> bool:
        if shelf.user_id is None:
            return False
        home_shelf = get_home_library_shelf(shelf.user)
        if shelf.pk != home_shelf.pk:
            return False
        return GameShelfState.objects.filter(game=cls.get_game(), shelf=home_shelf).exists()

    @classmethod
    def get_state_for_shelf(
        cls, user: User, shelf: Shelf, *, create: bool = False
    ) -> Optional[GameShelfState]:
        if shelf.user_id != user.id:
            return None
        home_shelf = get_home_library_shelf(user)
        if shelf.pk != home_shelf.pk:
            return None
        game = cls.get_game()
        try:
            return GameShelfState.objects.get(game=game, shelf=home_shelf)
        except GameShelfState.DoesNotExist:
            if create:
                return cls.enable_for_shelf(user, home_shelf)
            return None

    @classmethod
    def get_state_by_id(cls, user: User, state_id: int) -> Optional[GameShelfState]:
        game = cls.get_game()
        try:
            state = GameShelfState.objects.get(pk=state_id, user=user, game=game)
        except GameShelfState.DoesNotExist:
            return None
        home_shelf = get_home_library_shelf(user)
        if state.shelf_id != home_shelf.pk:
            return None
        return state

    # --- начисление баллов ---
    @classmethod
    def award_pages(
        cls,
        user: User,
        book: Book,
        pages_read: int,
        *,
        occurred_at: datetime | date | None = None,
    ) -> None:
        if pages_read <= 0:
            return
        game = cls.get_game()
        moment = cls._normalize_timestamp(occurred_at)
        home_shelf = get_home_library_shelf(user)
        states = (
            GameShelfState.objects.filter(
                game=game,
                user=user,
                shelf=home_shelf,
                shelf__items__book=book,
            )
            .select_related("shelf")
            .distinct()
        )
        for state in states:
            if moment < state.started_at:
                continue
            cls._increment_points(state, pages_read, timestamp=moment)
            entry, _ = GameShelfBook.objects.get_or_create(state=state, book=book)
            GameShelfBook.objects.filter(pk=entry.pk).update(
                pages_logged=F("pages_logged") + pages_read,
                updated_at=moment,
            )

    @classmethod
    def handle_review(cls, user: User, book: Book, review_text: str) -> None:
        if not review_text or not review_text.strip():
            return
        game = cls.get_game()
        home_shelf = get_home_library_shelf(user)
        states = (
            GameShelfState.objects.filter(
                game=game,
                user=user,
                shelf=home_shelf,
                shelf__items__book=book,
            )
            .select_related("shelf")
            .distinct()
        )
        if not states:
            return
        bonus = cls._calculate_bonus(book)
        moment = cls._normalize_timestamp(None)
        for state in states:
            if moment < state.started_at:
                continue
            entry, _ = GameShelfBook.objects.get_or_create(state=state, book=book)
            updates = {}
            if not entry.reviewed_at:
                updates["reviewed_at"] = moment
                GameShelfState.objects.filter(pk=state.pk).update(
                    books_reviewed=F("books_reviewed") + 1,
                    updated_at=moment,
                )
            if bonus and not entry.bonus_awarded:
                updates["bonus_awarded"] = True
                cls._increment_points(state, bonus, timestamp=moment)
            if updates:
                updates["updated_at"] = moment
                GameShelfBook.objects.filter(pk=entry.pk).update(**updates)

    @classmethod
    def ensure_completion_awarded(
        cls,
        user: User,
        shelf: Shelf,
        book: Book,
        *,
        occurred_at: datetime | date | None = None,
    ) -> None:
        home_shelf = get_home_library_shelf(user)
        if shelf.pk != home_shelf.pk:
            return
        state = cls.get_state_for_shelf(user, home_shelf)
        if not state:
            return
        moment = cls._normalize_timestamp(occurred_at)
        if moment < state.started_at:
            return
        if not ShelfItem.objects.filter(shelf=home_shelf, book=book).exists():
            return
        total_pages = book.get_total_pages()
        if not total_pages:
            return
        entry, _ = GameShelfBook.objects.get_or_create(state=state, book=book)
        missing = max(0, total_pages - entry.pages_logged)
        if missing <= 0:
            return
        cls._increment_points(state, missing, timestamp=moment)
        GameShelfBook.objects.filter(pk=entry.pk).update(
            pages_logged=F("pages_logged") + missing,
            updated_at=moment,
        )

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

    @classmethod
    def spend_points_for_bulk_purchase(
        cls, state: GameShelfState, count: int
    ) -> Tuple[bool, str, str]:
        if count <= 0:
            return False, "Укажите количество купленных книг.", "error"

        total_cost = cls.PURCHASE_COST * count
        with transaction.atomic():
            locked_state = GameShelfState.objects.select_for_update().get(pk=state.pk)
            if locked_state.points_balance < total_cost:
                need = total_cost - locked_state.points_balance
                return (
                    False,
                    f"Недостаточно баллов: требуется ещё {need} для покупки {count} книг.",
                    "error",
                )
            locked_state.points_balance -= total_cost
            locked_state.books_purchased += count
            locked_state.save(
                update_fields=[
                    "points_balance",
                    "books_purchased",
                    "updated_at",
                ]
            )
            purchases = [
                GameShelfPurchase(
                    state=locked_state,
                    book=None,
                    points_spent=cls.PURCHASE_COST,
                )
                for _ in range(count)
            ]
            GameShelfPurchase.objects.bulk_create(purchases)

        message = (
            f"Списано {total_cost} баллов за {count} купленных книг."
        )
        return True, message, "success"

    # --- внутренние утилиты ---
    @classmethod
    def _increment_points(
        cls, state: GameShelfState, amount: int, *, timestamp: datetime | date | None = None
    ) -> None:
        if amount <= 0:
            return
        moment = cls._normalize_timestamp(timestamp)
        GameShelfState.objects.filter(pk=state.pk).update(
            points_balance=F("points_balance") + amount,
            total_points_earned=F("total_points_earned") + amount,
            updated_at=moment,
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

    @staticmethod
    def _normalize_timestamp(value: datetime | date | None) -> datetime:
        moment: datetime
        if value is None:
            moment = timezone.now()
        elif isinstance(value, datetime):
            moment = value
        else:
            moment = datetime.combine(value, time.max)
        if timezone.is_naive(moment):
            moment = timezone.make_aware(moment)
        return moment
    
    @classmethod
    def iter_participating_shelves(cls, user: User) -> Iterable[GameShelfState]:
        game = cls.get_game()
        home_shelf = get_home_library_shelf(user)
        return (
            GameShelfState.objects.filter(game=game, user=user, shelf=home_shelf)
            .select_related("shelf")
        )