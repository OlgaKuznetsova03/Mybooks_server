"""Custom middleware for the accounts app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from django.contrib import messages
from django.contrib.messages.api import MessageFailure
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from .models import DAILY_LOGIN_REWARD_COINS, Profile


@dataclass
class DailyLoginRewardMiddleware:
    """Grant a daily login reward the first time a user visits each day."""

    get_response: Callable[[HttpRequest], HttpResponse]
    session_key: str = "accounts.last_daily_reward_at"

    def __call__(self, request: HttpRequest) -> HttpResponse:
        self._maybe_grant_daily_reward(request)
        return self.get_response(request)

    def _maybe_grant_daily_reward(self, request: HttpRequest) -> None:
        if not request.user.is_authenticated:
            if self.session_key in request.session:
                request.session.pop(self.session_key, None)
            return

        try:
            profile = request.user.profile
        except Profile.DoesNotExist:
            return

        today = timezone.localdate()
        today_iso = today.isoformat()
        last_reward_date = request.session.get(self.session_key)

        if last_reward_date == today_iso:
            return

        tx = profile.grant_daily_login_reward()
        request.session[self.session_key] = today_iso

        if tx:
            try:
                messages.success(
                    request,
                    f"Вы получили {DAILY_LOGIN_REWARD_COINS} монет за ежедневный вход!",
                )
            except MessageFailure:
                pass