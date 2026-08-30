from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import CoinTransaction, PremiumSubscription, Profile
from accounts.services import (
    TRACKER_STORY_BACKGROUND_COST,
    TRACKER_STORY_GENERATION_COST,
)
from books.models import Book
from shelves.models import BookProgress


class TrackerStoryPaymentApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="story_reader",
            email="story-reader@example.com",
            password="StoryPass123!",
        )
        self.profile, _ = Profile.objects.get_or_create(user=self.user)
        Profile.objects.filter(pk=self.profile.pk).update(coins=100)
        self.profile.refresh_from_db()
        self.book = Book.objects.create(title="Книга для сторис")
        self.progress = BookProgress.objects.create(user=self.user, book=self.book)
        self.url = f"/api/v1/tracker/{self.progress.pk}/story-payment/"
        self.client.force_authenticate(self.user)

    def test_quote_returns_both_server_prices(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["generation"]["cost"], TRACKER_STORY_GENERATION_COST)
        self.assertEqual(response.data["background"]["cost"], TRACKER_STORY_BACKGROUND_COST)
        self.assertEqual(response.data["generation"]["coin_balance"], 100)

    def test_vk_app_route_uses_the_same_payment_contract(self):
        response = self.client.get(
            f"/api/v1/vk-app/tracker/{self.progress.pk}/story-payment/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["generation"]["cost"], 10)
        self.assertEqual(response.data["background"]["cost"], 5)

    def test_generate_and_background_use_shared_coin_balance(self):
        generated = self.client.post(
            self.url,
            {"action": "generate", "operation_id": "generation-1"},
            format="json",
        )
        changed = self.client.post(
            self.url,
            {"action": "change_background", "operation_id": "background-1"},
            format="json",
        )

        self.assertEqual(generated.status_code, status.HTTP_200_OK)
        self.assertEqual(generated.data["balance_after"], 90)
        self.assertEqual(changed.status_code, status.HTTP_200_OK)
        self.assertEqual(changed.data["balance_after"], 85)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.coins, 85)

    def test_repeated_operation_id_is_idempotent(self):
        payload = {"action": "generate", "operation_id": "same-generation"}

        first = self.client.post(self.url, payload, format="json")
        second = self.client.post(self.url, payload, format="json")

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertFalse(first.data["duplicate"])
        self.assertTrue(second.data["duplicate"])
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.coins, 90)
        self.assertEqual(
            CoinTransaction.objects.filter(
                profile=self.profile,
                transaction_type=CoinTransaction.Type.FEATURE_PURCHASE,
            ).count(),
            1,
        )

    def test_premium_user_gets_the_story_without_balance_deduction(self):
        PremiumSubscription.objects.create(
            user=self.user,
            start_at=timezone.now(),
            end_at=timezone.now() + timedelta(days=30),
        )

        response = self.client.post(
            self.url,
            {"action": "generate", "operation_id": "premium-generation"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["unlimited"])
        self.assertFalse(response.data["charged"])
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.coins, 100)

    def test_insufficient_balance_does_not_create_transaction(self):
        Profile.objects.filter(pk=self.profile.pk).update(coins=4)

        response = self.client.post(
            self.url,
            {"action": "change_background", "operation_id": "too-expensive"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_402_PAYMENT_REQUIRED)
        self.assertEqual(response.data["shortage"], 1)
        self.assertFalse(
            CoinTransaction.objects.filter(
                profile=self.profile,
                transaction_type=CoinTransaction.Type.FEATURE_PURCHASE,
            ).exists()
        )

    def test_other_users_tracker_is_not_available(self):
        other = get_user_model().objects.create_user(
            username="other_story_reader",
            password="StoryPass123!",
        )
        other_progress = BookProgress.objects.create(user=other, book=self.book)

        response = self.client.get(
            f"/api/v1/tracker/{other_progress.pk}/story-payment/"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
