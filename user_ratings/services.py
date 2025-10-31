"""Helper utilities for awarding rating points."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.contrib.auth import get_user_model
from django.db import models

from .models import LeaderboardPeriod, UserPointEvent

User = get_user_model()


@dataclass(frozen=True)
class AwardConfig:
    points: int
    daily_limit: Optional[int] = None


BOOK_COMPLETION = AwardConfig(points=50, daily_limit=2)
REVIEW_COMPLETION = AwardConfig(points=30, daily_limit=3)
DISCUSSION_POST = AwardConfig(points=15)
GAME_STAGE = AwardConfig(points=40)
MARATHON_CONFIRMATION = AwardConfig(points=35)


def _award(
    *,
    user: User,
    event_type: str,
    config: AwardConfig,
    related_object: Optional[models.Model] = None,
) -> Optional[UserPointEvent]:
    if not user or not getattr(user, "pk", None):
        return None
    return UserPointEvent.award(
        user=user,
        event_type=event_type,
        points=config.points,
        related_object=related_object,
        max_events_per_day=config.daily_limit,
    )


def award_for_book_completion(user: User, book: models.Model) -> Optional[UserPointEvent]:
    return _award(
        user=user,
        event_type=UserPointEvent.EventType.BOOK_COMPLETED,
        config=BOOK_COMPLETION,
        related_object=book,
    )


def award_for_review(user: User, rating: models.Model) -> Optional[UserPointEvent]:
    return _award(
        user=user,
        event_type=UserPointEvent.EventType.REVIEW_WRITTEN,
        config=REVIEW_COMPLETION,
        related_object=rating,
    )


def award_for_discussion_post(post: models.Model) -> Optional[UserPointEvent]:
    return _award(
        user=post.author,
        event_type=UserPointEvent.EventType.CLUB_DISCUSSION,
        config=DISCUSSION_POST,
        related_object=post,
    )


def award_for_game_stage_completion(assignment: models.Model) -> Optional[UserPointEvent]:
    return _award(
        user=assignment.user,
        event_type=UserPointEvent.EventType.GAME_STAGE_COMPLETED,
        config=GAME_STAGE,
        related_object=assignment,
    )


def award_for_marathon_confirmation(entry: models.Model) -> Optional[UserPointEvent]:
    return _award(
        user=entry.participant.user,
        event_type=UserPointEvent.EventType.MARATHON_CONFIRMED,
        config=MARATHON_CONFIRMATION,
        related_object=entry,
    )


__all__ = [
    "LeaderboardPeriod",
    "award_for_book_completion",
    "award_for_review",
    "award_for_discussion_post",
    "award_for_game_stage_completion",
    "award_for_marathon_confirmation",
]