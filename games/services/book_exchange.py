"""Helpers for the player-driven book exchange challenge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone

from books.models import Book, Genre
from shelves.models import Shelf, ShelfItem
from shelves.services import ALL_DEFAULT_READ_SHELF_NAMES

from ..models import (
    BookExchangeAcceptedBook,
    BookExchangeChallenge,
    BookExchangeOffer,
    Game,
)

User = get_user_model()


@dataclass(frozen=True)
class OfferBundle:
    pending: Sequence[BookExchangeOffer]
    accepted: Sequence[BookExchangeOffer]
    declined: Sequence[BookExchangeOffer]


class BookExchangeGame:
    """High-level API for managing the book exchange challenge."""

    SLUG = "book-exchange-challenge"
    TITLE = "Обмен читательскими вызовами"
    DESCRIPTION = (
        "Выберите, сколько новых книг готовы принять, укажите предпочтительные жанры и "
        "позвольте другим игрокам пополнять вашу игровую полку прочитанными историями."
    )
    SHELF_NAME_TEMPLATE = "Игровой обмен — Раунд {number}"

    @classmethod
    def get_game(cls) -> Game:
        game, _ = Game.objects.get_or_create(
            slug=cls.SLUG,
            defaults={
                "title": cls.TITLE,
                "description": cls.DESCRIPTION,
            },
        )
        return game

    # --- challenge lifecycle -------------------------------------------------
    @classmethod
    def has_active_challenge(cls, user: User) -> bool:
        return BookExchangeChallenge.objects.filter(
            user=user,
            status=BookExchangeChallenge.Status.ACTIVE,
        ).exists()

    @classmethod
    def get_active_challenge(cls, user: User) -> BookExchangeChallenge | None:
        return (
            BookExchangeChallenge.objects.filter(
                user=user,
                status=BookExchangeChallenge.Status.ACTIVE,
            )
            .select_related("shelf")
            .prefetch_related("genres")
            .first()
        )

    @classmethod
    def get_completed_challenges(cls, user: User) -> Iterable[BookExchangeChallenge]:
        return (
            BookExchangeChallenge.objects.filter(
                user=user,
                status=BookExchangeChallenge.Status.COMPLETED,
            )
            .select_related("shelf")
            .prefetch_related("genres")
            .order_by("-completed_at", "-round_number")
        )

    @classmethod
    def get_public_active_challenges(
        cls, *, exclude_user: User | None = None
    ) -> Iterable[BookExchangeChallenge]:
        qs = BookExchangeChallenge.objects.filter(
            status=BookExchangeChallenge.Status.ACTIVE
        ).select_related("user", "shelf").prefetch_related("accepted_books")
        if exclude_user is not None:
            qs = qs.exclude(user=exclude_user)
        return qs.order_by("user__username")

    @classmethod
    def get_challenge_for_view(
        cls, username: str, round_number: int
    ) -> BookExchangeChallenge | None:
        return (
            BookExchangeChallenge.objects.filter(
                user__username=username,
                round_number=round_number,
            )
            .select_related("user", "shelf")
            .prefetch_related("genres")
            .first()
        )

    @classmethod
    def start_new_challenge(
        cls,
        user: User,
        *,
        target_books: int,
        genres: Sequence[Genre],
    ) -> BookExchangeChallenge:
        if target_books <= 0:
            raise ValueError("Target book count must be positive.")
        if cls.has_active_challenge(user):
            raise ValueError("Active challenge already exists for this user.")

        game = cls.get_game()
        with transaction.atomic():
            next_number = (
                BookExchangeChallenge.objects.filter(user=user)
                .aggregate(number=Max("round_number"))
                .get("number")
                or 0
            )
            round_number = next_number + 1
            shelf_name = cls.SHELF_NAME_TEMPLATE.format(number=round_number)
            shelf = Shelf.objects.create(
                user=user,
                name=shelf_name,
                is_default=False,
                is_public=True,
            )
            challenge = BookExchangeChallenge.objects.create(
                game=game,
                user=user,
                round_number=round_number,
                target_books=target_books,
                shelf=shelf,
            )
            if genres:
                challenge.genres.set(genres)
            return challenge

    # --- offers --------------------------------------------------------------
    @classmethod
    def get_offer_bundle(
        cls, challenge: BookExchangeChallenge
    ) -> OfferBundle:
        offers = list(
            challenge.offers.select_related("book", "offered_by", "accepted_entry")
            .prefetch_related("book__authors")
            .order_by("-created_at")
        )
        pending = [item for item in offers if item.status == BookExchangeOffer.Status.PENDING]
        accepted = [item for item in offers if item.status == BookExchangeOffer.Status.ACCEPTED]
        declined = [item for item in offers if item.status == BookExchangeOffer.Status.DECLINED]
        return OfferBundle(pending=pending, accepted=accepted, declined=declined)

    @classmethod
    def offer_book(
        cls,
        challenge: BookExchangeChallenge,
        *,
        offered_by: User,
        book: Book,
    ) -> tuple[bool, str, str]:
        if challenge.status != BookExchangeChallenge.Status.ACTIVE:
            return False, "Раунд уже завершён.", "warning"
        if offered_by == challenge.user:
            return False, "Нельзя предлагать книги самому себе.", "danger"
        if challenge.accepted_count >= challenge.target_books:
            return False, "Игрок уже набрал нужное количество книг.", "info"
        genre_ids = list(challenge.genres.values_list("id", flat=True))
        if genre_ids:
            if not book.genres.filter(id__in=genre_ids).exists():
                return False, "Жанр книги не входит в предпочтения игрока.", "warning"
        has_read = ShelfItem.objects.filter(
            shelf__user=offered_by,
            shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
            book=book,
        ).exists()
        if not has_read:
            return False, "Добавьте книгу в полку «Прочитал», прежде чем предлагать.", "danger"
        if BookExchangeOffer.objects.filter(
            challenge=challenge, offered_by=offered_by, book=book
        ).exists():
            return False, "Вы уже предложили эту книгу игроку.", "info"

        BookExchangeOffer.objects.create(
            challenge=challenge,
            offered_by=offered_by,
            book=book,
        )
        return True, f"Книга «{book.title}» отправлена на рассмотрение.", "success"

    @classmethod
    def _get_decline_stats(
        cls, challenge: BookExchangeChallenge
    ) -> tuple[int, int]:
        result = challenge.offers.aggregate(
            total=Count("id"),
            declined=Count("id", filter=Q(status=BookExchangeOffer.Status.DECLINED)),
        )
        return result.get("total", 0), result.get("declined", 0)

    @classmethod
    def can_decline_offer(
        cls, challenge: BookExchangeChallenge, *, additional_decline: int = 0
    ) -> bool:
        total, declined = cls._get_decline_stats(challenge)
        allowed = total // 2
        return declined + additional_decline <= allowed

    @classmethod
    def accept_offer(
        cls,
        offer: BookExchangeOffer,
        *,
        acting_user: User,
    ) -> tuple[bool, str, str]:
        challenge = offer.challenge
        if acting_user != challenge.user:
            return False, "Только владелец раунда может принимать книги.", "danger"
        if offer.status != BookExchangeOffer.Status.PENDING:
            return False, "Предложение уже обработано.", "info"
        if challenge.status != BookExchangeChallenge.Status.ACTIVE:
            return False, "Раунд завершён.", "warning"
        with transaction.atomic():
            challenge = (
                BookExchangeChallenge.objects.select_for_update()
                .filter(pk=challenge.pk)
                .first()
            )
            if not challenge:
                return False, "Раунд не найден.", "danger"
            if challenge.accepted_books.count() >= challenge.target_books:
                return False, "Вы уже приняли достаточно книг.", "info"
            now = timezone.now()
            BookExchangeOffer.objects.filter(pk=offer.pk).update(
                status=BookExchangeOffer.Status.ACCEPTED,
                responded_at=now,
                updated_at=now,
            )
            offer.refresh_from_db()
            accepted_entry, created = BookExchangeAcceptedBook.objects.get_or_create(
                offer=offer,
                defaults={
                    "challenge": challenge,
                    "book": offer.book,
                },
            )
            if not created and accepted_entry.challenge_id != challenge.id:
                accepted_entry.challenge = challenge
                accepted_entry.save(update_fields=["challenge", "updated_at"])
            ShelfItem.objects.get_or_create(shelf=challenge.shelf, book=offer.book)
            BookExchangeAcceptedBook.sync_for_user_book(challenge.user, offer.book)
            challenge.ensure_deadline()
            challenge.refresh_completion_status()
        return True, f"Книга «{offer.book.title}» добавлена на игровую полку.", "success"

    @classmethod
    def decline_offer(
        cls,
        offer: BookExchangeOffer,
        *,
        acting_user: User,
    ) -> tuple[bool, str, str]:
        challenge = offer.challenge
        if acting_user != challenge.user:
            return False, "Только владелец раунда может отклонять книги.", "danger"
        if offer.status != BookExchangeOffer.Status.PENDING:
            return False, "Предложение уже обработано.", "info"
        if not cls.can_decline_offer(challenge, additional_decline=1):
            return False, "Нельзя отклонить более половины предложенных книг.", "warning"
        now = timezone.now()
        BookExchangeOffer.objects.filter(pk=offer.pk).update(
            status=BookExchangeOffer.Status.DECLINED,
            responded_at=now,
            updated_at=now,
        )
        return True, f"Книга «{offer.book.title}» отклонена.", "info"


__all__ = ["BookExchangeGame", "OfferBundle"]