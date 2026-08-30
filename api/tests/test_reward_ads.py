from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import CoinTransaction, Profile, RewardAdTicket, YANDEX_AD_REWARD_COINS


@override_settings(
    YANDEX_REWARDED_AD_UNIT_ID="demo-yandex-unit",
    REWARD_AD_DAILY_LIMIT=10,
    REWARD_AD_COOLDOWN_SECONDS=60,
    REWARD_AD_MIN_VIEW_SECONDS=5,
    REWARD_AD_TICKET_TTL_SECONDS=900,
)
class RewardAdTicketApiTests(APITestCase):
    start_url = "/api/v1/vk-app/reward-ads/start/"
    claim_url = "/api/v1/vk-app/reward-ads/claim/"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="reward_ticket_user",
            email="reward-ticket@example.com",
            password="RewardPass123!",
        )
        self.profile, _ = Profile.objects.get_or_create(user=self.user)
        self.initial_balance = self.profile.coins
        self.client.force_authenticate(self.user)

    def _start(self, provider="yandex"):
        return self.client.post(self.start_url, {"provider": provider}, format="json")

    def test_start_credits_shared_coin_balance_and_closes_ticket(self):
        response = self._start(provider="vk")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["reward_amount"], YANDEX_AD_REWARD_COINS)
        self.assertEqual(response.data["coins_awarded"], YANDEX_AD_REWARD_COINS)
        self.assertEqual(response.data["balance_before"], self.initial_balance)
        self.assertEqual(
            response.data["balance_after"],
            self.initial_balance + YANDEX_AD_REWARD_COINS,
        )
        self.assertEqual(response.data["daily_remaining"], 9)
        self.assertIsNotNone(response.data["transaction_id"])

        ticket = RewardAdTicket.objects.get(
            profile=self.profile,
            token=response.data["ticket"],
        )
        self.assertIsNotNone(ticket.claimed_at)
        self.assertEqual(ticket.transaction_id, response.data["transaction_id"])

        self.profile.refresh_from_db()
        self.assertEqual(
            self.profile.coins,
            self.initial_balance + YANDEX_AD_REWARD_COINS,
        )

    def test_claim_endpoint_is_idempotent_for_immediately_credited_ticket(self):
        start = self._start(provider="vk")

        first = self.client.post(
            self.claim_url,
            {"ticket": start.data["ticket"]},
            format="json",
        )
        second = self.client.post(
            self.claim_url,
            {"ticket": start.data["ticket"]},
            format="json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(first.data["already_claimed"])
        self.assertTrue(second.data["already_claimed"])
        self.assertEqual(first.data["coins_awarded"], 0)
        self.assertEqual(second.data["coins_awarded"], 0)
        self.assertEqual(first.data["transaction_id"], start.data["transaction_id"])
        self.assertEqual(second.data["transaction_id"], start.data["transaction_id"])
        self.assertEqual(
            CoinTransaction.objects.filter(
                profile=self.profile,
                transaction_type=CoinTransaction.Type.AD_REWARD,
            ).count(),
            1,
        )

    def test_replayed_claim_returns_current_shared_balance(self):
        start = self._start(provider="vk")
        self.profile.refresh_from_db()
        self.profile.credit_coins(
            10,
            transaction_type=CoinTransaction.Type.DAILY_LOGIN,
            description="Daily reward after ad reward",
        )
        self.profile.refresh_from_db()

        replay = self.client.post(
            self.claim_url,
            {"ticket": start.data["ticket"]},
            format="json",
        )

        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.data["already_claimed"])
        self.assertEqual(replay.data["coins_awarded"], 0)
        self.assertEqual(replay.data["balance_after"], self.profile.coins)
        self.assertEqual(replay.data["balance_before"], self.profile.coins)

    def test_vk_reward_uses_the_same_profile_coin_balance(self):
        response = self._start(provider="vk")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["coins_awarded"], YANDEX_AD_REWARD_COINS)
        self.profile.refresh_from_db()
        self.assertEqual(
            self.profile.coins,
            self.initial_balance + YANDEX_AD_REWARD_COINS,
        )

    def test_yandex_reward_keeps_completion_claim_flow_for_android(self):
        start = self._start(provider="yandex")

        self.assertEqual(start.status_code, 201)
        self.assertNotIn("coins_awarded", start.data)
        ticket = RewardAdTicket.objects.get(token=start.data["ticket"])
        self.assertIsNone(ticket.claimed_at)
        self.assertIsNone(ticket.transaction_id)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.coins, self.initial_balance)

        RewardAdTicket.objects.filter(pk=ticket.pk).update(
            not_before=timezone.now() - timedelta(seconds=1)
        )
        claim = self.client.post(
            self.claim_url,
            {"ticket": start.data["ticket"]},
            format="json",
        )

        self.assertEqual(claim.status_code, 200)
        self.assertEqual(claim.data["coins_awarded"], YANDEX_AD_REWARD_COINS)
        self.profile.refresh_from_db()
        self.assertEqual(
            self.profile.coins,
            self.initial_balance + YANDEX_AD_REWARD_COINS,
        )

    def test_legacy_claimed_ticket_without_transaction_is_recovered_once(self):
        now = timezone.now()
        ticket = RewardAdTicket.objects.create(
            profile=self.profile,
            provider=RewardAdTicket.Provider.VK,
            not_before=now - timedelta(seconds=10),
            expires_at=now + timedelta(minutes=10),
            claimed_at=now,
        )

        first = self.client.post(
            self.claim_url,
            {"ticket": str(ticket.token)},
            format="json",
        )
        second = self.client.post(
            self.claim_url,
            {"ticket": str(ticket.token)},
            format="json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.data["recovered"])
        self.assertEqual(first.data["coins_awarded"], YANDEX_AD_REWARD_COINS)
        self.assertEqual(second.data["coins_awarded"], 0)
        self.assertEqual(first.data["transaction_id"], second.data["transaction_id"])
        self.profile.refresh_from_db()
        self.assertEqual(
            self.profile.coins,
            self.initial_balance + YANDEX_AD_REWARD_COINS,
        )

    def test_start_respects_cooldown_after_immediate_reward(self):
        first = self._start(provider="vk")
        self.assertEqual(first.status_code, 201)

        response = self._start(provider="vk")

        self.assertEqual(response.status_code, 429)
        self.assertGreater(response.data["retry_after"], 0)

    def test_daily_limit_blocks_eleventh_reward(self):
        now = timezone.now()
        RewardAdTicket.objects.bulk_create(
            [
                RewardAdTicket(
                    profile=self.profile,
                    provider=RewardAdTicket.Provider.YANDEX,
                    ad_unit_id="demo-yandex-unit",
                    not_before=now - timedelta(minutes=2),
                    expires_at=now + timedelta(minutes=2),
                    claimed_at=now - timedelta(minutes=index + 1),
                )
                for index in range(10)
            ]
        )

        response = self._start()

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["daily_remaining"], 0)

    def test_start_expires_previous_pending_legacy_ticket(self):
        now = timezone.now()
        pending = RewardAdTicket.objects.create(
            profile=self.profile,
            provider=RewardAdTicket.Provider.VK,
            not_before=now - timedelta(minutes=2),
            expires_at=now + timedelta(minutes=10),
        )

        response = self._start(provider="vk")

        self.assertEqual(response.status_code, 201)
        pending.refresh_from_db()
        self.assertLessEqual(pending.expires_at, timezone.now())
