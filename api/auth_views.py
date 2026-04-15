from __future__ import annotations

from django.conf import settings
from django.contrib.auth import login, logout
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.forms import EmailAuthenticationForm, SignUpForm

from .authentication import issue_mobile_token


def _user_payload(user) -> dict[str, object]:
    try:
        profile = user.profile
    except ObjectDoesNotExist:
        profile = None

    avatar = None
    if profile and getattr(profile, "avatar", None):
        try:
            avatar = profile.avatar.url
        except Exception:
            avatar = None

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "roles": list(
            user.groups.filter(name__in=["reader", "author", "blogger"]).values_list(
                "name", flat=True
            )
        ),
        "avatar": avatar,
    }


def _normalize_form_errors(form) -> dict[str, list[str]]:
    return {
        field: [str(error) for error in errors]
        for field, errors in form.errors.get_json_data(escape_html=False).items()
    }


class AuthRegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        payload = request.data.copy()
        roles = payload.get("roles")
        if roles is None:
            payload["roles"] = []

        form = SignUpForm(payload)
        if not form.is_valid():
            return Response({"success": False, "errors": _normalize_form_errors(form)}, status=400)

        user = form.save()
        backend = (
            settings.AUTHENTICATION_BACKENDS[0]
            if settings.AUTHENTICATION_BACKENDS
            else "django.contrib.auth.backends.ModelBackend"
        )
        login(request, user, backend=backend)
        token = issue_mobile_token(user)

        return Response(
            {
                "success": True,
                "token": token,
                "user": _user_payload(user),
            },
            status=status.HTTP_201_CREATED,
        )


class AuthLoginView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        email = str(request.data.get("email", "")).strip()
        password = request.data.get("password", "")

        form = EmailAuthenticationForm(
            request=request,
            data={"username": email, "password": password},
        )
        if not form.is_valid():
            return Response({"success": False, "errors": _normalize_form_errors(form)}, status=400)

        user = form.get_user()
        login(request, user)
        token = issue_mobile_token(user, rotate=True)

        return Response(
            {
                "success": True,
                "token": token,
                "user": _user_payload(user),
            }
        )


class AuthMeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return Response(_user_payload(request.user))


class AuthLogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        auth_obj = getattr(request, "auth", None)
        if isinstance(auth_obj, Token):
            auth_obj.delete()

        logout(request)
        return Response({"success": True})