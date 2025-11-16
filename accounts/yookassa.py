"""YooKassa payment integration."""

from __future__ import annotations

import json
import uuid
from base64 import b64encode
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable
from urllib import request as urllib_request

from django.conf import settings

try:  # pragma: no cover - sdk import is optional in tests
    from yookassa import Configuration, Payment  # type: ignore
except Exception:  # pragma: no cover - fall back to HTTP client
    Configuration = None
    Payment = None


@dataclass(frozen=True)
class YooKassaPaymentResult:
    payment_id: str
    confirmation_url: str
    payload: dict
    idempotence_key: str


def _format_amount(amount: Decimal | float | int) -> str:
    return f"{Decimal(str(amount)).quantize(Decimal('0.01'))}"


def _build_receipt(
    *,
    description: str,
    amount: str,
    currency: str,
    customer_email: str | None,
    customer_phone: str | None = None,
    items: Iterable[dict] | None = None,
) -> dict | None:
    """Construct a receipt block if contact details are provided."""

    customer = {}
    if customer_email:
        customer["email"] = customer_email
    if customer_phone:
        customer["phone"] = customer_phone

    if not customer:
        return None

    if items:
        receipt_items = list(items)
    else:
        receipt_items = [
            {
                "description": description[:128],
                "quantity": "1.0",
                "amount": {"value": amount, "currency": currency},
                "vat_code": 1,  # Без НДС
                "payment_subject": "service",
                "payment_mode": "full_payment",
            }
        ]

    receipt: dict = {"customer": customer, "items": receipt_items}

    tax_system_code = getattr(settings, "YOOKASSA_TAX_SYSTEM_CODE", None)
    if tax_system_code:
        receipt["tax_system_code"] = tax_system_code

    return receipt


def _build_payload(
    *,
    amount: Decimal | float | int,
    currency: str,
    return_url: str,
    description: str,
    metadata: dict | None,
    receipt: dict | None,
) -> dict:
    formatted_amount = _format_amount(amount)
    payload = {
        "amount": {"value": formatted_amount, "currency": currency},
        "confirmation": {"type": "redirect", "return_url": return_url},
        "capture": True,
        "description": description[:128],
    }

    if metadata:
        payload["metadata"] = metadata
    if receipt:
        payload["receipt"] = receipt

    return payload


def create_payment(
    *,
    amount: Decimal | float | int,
    currency: str = "RUB",
    return_url: str,
    description: str,
    metadata: dict | None = None,
    idempotence_key: str | None = None,
    customer_email: str | None = None,
    customer_phone: str | None = None,
    receipt_items: Iterable[dict] | None = None,
) -> YooKassaPaymentResult:
    """Create a YooKassa payment with mandatory receipt details."""

    idem_key = idempotence_key or str(uuid.uuid4())
    receipt = _build_receipt(
        description=description,
        amount=_format_amount(amount),
        currency=currency,
        customer_email=customer_email,
        customer_phone=customer_phone,
        items=receipt_items,
    )
    payload = _build_payload(
        amount=amount,
        currency=currency,
        return_url=return_url,
        description=description,
        metadata=metadata,
        receipt=receipt,
    )

    if Configuration and Payment:
        Configuration.account_id = settings.YOOKASSA_SHOP_ID
        Configuration.secret_key = settings.YOOKASSA_SECRET_KEY
        payment = Payment.create(payload, idem_key)
        try:
            payload_data = payment.to_dict()
        except AttributeError:  # pragma: no cover - fallback for older SDKs
            raw_json = payment.json()
            payload_data = raw_json if isinstance(raw_json, dict) else json.loads(raw_json)
        return YooKassaPaymentResult(
            payment_id=payment.id,
            confirmation_url=payment.confirmation.confirmation_url,
            payload=payload_data,
            idempotence_key=idem_key,
        )

    # Fallback to direct HTTP request when SDK is unavailable.
    request = urllib_request.Request(
        "https://api.yookassa.ru/v3/payments",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )
    credentials = f"{settings.YOOKASSA_SHOP_ID}:{settings.YOOKASSA_SECRET_KEY}".encode(
        "utf-8"
    )
    request.add_header("Content-Type", "application/json")
    request.add_header("Idempotence-key", idem_key)
    request.add_header("Authorization", f"Basic {b64encode(credentials).decode()}")

    with urllib_request.urlopen(request) as response:  # pragma: no cover - network
        payload = json.loads(response.read().decode("utf-8"))

    return YooKassaPaymentResult(
        payment_id=payload["id"],
        confirmation_url=payload["confirmation"]["confirmation_url"],
        payload=payload,
        idempotence_key=idem_key,
    )
