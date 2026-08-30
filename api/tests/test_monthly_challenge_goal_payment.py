from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import CoinTransaction, PremiumSubscription, Profile
from books.models import Book
from games.models import MonthlyChallenge


class MonthlyChallengeGoalPaymentTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="monthly-goal-payment-user",
            password="password",
        )
        self.profile, _created = Profile.objects.get_or_create(user=self.user)
        self.profile.coins = 100
        self.profile.save(update_fields=("coins",))
        self.client.force_authenticate(self.user)
        self.month = "2026-08-01"

    def post_goal(self, slug, payload):
        return self.client.post(
            f"/api/v1/vk-app/games/{slug}/",
            {"action": "monthly_save", "month": self.month, **payload},
            format="json",
        )

    def feature_purchases(self):
        return CoinTransaction.objects.filter(
            profile=self.profile,
            transaction_type=CoinTransaction.Type.FEATURE_PURCHASE,
        )

    def test_initial_goal_is_free_and_changed_goal_costs_fifty_coins(self):
        first = self.post_goal("monthly-mini-books", {"target_books": 2})
        changed = self.post_goal("monthly-mini-books", {"target_books": 3})
        self.profile.refresh_from_db()

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(changed.status_code, status.HTTP_200_OK)
        self.assertEqual(self.profile.coins, 50)
        self.assertEqual(self.feature_purchases().count(), 1)
        payment = changed.data["game"]["monthly_game"]["goal_edit_payment"]
        self.assertEqual(payment["cost"], 50)
        self.assertEqual(payment["coin_balance"], 50)

    def test_saving_same_goal_again_is_free(self):
        self.post_goal("monthly-mini-books", {"target_books": 2})
        self.post_goal("monthly-mini-books", {"target_books": 3})
        repeated = self.post_goal("monthly-mini-books", {"target_books": 3})
        self.profile.refresh_from_db()

        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertEqual(self.profile.coins, 50)
        self.assertEqual(self.feature_purchases().count(), 1)

    def test_insufficient_balance_keeps_goal_and_balance_unchanged(self):
        self.post_goal("monthly-mini-books", {"target_books": 2})
        self.profile.coins = 20
        self.profile.save(update_fields=("coins",))

        response = self.post_goal("monthly-mini-books", {"target_books": 4})
        self.profile.refresh_from_db()
        challenge = MonthlyChallenge.objects.get(user=self.user)

        self.assertEqual(response.status_code, status.HTTP_402_PAYMENT_REQUIRED)
        self.assertEqual(self.profile.coins, 20)
        self.assertEqual(challenge.target_books, 2)
        self.assertEqual(self.feature_purchases().count(), 0)

    def test_premium_user_changes_goal_without_deduction(self):
        PremiumSubscription.objects.create(
            user=self.user,
            start_at=timezone.now(),
            end_at=timezone.now() + timedelta(days=30),
        )
        self.post_goal("monthly-mini-books", {"target_books": 2})
        response = self.post_goal("monthly-mini-books", {"target_books": 4})
        self.profile.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.profile.coins, 100)
        payment = response.data["game"]["monthly_game"]["goal_edit_payment"]
        self.assertTrue(payment["has_unlimited_coins"])

    def test_book_list_charges_once_when_saved_list_changes(self):
        first_book = Book.objects.create(title="First book")
        second_book = Book.objects.create(title="Second book")
        third_book = Book.objects.create(title="Third book")

        initial = self.post_goal(
            "monthly-book-list",
            {"book_ids": [first_book.id, second_book.id]},
        )
        changed = self.post_goal(
            "monthly-book-list",
            {"book_ids": [first_book.id, third_book.id]},
        )
        self.profile.refresh_from_db()

        self.assertEqual(initial.status_code, status.HTTP_200_OK)
        self.assertEqual(changed.status_code, status.HTTP_200_OK)
        self.assertEqual(self.profile.coins, 50)
        self.assertEqual(self.feature_purchases().count(), 1)

    def test_pages_minutes_goal_change_costs_fifty_coins(self):
        initial = self.post_goal(
            "monthly-pages-minutes",
            {"target_pages": 500, "target_minutes": 0},
        )
        changed = self.post_goal(
            "monthly-pages-minutes",
            {"target_pages": 700, "target_minutes": 600},
        )
        self.profile.refresh_from_db()

        self.assertEqual(initial.status_code, status.HTTP_200_OK)
        self.assertEqual(changed.status_code, status.HTTP_200_OK)
        self.assertEqual(self.profile.coins, 50)
        self.assertEqual(self.feature_purchases().count(), 1)
