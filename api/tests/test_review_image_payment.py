from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import CoinTransaction, PremiumSubscription, Profile
from accounts.services import (
    REVIEW_IMAGE_BACKGROUND_COST,
    REVIEW_IMAGE_GENERATION_COST,
)
from books.models import Book, Rating
from shelves.models import BookProgress


class ReviewImagePaymentApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="review_reader",
            email="review-reader@example.com",
            password="ReviewPass123!",
        )
        self.profile, _ = Profile.objects.get_or_create(user=self.user)
        Profile.objects.filter(pk=self.profile.pk).update(coins=100)
        self.profile.refresh_from_db()
        self.book = Book.objects.create(title="Книга для отзыва")
        self.progress = BookProgress.objects.create(
            user=self.user,
            book=self.book,
            started_at=timezone.localdate() - timedelta(days=4),
            finished_at=timezone.localdate(),
        )
        self.rating = Rating.objects.create(
            user=self.user,
            book=self.book,
            score=9,
            plot_score=8,
            review="Подробный отзыв о прочитанной книге.",
        )
        self.url = f"/api/v1/reviews/{self.rating.pk}/image-payment/"
        self.client.force_authenticate(self.user)

    def test_quote_returns_prices_and_review_data(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["generation"]["cost"], REVIEW_IMAGE_GENERATION_COST)
        self.assertEqual(response.data["background"]["cost"], REVIEW_IMAGE_BACKGROUND_COST)
        self.assertEqual(response.data["review"]["score"], 9)
        self.assertEqual(response.data["review"]["reading_days"], 5)
        self.assertEqual(len(response.data["backgrounds"]), 2)
        self.assertTrue(all("/reviews/review" in url for url in response.data["backgrounds"]))

    def test_vk_app_route_uses_the_same_contract(self):
        response = self.client.get(
            f"/api/v1/vk-app/reviews/{self.rating.pk}/image-payment/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["generation"]["cost"], 50)
        self.assertEqual(response.data["background"]["cost"], 5)

    def test_generation_and_background_change_use_shared_balance(self):
        generated = self.client.post(
            self.url,
            {"action": "generate", "operation_id": "review-generation-1"},
            format="json",
        )
        changed = self.client.post(
            self.url,
            {
                "action": "change_background",
                "operation_id": "review-background-1",
                "page_index": 1,
                "current_background_index": generated.data["background_index"],
            },
            format="json",
        )

        self.assertEqual(generated.status_code, status.HTTP_200_OK)
        self.assertEqual(generated.data["balance_after"], 50)
        self.assertEqual(changed.status_code, status.HTTP_200_OK)
        self.assertEqual(changed.data["balance_after"], 45)
        self.assertEqual(changed.data["page_index"], 1)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.coins, 45)

    def test_repeated_operation_id_is_idempotent(self):
        payload = {"action": "generate", "operation_id": "same-review-generation"}

        first = self.client.post(self.url, payload, format="json")
        second = self.client.post(self.url, payload, format="json")

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertFalse(first.data["duplicate"])
        self.assertTrue(second.data["duplicate"])
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.coins, 50)
        self.assertEqual(
            CoinTransaction.objects.filter(
                profile=self.profile,
                transaction_type=CoinTransaction.Type.FEATURE_PURCHASE,
            ).count(),
            1,
        )

    def test_premium_user_is_not_charged(self):
        PremiumSubscription.objects.create(
            user=self.user,
            start_at=timezone.now(),
            end_at=timezone.now() + timedelta(days=30),
        )

        response = self.client.post(
            self.url,
            {"action": "generate", "operation_id": "premium-review-generation"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["unlimited"])
        self.assertFalse(response.data["charged"])
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.coins, 100)

    def test_another_users_review_is_not_available(self):
        other = get_user_model().objects.create_user(
            username="other_review_reader",
            password="ReviewPass123!",
        )
        other_rating = Rating.objects.create(
            user=other,
            book=self.book,
            score=7,
            review="Чужой отзыв",
        )

        response = self.client.get(
            f"/api/v1/reviews/{other_rating.pk}/image-payment/"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

