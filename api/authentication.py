from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
from django.db import DatabaseError
from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token

_MOBILE_TOKEN_SALT = "mobile-auth-fallback"
_MOBILE_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 30


def issue_mobile_token(user) -> str:
    """Return DB token when available, otherwise signed fallback token."""

    try:
        token, _ = Token.objects.get_or_create(user=user)
        return token.key
    except DatabaseError:
        payload = {"uid": user.pk}
        return signing.dumps(payload, salt=_MOBILE_TOKEN_SALT)


class MobileTokenAuthentication(TokenAuthentication):
    """Supports DRF Token model and a signed fallback token for degraded DB states."""

    def authenticate_credentials(self, key):
        try:
            return super().authenticate_credentials(key)
        except exceptions.AuthenticationFailed:
            user = self._authenticate_signed_token(key)
            if not user:
                raise
            return (user, key)

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