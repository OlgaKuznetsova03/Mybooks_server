"""Integration helpers for working with YooKassa payments."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.conf import settings

try:  # pragma: no cover - optional dependency
    from yookassa import Configuration, Payment
    from yookassa.domain.exceptions import ApiError, ResponseProcessingError
except ImportError:  # pragma: no cover - executed when SDK is unavailable
    Configuration = None  # type: ignore[assignment]
    Payment = None  # type: ignore[assignment]

    class ApiError(Exception):
        """Fallback error used when the SDK is not installed."""

    class ResponseProcessingError(Exception):
        """Fallback error used when the SDK is not installed."""


class YooKassaError(Exception):
    """Base exception for YooKassa integration errors."""


class YooKassaConfigurationError(YooKassaError):
    """Raised when the integration is misconfigured."""


class YooKassaPaymentError(YooKassaError):
    """Raised when a payment could not be created."""


@dataclass(slots=True)
class YooKassaPaymentResult:
    """Result of a payment creation request."""

    payment_id: str
    confirmation_url: str
    payload: dict[str, Any]
    idempotence_key: str


def _ensure_configured() -> None:
    """Ensure YooKassa credentials are available and configure the SDK."""

    if Configuration is None or Payment is None:
        raise YooKassaConfigurationError(
            "Пакет 'yookassa' не установлен. Установите его, чтобы создавать платежи."
        )
    if not settings.YOOKASSA_SHOP_ID or not settings.YOOKASSA_SECRET_KEY:
        raise YooKassaConfigurationError(
            "YooKassa credentials are not configured."
        )
    Configuration.configure(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY)


def _format_amount(amount: Decimal) -> str:
    quantized = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(quantized, "0.2f")


def create_payment(
    *,
    amount: Decimal,
    currency: str,
    return_url: str,
    description: str,
    metadata: dict[str, Any],
    idempotence_key: str | None = None,
    save_payment_method: bool = False,
) -> YooKassaPaymentResult:
    """Create a YooKassa payment and return the confirmation details."""

    _ensure_configured()
    key = idempotence_key or uuid.uuid4().hex

    payload: dict[str, Any] = {
        "amount": {"value": _format_amount(amount), "currency": currency},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": return_url,
        },
        "description": description[:128],
        "metadata": metadata,
        "save_payment_method": save_payment_method,
    }

    try:
        try:
            response = Payment.create(payload, idempotence_key=key)
        except TypeError as exc:
            if "idempotence_key" not in str(exc):
                raise
            response = Payment.create(payload, key)
    except (ApiError, ResponseProcessingError) as exc:  # pragma: no cover - network
        raise YooKassaPaymentError(str(exc)) from exc

    confirmation = getattr(response, "confirmation", None)
    confirmation_url = ""
    if confirmation is not None:
        confirmation_url = getattr(confirmation, "confirmation_url", "") or ""

    raw_payload = response.json()
    try:
        parsed_payload = json.loads(raw_payload)
    except (TypeError, json.JSONDecodeError):
        parsed_payload = {"raw": raw_payload}

    return YooKassaPaymentResult(
        payment_id=response.id,
        confirmation_url=confirmation_url,
        payload=parsed_payload,
        idempotence_key=key,
    )