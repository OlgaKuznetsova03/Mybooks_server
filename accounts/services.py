from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.utils.translation import gettext_lazy as _

from .models import CoinTransaction, Profile


FEATURE_ACCESS_COST = 100


class InsufficientCoinsError(Exception):
    """Raised when a profile does not have enough coins for a feature purchase."""

    def __init__(self, message: str | None = None):
        default_message = _("Недостаточно монет для выполнения действия.")
        super().__init__(message or default_message)


@dataclass(frozen=True)
class FeatureChargeResult:
    profile: Profile
    transaction: CoinTransaction
    cost: int


def charge_feature_access(
    profile: Profile,
    *,
    cost: int = FEATURE_ACCESS_COST,
    description: str | None = None,
) -> FeatureChargeResult:
    """Deduct coins from the profile for using a paid feature.

    Premium users have unlimited coins, therefore the transaction is recorded
    without affecting the balance. When there are not enough coins the
    :class:`InsufficientCoinsError` is raised.
    """

    if cost <= 0:
        raise ValueError("Feature cost must be positive")

    try:
        transaction = profile.spend_coins(
            cost,
            transaction_type=CoinTransaction.Type.FEATURE_PURCHASE,
            description=description or _("Оплата функции сайта"),
        )
    except ValueError as exc:
        raise InsufficientCoinsError() from exc

    return FeatureChargeResult(profile=profile, transaction=transaction, cost=cost)


def get_feature_payment_context(
    profile: Profile | None,
    *,
    cost: int = FEATURE_ACCESS_COST,
) -> dict[str, Any]:
    """Build a template-friendly context about feature payments.

    Parameters
    ----------
    profile:
        The profile of the current user. ``None`` means the user is anonymous.
    cost:
        How many coins the feature costs. Must be positive.
    """

    if cost <= 0:
        raise ValueError("Feature cost must be positive")

    has_profile = profile is not None
    has_unlimited_coins = bool(profile and profile.has_unlimited_coins)
    coin_balance: int | None = None
    can_afford = False
    shortage: int | None = None

    if profile:
        if has_unlimited_coins:
            can_afford = True
        else:
            coin_balance = profile.coins
            can_afford = coin_balance >= cost
            if not can_afford:
                shortage = cost - coin_balance

    return {
        "cost": cost,
        "has_profile": has_profile,
        "has_unlimited_coins": has_unlimited_coins,
        "coin_balance": coin_balance,
        "can_afford": can_afford,
        "shortage": shortage,
    }