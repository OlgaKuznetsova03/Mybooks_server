from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Iterable

from django.db.models import Count, DateTimeField, F, Max, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import DiscussionPost, DiscussionRead, ReadingClub, ReadingNorm, ReadingParticipant


def attach_prefetched_counts(readings: Iterable[ReadingClub]) -> None:
    """Populate cached message and participant counts without GROUP BY."""

    reading_list = list(readings)
    if not reading_list:
        return

    reading_ids = [reading.id for reading in reading_list if reading.id is not None]
    if not reading_ids:
        return

    message_counts = Counter(
        DiscussionPost.objects.filter(topic__reading_id__in=reading_ids)
        .order_by()
        .values_list("topic__reading_id", flat=True)
    )

    approved_counts = Counter(
        ReadingParticipant.objects.filter(
            reading_id__in=reading_ids,
            status=ReadingParticipant.Status.APPROVED,
        )
        .order_by()
        .values_list("reading_id", flat=True)
    )

    for reading in reading_list:
        reading.set_prefetched_message_count(message_counts.get(reading.id, 0))
        reading.approved_participant_count = approved_counts.get(reading.id, 0)


def mark_topic_read(user, topic: ReadingNorm) -> None:
    if user is None or not getattr(user, "is_authenticated", False):
        return
    DiscussionRead.objects.update_or_create(
        user=user,
        topic=topic,
        defaults={"last_read_at": timezone.now()},
    )


def get_unread_discussion_topics(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return [], 0

    last_read_subquery = DiscussionRead.objects.filter(
        user=user, topic=OuterRef("pk")
    ).values("last_read_at")[:1]
    earliest = timezone.make_aware(datetime(1970, 1, 1))

    topics = (
        ReadingNorm.objects.filter(
            reading__participants__user=user,
            reading__participants__status=ReadingParticipant.Status.APPROVED,
        )
        .prefetch_related("reading", "reading__book")
        .annotate(
            last_read_at=Coalesce(
                Subquery(last_read_subquery),
                Value(earliest, output_field=DateTimeField()),
            )
        )
        .annotate(
            unread_count=Count(
                "posts",
                filter=Q(posts__created_at__gt=F("last_read_at"))
                & ~Q(posts__author=user),
                distinct=True,
            ),
            last_post_at=Max("posts__created_at"),
        )
        .filter(unread_count__gt=0)
        .order_by("-last_post_at")
    )

    topic_list = list(topics)
    total_unread = sum(topic.unread_count for topic in topic_list)
    return topic_list, total_unread


def get_unread_discussion_total(user) -> int:
    if user is None or not getattr(user, "is_authenticated", False):
        return 0

    last_read_subquery = DiscussionRead.objects.filter(
        user=user, topic=OuterRef("topic_id")
    ).values("last_read_at")[:1]

    return (
        DiscussionPost.objects.filter(
            topic__reading__participants__user=user,
            topic__reading__participants__status=ReadingParticipant.Status.APPROVED,
        )
        .exclude(author=user)
        .annotate(last_read_at=Subquery(last_read_subquery))
        .filter(Q(last_read_at__isnull=True) | Q(created_at__gt=F("last_read_at")))
        .count()
    )
