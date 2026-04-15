from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient


class AuthLoginViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="reader1",
            email="reader1@example.com",
            password="StrongPass123!",
        )
        self.client = APIClient()
        self.url = "/api/v1/auth/login/"

    def test_login_returns_token_if_session_write_fails(self):
        with patch("api.auth_views.login", side_effect=DatabaseError):
            response = self.client.post(
                self.url,
                {"email": self.user.email, "password": "StrongPass123!"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()["success"])
        self.assertIn("token", response.json())

    def test_login_returns_503_if_auth_database_is_unavailable(self):
        with patch("accounts.forms.User.objects.filter", side_effect=DatabaseError):
            response = self.client.post(
                self.url,
                {"email": self.user.email, "password": "StrongPass123!"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(response.json()["success"])