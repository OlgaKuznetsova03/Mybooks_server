from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from books.models import Book
from shelves.models import BookProgress, BookProgressMedium
from shelves.services import move_book_to_reading_shelf


class TrackerProgressFreshnessApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="progress_reader",
            email="progress_reader@example.com",
            password="StrongPass123!",
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

        self.book = Book.objects.create(title="Последовательный прогресс")
        move_book_to_reading_shelf(self.user, self.book)
        self.progress = BookProgress.objects.create(
            user=self.user,
            book=self.book,
            custom_total_pages=300,
        )
        BookProgressMedium.objects.create(
            progress=self.progress,
            medium=self.progress.FORMAT_PAPER,
            current_page=0,
            total_pages_override=300,
        )
        self.tracker_url = f"/api/v1/vk-app/tracker/{self.progress.pk}/"

    def _assert_home_and_feed_progress(self, expected_page):
        home_response = self.client.get("/api/v1/home/", secure=True)
        self.assertEqual(home_response.status_code, status.HTTP_200_OK)
        home_payload = home_response.json()
        reading_item = next(
            item
            for item in home_payload["reading_items"]
            if item["book"]["id"] == self.book.pk
        )
        self.assertEqual(reading_item["progress_current_page"], expected_page)
        home_update = next(
            item
            for item in home_payload["reading_updates"]
            if item["progress_id"] == self.progress.pk
        )
        self.assertEqual(home_update["current_page"], expected_page)
        self.assertEqual(home_update["total_pages"], 300)

        feed_response = self.client.get(
            "/api/v1/vk/progress-feed/?limit=15",
            secure=True,
        )
        self.assertEqual(feed_response.status_code, status.HTTP_200_OK)
        feed_item = next(
            item
            for item in feed_response.json()["reading_updates"]
            if item["id"] == self.progress.pk
        )
        self.assertEqual(feed_item["current_page"], expected_page)

    def test_sequential_updates_are_immediately_current_everywhere(self):
        for page in (101, 110, 125):
            with self.subTest(page=page):
                update_response = self.client.post(
                    self.tracker_url,
                    {
                        "action": "set_page",
                        "medium": self.progress.FORMAT_PAPER,
                        "page": page,
                        "is_public": True,
                    },
                    format="json",
                    secure=True,
                )

                self.assertEqual(update_response.status_code, status.HTTP_200_OK)
                self.assertEqual(update_response.json()["current_page"], page)

                self.progress.refresh_from_db()
                self.assertEqual(self.progress.current_page, page)
                self._assert_home_and_feed_progress(page)
