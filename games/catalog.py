"""Registry of available and planned games for the platform."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

from django.urls import reverse

from .services.book_journey import BookJourneyMap
from .services.read_before_buy import ReadBeforeBuyGame


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