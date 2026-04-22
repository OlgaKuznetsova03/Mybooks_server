"""Registry of available and planned games for the platform."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

from django.urls import reverse

from .services.book_exchange import BookExchangeGame
from .services.book_journey import BookJourneyMap
from .services.forgotten_books import ForgottenBooksGame
from .services.read_before_buy import ReadBeforeBuyGame
from .services.nobel_challenge import NobelLaureatesChallenge
from .services.yasnaya_polyana import YasnayaPolyanaForeign2026Game


@dataclass(frozen=True)
class GameCard:
    """Data required to render the game card on the listing page."""

    slug: str
    title: str
    description: str
    url_name: str
    icon: str = "🎮"
    is_available: bool = True
    badge: str | None = None
    badge_variant: str = "primary"
    highlights: Sequence[str] = ()

    def resolve_url(self) -> str:
        return reverse(self.url_name)


def get_game_cards() -> List[GameCard]:
    """Return card descriptors for all available and planned games."""

    read_before_buy = ReadBeforeBuyGame.get_game()
    forgotten_books = ForgottenBooksGame.get_game()
    book_exchange = BookExchangeGame.get_game()
    nobel_challenge = NobelLaureatesChallenge.get_game()
    yasnaya_polyana = YasnayaPolyanaForeign2026Game.get_game()
    available: List[GameCard] = [
        GameCard(
            slug=ReadBeforeBuyGame.SLUG,
            title=read_before_buy.title,
            description=read_before_buy.description,
            url_name="games:read_before_buy",
            icon="📚",
            highlights=(
                "Баллы за прочитанные страницы",
                "Бонусы за большие книги",
                "Коллекционирование покупок",
            ),
        ),
        GameCard(
            slug=BookExchangeGame.SLUG,
            title=book_exchange.title,
            description=book_exchange.description,
            url_name="games:book_exchange",
            icon="🤝",
            highlights=(
                "Вы сами задаёте цель",
                "Книги только из любимых жанров",
                "Год на прочтение и отзыв",
            ),
        ),
        GameCard(
            slug=ForgottenBooksGame.SLUG,
            title=forgotten_books.title,
            description=forgotten_books.description,
            url_name="games:forgotten_books",
            icon="🕰️",
            highlights=(
                "12 книг из домашней библиотеки",
                "Случайный выбор каждый месяц",
                "Отзыв до конца месяца",
            ),
        ),
        GameCard(
            slug="book-journey-map",
            title=BookJourneyMap.TITLE,
            description=BookJourneyMap.SUBTITLE,
            url_name="games:book_journey_map",
            icon="🗺️",
            highlights=(
                f"{BookJourneyMap.get_stage_count()} этапов",
                "Геймификация чтения",
                "Трекинг прогресса",
            ),
        ),
        GameCard(
            slug=NobelLaureatesChallenge.SLUG,
            title=nobel_challenge.title,
            description=nobel_challenge.description,
            url_name="games:nobel_challenge",
            icon="🏆",
            highlights=(
                f"{NobelLaureatesChallenge.get_stage_count()} лауреата",
                "Поиск по библиотеке",
                "Автоматический зачёт этапов",
            ),
        ),
        GameCard(
            slug=YasnayaPolyanaForeign2026Game.SLUG,
            title=yasnaya_polyana.title,
            description=yasnaya_polyana.description,
            url_name="games:yasnaya_polyana_foreign_2026",
            icon="🌿",
            highlights=(
                "Длинный и короткий список",
                "Автоматическая синхронизация с «Прочитано»",
                "Быстрый старт чтения",
            ),
        ),
    ]

    planned: Iterable[GameCard] = (
        GameCard(
            slug="reading-streaks",
            title="Ежедневные серии чтения",
            description="Отмечайте чтение каждый день и открывайте сезонные награды.",
            url_name="games:read_before_buy",
            icon="🔥",
            is_available=False,
            badge="Скоро",
            badge_variant="warning",
        ),
        GameCard(
            slug="club-quests",
            title="Квесты книжного клуба",
            description="Командные задания с совместными целями и общим прогрессом.",
            url_name="games:read_before_buy",
            icon="🤝",
            is_available=False,
            badge="В разработке",
            badge_variant="secondary",
        ),
    )

    return [*available, *planned]