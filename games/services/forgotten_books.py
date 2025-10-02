"""Сервисы для челленджа «12 забытых книг».

Описывают доступ к модели и вспомогательную логику выбора книг по месяцам.
"""

from __future__ import annotations

import calendar
import random
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from books.models import Book
from shelves.models import ShelfItem
from shelves.services import (
    DEFAULT_HOME_LIBRARY_SHELF,
    DEFAULT_READ_SHELF,
    get_home_library_shelf,
)

from ..models import ForgottenBookEntry, Game


@dataclass(frozen=True)
class MonthlySelection:
    entry: ForgottenBookEntry
    month_start: date
    deadline: date


class ForgottenBooksGame:
    """Интерфейс для работы с челленджем «12 забытых книг»."""

    SLUG = "forgotten-books-12"
    TITLE = "12 забытых книг"
    DESCRIPTION = (
        "Соберите двенадцать книг из своей домашней библиотеки и каждый месяц читайте "
        "одну новую. Первый день месяца выбирает следующую книгу случайным образом — "
        "у вас есть целый месяц, чтобы прочитать её и написать отзыв."
    )
    MAX_BOOKS = 12

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

    # --- работа с подборкой книг ---
    @classmethod
    def get_entries(cls, user: User) -> Iterable[ForgottenBookEntry]:
        return ForgottenBookEntry.objects.filter(user=user).select_related("book")

    @classmethod
    def can_add_more(cls, user: User) -> bool:
        return ForgottenBookEntry.objects.filter(user=user).count() < cls.MAX_BOOKS

    @classmethod
    def add_book(cls, user: User, book: Book) -> tuple[bool, str, str]:
        if ForgottenBookEntry.objects.filter(user=user, book=book).exists():
            return False, "Эта книга уже участвует в челлендже.", "warning"
        total = ForgottenBookEntry.objects.filter(user=user).count()
        if total >= cls.MAX_BOOKS:
            return False, "Вы уже добавили все 12 книг.", "warning"
        home_shelf = get_home_library_shelf(user)
        if not ShelfItem.objects.filter(shelf=home_shelf, book=book).exists():
            return False, (
                "Добавьте книгу в полку «{name}», чтобы участвовать в челлендже."
            ).format(name=DEFAULT_HOME_LIBRARY_SHELF), "danger"
        if ShelfItem.objects.filter(
            shelf__user=user, shelf__name=DEFAULT_READ_SHELF, book=book
        ).exists():
            return False, "Эта книга уже отмечена как прочитанная.", "danger"
        entry = ForgottenBookEntry.objects.create(user=user, book=book)
        return True, f"Книга «{book.title}» добавлена в список из 12 забытых книг.", "success"

    @classmethod
    def remove_entry(cls, entry: ForgottenBookEntry) -> tuple[bool, str, str]:
        if entry.is_selected:
            return False, "Нельзя убрать книгу, которая уже выбрана на месяц.", "warning"
        title = entry.book.title
        entry.delete()
        return True, f"Книга «{title}» удалена из списка.", "info"

    # --- выбор книги на месяц ---
    @classmethod
    def ensure_monthly_selection(
        cls,
        user: User,
        *,
        reference_date: Optional[date] = None,
    ) -> Optional[MonthlySelection]:
        today = reference_date or timezone.localdate()
        month_start = cls._get_month_start(today)
        with transaction.atomic():
            existing = (
                ForgottenBookEntry.objects.select_for_update()
                .filter(user=user, selected_month=month_start)
                .select_related("book")
                .first()
            )
            if existing:
                return MonthlySelection(
                    entry=existing,
                    month_start=month_start,
                    deadline=cls._get_month_deadline(month_start),
                )
            total = (
                ForgottenBookEntry.objects.select_for_update()
                .filter(user=user)
                .count()
            )
            if total < cls.MAX_BOOKS:
                return None
            available = list(
                ForgottenBookEntry.objects.select_for_update()
                .filter(user=user, selected_month__isnull=True)
                .select_related("book")
            )
            if not available:
                return None
            chosen = random.choice(available)
            now = timezone.now()
            ForgottenBookEntry.objects.filter(pk=chosen.pk).update(
                selected_month=month_start,
                selected_at=now,
                updated_at=now,
            )
            chosen.selected_month = month_start
            chosen.selected_at = now
            return MonthlySelection(
                entry=chosen,
                month_start=month_start,
                deadline=cls._get_month_deadline(month_start),
            )

    @classmethod
    def get_current_selection(
        cls, user: User, *, reference_date: Optional[date] = None
    ) -> Optional[MonthlySelection]:
        today = reference_date or timezone.localdate()
        month_start = cls._get_month_start(today)
        entry = (
            ForgottenBookEntry.objects.filter(user=user, selected_month=month_start)
            .select_related("book")
            .first()
        )
        if not entry:
            return None
        return MonthlySelection(
            entry=entry,
            month_start=month_start,
            deadline=cls._get_month_deadline(month_start),
        )

    @staticmethod
    def _get_month_start(value: date) -> date:
        return value.replace(day=1)

    @staticmethod
    def _get_month_deadline(month_start: date) -> date:
        last_day = calendar.monthrange(month_start.year, month_start.month)[1]
        return month_start.replace(day=last_day)


__all__ = ["ForgottenBooksGame", "MonthlySelection"]