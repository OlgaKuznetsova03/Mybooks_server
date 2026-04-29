from __future__ import annotations

from typing import Any, Dict, Optional

from django.db import transaction

from games.models import Game, YasnayaPolyanaNominationBook


class GameCloner:
    """Сервис клонирования игр и связанного контента."""

    @classmethod
    @transaction.atomic
    def clone_game(
        cls,
        *,
        source_game: Game,
        new_slug: str,
        new_title: str,
        new_description: str = "",
        year: Optional[int] = None,
        copy_books: bool = True,
        extra_config: Optional[Dict[str, Any]] = None,
    ) -> Game:
        new_game = Game.objects.create(
            slug=new_slug,
            title=new_title,
            description=new_description or source_game.description,
            year=year if year is not None else source_game.year,
            is_active=source_game.is_active,
        )
        if copy_books:
            cls._copy_yasnaya_polyana_books(source_game=source_game, target_game=new_game)
        cls._copy_game_config(source_game=source_game, target_game=new_game, extra_config=extra_config)
        return new_game

    @staticmethod
    def _copy_yasnaya_polyana_books(*, source_game: Game, target_game: Game) -> int:
        source_books = YasnayaPolyanaNominationBook.objects.filter(game=source_game).select_related("book")
        created_count = 0
        for source_entry in source_books:
            YasnayaPolyanaNominationBook.objects.create(
                game=target_game,
                book=source_entry.book,
                is_shortlist=source_entry.is_shortlist,
            )
            created_count += 1
        return created_count

    @staticmethod
    def _copy_game_config(*, source_game: Game, target_game: Game, extra_config: Optional[Dict[str, Any]] = None) -> None:
        """Расширяемая точка для копирования других связанных сущностей."""
        _ = (source_game, target_game, extra_config)
