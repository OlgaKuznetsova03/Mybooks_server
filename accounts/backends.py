from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


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
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        return None