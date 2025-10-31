from __future__ import annotations

from collections import Counter
from typing import Iterable

from .models import DiscussionPost, ReadingClub, ReadingParticipant


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
