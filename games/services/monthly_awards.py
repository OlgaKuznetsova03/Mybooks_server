from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from django.conf import settings
from django.utils import timezone


MonthlyChallengeAwardGame = Literal["pages-minutes", "mini-books", "book-list"]
MonthlyChallengeAwardState = Literal[1, 2]

MONTHLY_CHALLENGE_AWARD_GAMES: tuple[MonthlyChallengeAwardGame, ...] = (
    "pages-minutes",
    "mini-books",
    "book-list",
)

DEFAULT_MONTHLY_CHALLENGE_AWARD_BASE_URL = (
    "https://s3.ru1.storage.beget.cloud/"
    "0a648590a767-openhearted-anastasiya/monthly-challenges"
)


def get_monthly_challenge_award_base_url() -> str:
    return getattr(
        settings,
        "MONTHLY_CHALLENGE_AWARD_BASE_URL",
        DEFAULT_MONTHLY_CHALLENGE_AWARD_BASE_URL,
    ).rstrip("/")


def get_monthly_challenge_month_key(value: date | datetime | str | None = None) -> str:
    if isinstance(value, str):
        cleaned_value = value.strip()
        if len(cleaned_value) == 7 and cleaned_value[2] == ".":
            return cleaned_value
        if len(cleaned_value) >= 7 and cleaned_value[4] == "-" and cleaned_value[7:8] in {"", "-"}:
            return f"{cleaned_value[5:7]}.{cleaned_value[:4]}"

        try:
            value = datetime.fromisoformat(cleaned_value)
        except ValueError:
            value = None

    if value is None:
        value = timezone.localdate()

    if isinstance(value, datetime):
        value = value.date()

    return f"{value.month:02d}.{value.year}"


def get_monthly_challenge_award_state(awarded: bool = False) -> MonthlyChallengeAwardState:
    return 2 if awarded else 1


def build_monthly_challenge_award_url(
    game: MonthlyChallengeAwardGame,
    *,
    month: date | datetime | str | None = None,
    awarded: bool = False,
    state: MonthlyChallengeAwardState | None = None,
    extension: str = "webp",
) -> str:
    if game not in MONTHLY_CHALLENGE_AWARD_GAMES:
        raise ValueError(f"Unknown monthly challenge award game: {game}")

    month_key = get_monthly_challenge_month_key(month)
    award_state = state or get_monthly_challenge_award_state(awarded)
    file_extension = extension.lstrip(".") or "webp"

    return f"{get_monthly_challenge_award_base_url()}/{game}/{month_key}/{award_state}.{file_extension}"

