from __future__ import annotations

from dataclasses import dataclass

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