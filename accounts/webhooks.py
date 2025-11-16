"""Webhook entry points for external providers."""
from django.http import HttpRequest, HttpResponse
from .views import yookassa_webhook as _views_yookassa_webhook

def yookassa_webhook(request: HttpRequest) -> HttpResponse:
    """Proxy YooKassa webhook requests to the main handler in ``views``."""
    return _views_yookassa_webhook(request)