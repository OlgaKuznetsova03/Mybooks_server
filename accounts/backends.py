import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

logger = logging.getLogger(__name__)


class EmailBackend(ModelBackend):
    """Authenticate a user by email address (case insensitive)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None

        candidates = list(UserModel.objects.filter(email__iexact=username).order_by("id"))
        if not candidates:
            candidates = list(
                UserModel.objects.filter(username__iexact=username).order_by("id")
            )

        for user in candidates:
            try:
                password_matches = user.check_password(password)
            except (TypeError, ValueError):
                logger.warning(
                    "Skipping user id=%s during email auth: invalid password hash format",
                    getattr(user, "id", None),
                    exc_info=True,
                )
                continue
            if password_matches and self.user_can_authenticate(user):
                return user
        return None