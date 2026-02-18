from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class PublicApiTests(APITestCase):
    def test_health_endpoint_available(self):
        response = self.client.get(reverse("v1:health"), secure=True)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json().get("status"), "ok")

    def test_feature_map_is_served(self):
        response = self.client.get(reverse("v1:feature-map"), secure=True)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("books", data)
        self.assertIn("communities", data)

    def test_books_list_returns_empty_payload(self):
        response = self.client.get(
            reverse("v1:books-list"), {"page_size": 1}, secure=True
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertIn("results", payload)
        self.assertIsInstance(payload["results"], list)

    def test_stats_endpoint_is_accessible(self):
        response = self.client.get(reverse("v1:stats"), secure=True)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertIn("books_per_month", payload)
        self.assertIn("challenge_progress", payload)
        self.assertIn("calendar", payload)

    def test_reading_clubs_list_is_accessible(self):
        response = self.client.get(
            reverse("v1:reading-clubs"), {"page_size": 1}, secure=True
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertIn("results", payload)
        self.assertIsInstance(payload["results"], list)

    def test_marathons_list_is_accessible(self):
        response = self.client.get(
            reverse("v1:marathons"), {"page_size": 1}, secure=True
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertIn("results", payload)
        self.assertIsInstance(payload["results"], list)

class MobileAuthApiTests(APITestCase):
    def setUp(self):
        self.user_model = get_user_model()

    def test_mobile_login_accepts_existing_website_credentials(self):
        password = "StrongPass123!"
        self.user_model.objects.create_user(
            username="site_user",
            email="reader@example.com",
            password=password,
        )

        response = self.client.post(
            reverse("v1:auth-login"),
            {"login": "reader@example.com", "password": password},
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertIn("token", payload)
        self.assertEqual(payload["user"]["email"], "reader@example.com")


    def test_mobile_login_accepts_email_field_alias(self):
        password = "StrongPass123!"
        self.user_model.objects.create_user(
            username="alias_user",
            email="alias@example.com",
            password=password,
        )

        response = self.client.post(
            reverse("v1:auth-login"),
            {"email": "alias@example.com", "password": password},
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["user"]["email"], "alias@example.com")

    def test_mobile_login_accepts_username_field_alias(self):
        password = "StrongPass123!"
        self.user_model.objects.create_user(
            username="nickname_user",
            email="nick@example.com",
            password=password,
        )

        response = self.client.post(
            reverse("v1:auth-login"),
            {"username": "nickname_user", "password": password},
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["user"]["username"], "nickname_user")

    def test_mobile_login_requires_any_login_identifier(self):
        response = self.client.post(
            reverse("v1:auth-login"),
            {"password": "StrongPass123!"},
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("login", response.json())

    def test_mobile_signup_creates_account_and_allows_website_login(self):
        password = "StrongPass123!"
        signup_response = self.client.post(
            reverse("v1:auth-signup"),
            {
                "username": "app_user",
                "email": "app@example.com",
                "password": password,
            },
            format="json",
            secure=True,
        )

        self.assertEqual(signup_response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(self.user_model.objects.filter(email="app@example.com").exists())
        self.assertTrue(
            self.client.login(username="app@example.com", password=password)
        )