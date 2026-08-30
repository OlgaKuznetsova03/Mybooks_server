from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
from django.db import DatabaseError
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token

from .models import MobileAuthToken

_MOBILE_TOKEN_SALT = "mobile-auth-fallback"
_MOBILE_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 30
_MOBILE_TOKEN_DEVICE_LIMIT = 3


def _trim_mobile_tokens(user) -> None:
    stale_keys = list(
        MobileAuthToken.objects.filter(user=user)
        .order_by("-created_at")
        .values_list("key", flat=True)[_MOBILE_TOKEN_DEVICE_LIMIT:]
    )
    if stale_keys:
        MobileAuthToken.objects.filter(key__in=stale_keys).delete()


def issue_mobile_token(user, *, rotate: bool = False) -> str:
    """Issue a mobile token and keep up to three active devices per user."""

    try:
        token = MobileAuthToken.objects.create(user=user, last_used_at=timezone.now())
        _trim_mobile_tokens(user)
        return token.key
    except DatabaseError:
        pass

    try:
        token, _ = Token.objects.get_or_create(user=user)
        return token.key
    except DatabaseError:
        payload = {"uid": user.pk}
        return signing.dumps(payload, salt=_MOBILE_TOKEN_SALT)


class MobileTokenAuthentication(TokenAuthentication):
    """Supports multi-device mobile tokens, DRF Token model and signed fallback tokens."""

    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except exceptions.AuthenticationFailed:
            if request.method in ("GET", "HEAD", "OPTIONS"):
                return None
            raise

    def authenticate_credentials(self, key):
        mobile_credentials = self._authenticate_mobile_token(key)
        if mobile_credentials is not None:
            return mobile_credentials

        try:
            return super().authenticate_credentials(key)
        except exceptions.AuthenticationFailed:
            user = self._authenticate_signed_token(key)
            if not user:
                raise
            return (user, key)

    def _authenticate_mobile_token(self, key):
        try:
            token = MobileAuthToken.objects.select_related("user").filter(key=key).first()
        except DatabaseError:
            return None

        if token is None:
            return None

        user = token.user
        if not user.is_active:
            raise exceptions.AuthenticationFailed("User inactive or deleted.")

        MobileAuthToken.objects.filter(key=token.key).update(last_used_at=timezone.now())
        return (user, token)

    def _authenticate_signed_token(self, key):
        try:
            payload = signing.loads(
                key,
                salt=_MOBILE_TOKEN_SALT,
                max_age=_MOBILE_TOKEN_MAX_AGE_SECONDS,
            )
        except (BadSignature, SignatureExpired):
            return None

        user_id = payload.get("uid")
        if not user_id:
            return None

        user_model = get_user_model()
        try:
            user = user_model.objects.get(pk=user_id)
        except user_model.DoesNotExist:
            return None
        if not user.is_active:
            return None
        return user