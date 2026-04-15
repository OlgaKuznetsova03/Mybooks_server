from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from unittest.mock import patch

from api.models import VKAccount


class VKConnectViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="user1",
            email="user1@example.com",
            password="StrongPass123!",
        )
        self.other_user = user_model.objects.create_user(
            username="user2",
            email="user2@example.com",
            password="StrongPass123!",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = "/api/v1/vk/connect/"

    def test_connect_relinks_vk_id_from_other_user(self):
        VKAccount.objects.create(user=self.other_user, vk_user_id=123456)

        response = self.client.post(self.url, {"vk_user_id": 123456}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(VKAccount.objects.filter(vk_user_id=123456, user=self.user).count(), 1)
        self.assertFalse(VKAccount.objects.filter(user=self.other_user).exists())

    def test_connect_updates_existing_user_vk_account(self):
        VKAccount.objects.create(user=self.user, vk_user_id=555111)

        response = self.client.post(
            self.url,
            {
                "vk_user_id": 555222,
                "first_name": "Ivan",
                "last_name": "Petrov",
                "photo_100": "https://example.com/photo.jpg",
                "screen_name": "ivanpetrov",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        account = VKAccount.objects.get(user=self.user)
        self.assertEqual(account.vk_user_id, 555222)
        self.assertEqual(account.first_name, "Ivan")
        self.assertEqual(account.screen_name, "ivanpetrov")

    def test_connect_replaces_current_user_old_vk_link_when_relinking(self):
        VKAccount.objects.create(user=self.user, vk_user_id=111111)
        VKAccount.objects.create(user=self.other_user, vk_user_id=222222)

        response = self.client.post(self.url, {"vk_user_id": 222222}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(VKAccount.objects.filter(user=self.user).count(), 1)
        self.assertEqual(VKAccount.objects.get(user=self.user).vk_user_id, 222222)
        self.assertFalse(VKAccount.objects.filter(vk_user_id=111111).exists())

class VKLoginViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/v1/vk/login/"

    def test_login_rejects_vk_user_id_outside_bigint_range(self):
        response = self.client.post(
            self.url,
            {"vk_user_id": "9223372036854775808"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["error"], "vk_user_id out of range")

    def test_login_rejects_non_positive_vk_user_id(self):
        response = self.client.post(
            self.url,
            {"vk_user_id": 0},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["error"], "vk_user_id out of range")

    def test_login_succeeds_even_if_last_login_update_fails(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="vklogin",
            email="vklogin@example.com",
            password="StrongPass123!",
        )
        VKAccount.objects.create(user=user, vk_user_id=7654321)

        with patch.object(user_model, "save", side_effect=DatabaseError):
            response = self.client.post(
                self.url,
                {"vk_user_id": 7654321},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("token", response.json())


class VKAppLoginViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/v1/vk-app/auth/login/"

    def test_login_returns_503_when_user_lookup_fails(self):
        with patch("api.vk_app_views.get_user_model") as mocked_get_user_model:
            user_model = mocked_get_user_model.return_value
            user_model.objects.filter.side_effect = DatabaseError

            response = self.client.post(
                self.url,
                {"email": "broken@example.com", "password": "StrongPass123!"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)