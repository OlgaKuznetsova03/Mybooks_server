"""Models for tracking user rating points."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from enum import Enum
from typing import Iterable

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class LeaderboardPeriod(Enum):
    """Enumeration of supported leaderboard periods."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"

    @classmethod
    def choices(cls) -> Iterable[tuple[str, str]]:
        return tuple((item.value, item.label) for item in cls)

    @property
    def label(self) -> str:
        return {
            self.DAY: _("День"),
            self.WEEK: _("Неделя"),
            self.MONTH: _("Месяц"),
            self.YEAR: _("Год"),
        }[self]

    def period_start(self, *, reference: datetime | None = None) -> datetime:
        """Return the datetime marking the start of the period."""

        if reference is None:
            reference = timezone.now()
        current_date = timezone.localdate(reference)
        tz = timezone.get_current_timezone()
        if self is LeaderboardPeriod.DAY:
            start_date = current_date
        elif self is LeaderboardPeriod.WEEK:
            weekday = current_date.weekday()
            start_date = current_date - timedelta(days=weekday)
        elif self is LeaderboardPeriod.MONTH:
            start_date = current_date.replace(day=1)
        elif self is LeaderboardPeriod.YEAR:
            start_date = current_date.replace(month=1, day=1)
        else:  # pragma: no cover - defensive programming
            start_date = current_date
        start_naive = datetime.combine(start_date, time.min)
        return timezone.make_aware(start_naive, tz)


class UserPointEventQuerySet(models.QuerySet):
    def for_period(self, period: LeaderboardPeriod) -> "UserPointEventQuerySet":
        start = period.period_start()
        return self.filter(created_at__gte=start)


class UserPointEvent(models.Model):
    """Single entry describing awarded rating points for a user."""

    class EventType(models.TextChoices):
        BOOK_COMPLETED = "book_completed", _("Прочитана книга")
        REVIEW_WRITTEN = "review_written", _("Написан отзыв")
        CLUB_DISCUSSION = "club_discussion", _("Сообщение в совместном чтении")
        GAME_STAGE_COMPLETED = "game_stage_completed", _("Этап игры завершён")
        MARATHON_CONFIRMED = "marathon_confirmed", _("Этап марафона зачтён")

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="rating_events")
    event_type = models.CharField(max_length=64, choices=EventType.choices)
    points = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="user_rating_events",
    )
    object_id = models.PositiveBigIntegerField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    objects = UserPointEventQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["user", "event_type", "created_at"]),
            models.Index(fields=["content_type", "object_id"]),
        ]
        verbose_name = _("Событие рейтинга пользователя")
        verbose_name_plural = _("События рейтинга пользователей")

    def __str__(self) -> str:  # pragma: no cover - human readable string
        return f"{self.user} — {self.get_event_type_display()} ({self.points})"

    @classmethod
    def award(
        cls,
        *,
        user: User,
        event_type: str,
        points: int,
        related_object: models.Model | None = None,
        max_events_per_day: int | None = None,
    ) -> "UserPointEvent | None":
        """Create a new event if limits allow it."""

        if user is None or points <= 0:
            return None
        if related_object is not None and not getattr(related_object, "pk", None):
            return None
        today = timezone.localdate()
        if max_events_per_day is not None:
            today_count = cls.objects.filter(
                user=user,
                event_type=event_type,
                created_at__date=today,
            ).count()
            if today_count >= max_events_per_day:
                return None
        content_type = None
        object_id = None
        if related_object is not None:
            content_type = ContentType.objects.get_for_model(related_object)
            object_id = related_object.pk
            if cls.objects.filter(
                user=user,
                event_type=event_type,
                content_type=content_type,
                object_id=object_id,
            ).exists():
                return None
        return cls.objects.create(
            user=user,
            event_type=event_type,
            points=points,
            content_type=content_type,
            object_id=object_id,
        )

    @classmethod
    def get_leaderboard(
        cls,
        period: LeaderboardPeriod,
        *,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        """Return aggregated points per user for the requested period."""

        qs = cls.objects.for_period(period)
        aggregated = (
            qs.values("user")
            .annotate(total_points=Sum("points"))
            .order_by("-total_points", "user")
        )
        if limit is not None:
            aggregated = aggregated[:limit]
        rows = list(aggregated)
        user_map = {
            user.id: user
            for user in User.objects.filter(id__in=[row["user"] for row in rows]).select_related("profile")
        }
        results = []
        for row in rows:
            user_obj = user_map.get(row["user"])
            if not user_obj:
                continue
            results.append(
                {
                    "user": user_obj,
                    "points": int(row["total_points"] or 0),
                }
            )
        return results