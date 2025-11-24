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