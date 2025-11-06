import json
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.auth.models import Group
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from datetime import timedelta

from django.utils import timezone

from accounts.forms import SignUpForm
from accounts.models import (
    DAILY_LOGIN_REWARD_COINS,
    WELCOME_BONUS_COINS,
    CoinTransaction,
    PremiumSubscription,
    Profile,
    YANDEX_AD_REWARD_COINS,
)
from books.models import Author, Book
from shelves.models import BookProgress, Shelf, ShelfItem, ReadingLog
from shelves.services import DEFAULT_READ_SHELF

from accounts.views import _collect_profile_stats


@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
)
class SignUpPageTests(TestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = "localhost"
        self.client.defaults["wsgi.url_scheme"] = "https"
        self.client.defaults["HTTP_X_FORWARDED_PROTO"] = "https"

    def test_signup_page_renders(self):
        response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Создать аккаунт")
        self.assertContains(
            response,
            "Пароль должен состоять минимум из 8 символов, хотя бы одну букву и один символ.",
        )

    def test_signup_creates_user(self):
        payload = {
            "username": "newbie",
            "email": "newbie@example.com",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        }

        response = self.client.post(reverse("signup"), payload, follow=True)

        self.assertRedirects(response, reverse("book_list"))
        user = get_user_model().objects.get(username="newbie")
        self.assertEqual(user.email, "newbie@example.com")
        self.assertTrue(response.context["user"].is_authenticated)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
)
class PasswordResetFlowTests(TestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = "localhost"
        self.client.defaults["wsgi.url_scheme"] = "https"
        self.client.defaults["HTTP_X_FORWARDED_PROTO"] = "https"
        self.user = get_user_model().objects.create_user(
            username="reader",
            email="reader@example.com",
            password="OldPass123!",
        )

    def test_password_reset_page_renders(self):
        response = self.client.get(reverse("password_reset"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/password_reset_form.html")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_sends_email(self):
        response = self.client.post(
            reverse("password_reset"), {"email": self.user.email}
        )
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertIn("Сброс пароля", message.subject)
        self.assertIn(self.user.email, message.to)

    def test_password_reset_confirm_allows_setting_new_password(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        url = reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token})

        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "accounts/password_reset_confirm.html"
        )
        # Django redirects to a "set-password" URL once the token is validated.
        redirect_chain = response.redirect_chain
        if redirect_chain:
            self.assertTrue(
                any(chain_url.endswith("/set-password/") for chain_url, _ in redirect_chain),
                msg=f"Redirect chain did not include set-password URL: {redirect_chain}",
            )

        post_url = response.request.get("PATH_INFO", url)
        new_password = "NewPass123!"
        response = self.client.post(
            post_url,
            {
                "new_password1": new_password,
                "new_password2": new_password,
            },
        )
        self.assertRedirects(response, reverse("password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))


@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
)
class AuthorProfileBooksTests(TestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = "localhost"
        self.client.defaults["wsgi.url_scheme"] = "https"
        self.client.defaults["HTTP_X_FORWARDED_PROTO"] = "https"
        self.password = "AuthorPass123!"
        self.user = get_user_model().objects.create_user(
            username="author",
            email="author@example.com",
            password=self.password,
        )
        author_group, _ = Group.objects.get_or_create(name="author")
        self.user.groups.add(author_group)

        self.book = Book.objects.create(title="Авторская коллекция")
        self.book.contributors.add(self.user)
        self.author_entry = Author.objects.create(name="Автор Тестовый")
        self.book.authors.add(self.author_entry)

    def test_profile_books_tab_shows_contributed_books(self):
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(
            reverse("profile", kwargs={"username": self.user.username}),
            {"tab": "books"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.book, response.context["author_books"])
        self.assertContains(response, "Авторская коллекция")
        self.assertContains(response, "Автор Тестовый")
        self.assertContains(response, "Добавить книгу")


class SignUpRoleAssignmentTests(TestCase):
    def test_signup_assigns_selected_roles(self):
        form = SignUpForm(
            data={
                "username": "multiuser",
                "email": "multi@example.com",
                "password1": "ComplexPass123!",
                "password2": "ComplexPass123!",
                "roles": ["reader", "author", "blogger"],
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertSetEqual(
            set(user.groups.values_list("name", flat=True)),
            {"reader", "author", "blogger"},
        )

    def test_roles_preserved_when_saving_without_commit(self):
        form = SignUpForm(
            data={
                "username": "pendinguser",
                "email": "pending@example.com",
                "password1": "ComplexPass123!",
                "password2": "ComplexPass123!",
                "roles": ["reader", "author"],
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save(commit=False)
        user.save()
        form.save_m2m()
        self.assertSetEqual(
            set(user.groups.values_list("name", flat=True)),
            {"reader", "author"},
        )


class ProfileStatsAggregationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="statsuser",
            email="stats@example.com",
            password="StatsPass123!",
        )
        self.read_shelf = Shelf.objects.create(
            user=self.user,
            name=DEFAULT_READ_SHELF,
            is_default=True,
        )

    def test_pages_total_uses_tracked_logs(self):
        book = Book.objects.create(title="Журнал чтения")
        ShelfItem.objects.create(shelf=self.read_shelf, book=book)
        progress = BookProgress.objects.create(
            user=self.user,
            book=book,
            format=BookProgress.FORMAT_PAPER,
        )
        ReadingLog.objects.create(
            progress=progress,
            log_date=timezone.localdate(),
            medium=BookProgress.FORMAT_PAPER,
            pages_equivalent=Decimal("120.50"),
        )

        payload = _collect_profile_stats(self.user, {})
        stats = payload["stats"]

        expected_average = (
            Decimal("120.50") / Decimal("7")
        ).quantize(Decimal("0.01"))

        self.assertEqual(stats["pages_total"], 120.5)
        self.assertEqual(stats["pages_average"], float(expected_average))

    def test_audio_totals_fall_back_to_tracked_seconds(self):
        book = Book.objects.create(title="Аудио статистика")
        ShelfItem.objects.create(shelf=self.read_shelf, book=book)
        progress = BookProgress.objects.create(
            user=self.user,
            book=book,
            format=BookProgress.FORMAT_AUDIO,
        )
        ReadingLog.objects.create(
            progress=progress,
            log_date=timezone.localdate(),
            medium=BookProgress.FORMAT_AUDIO,
            pages_equivalent=Decimal("0"),
            audio_seconds=5400,
        )

        payload = _collect_profile_stats(self.user, {})
        stats = payload["stats"]

        self.assertEqual(stats["audio_tracked_display"], "01:30:00")
        self.assertEqual(stats["audio_total_display"], "01:30:00")
        self.assertEqual(stats["audio_adjusted_display"], "01:30:00")


class CoinEconomyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="coins_user",
            email="coins@example.com",
            password="CoinsPass123!",
        )
        self.profile = self.user.profile
        self.initial_balance = self.profile.coins

    def test_credit_coins_records_transaction(self):
        tx = self.profile.credit_coins(
            15,
            transaction_type=CoinTransaction.Type.ADMIN_ADJUSTMENT,
            description="Начисление",
        )

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.coins, self.initial_balance + 15)
        self.assertEqual(tx.balance_after, self.initial_balance + 15)
        self.assertEqual(tx.change, 15)
        self.assertFalse(tx.unlimited)

    def test_spend_coins_decreases_balance(self):
        self.profile.credit_coins(
            20,
            transaction_type=CoinTransaction.Type.ADMIN_ADJUSTMENT,
        )

        tx = self.profile.spend_coins(
            5,
            transaction_type=CoinTransaction.Type.FEATURE_PURCHASE,
            description="Трата",
        )

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.coins, self.initial_balance + 15)
        self.assertEqual(tx.change, -5)
        self.assertEqual(tx.balance_after, self.initial_balance + 15)

    def test_spend_coins_raises_when_insufficient(self):
        Profile.objects.filter(pk=self.profile.pk).update(coins=0)
        self.profile.refresh_from_db()
        with self.assertRaisesMessage(ValueError, "Недостаточно монет"):
            self.profile.spend_coins(
                1,
                transaction_type=CoinTransaction.Type.FEATURE_PURCHASE,
            )

    def test_premium_users_have_unlimited_coins(self):
        now = timezone.now()
        PremiumSubscription.objects.create(
            user=self.user,
            start_at=now - timedelta(days=1),
            end_at=now + timedelta(days=30),
            source=PremiumSubscription.Source.ADMIN,
        )

        tx = self.profile.spend_coins(
            999,
            transaction_type=CoinTransaction.Type.FEATURE_PURCHASE,
            description="Премиум трата",
        )

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.coins, self.initial_balance)
        self.assertTrue(tx.unlimited)
        self.assertIsNone(tx.balance_after)

    def test_reward_ad_view_credits_coins(self):
        tx = self.profile.reward_ad_view(YANDEX_AD_REWARD_COINS)

        self.profile.refresh_from_db()
        self.assertEqual(
            self.profile.coins,
            self.initial_balance + YANDEX_AD_REWARD_COINS,
        )
        self.assertEqual(tx.transaction_type, CoinTransaction.Type.AD_REWARD)
        self.assertGreater(len(tx.description), 0)

    def test_new_user_receives_welcome_bonus(self):
        self.assertEqual(self.initial_balance, WELCOME_BONUS_COINS)
        signup_tx = self.profile.coin_transactions.filter(
            transaction_type=CoinTransaction.Type.SIGNUP_BONUS
        ).first()
        self.assertIsNotNone(signup_tx)
        self.assertEqual(signup_tx.change, WELCOME_BONUS_COINS)
        self.assertEqual(signup_tx.balance_after, WELCOME_BONUS_COINS)

    def test_daily_login_reward_granted_once_per_day(self):
        tx = self.profile.grant_daily_login_reward()
        self.assertIsNotNone(tx)
        self.profile.refresh_from_db()
        self.assertEqual(
            self.profile.coins,
            self.initial_balance + DAILY_LOGIN_REWARD_COINS,
        )
        self.assertEqual(self.profile.last_daily_reward_at, timezone.localdate())

        second_attempt = self.profile.grant_daily_login_reward()
        self.assertIsNone(second_attempt)
        self.profile.refresh_from_db()
        self.assertEqual(
            self.profile.coins,
            self.initial_balance + DAILY_LOGIN_REWARD_COINS,
        )


@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
)
class DailyLoginRewardMiddlewareTests(TestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = "localhost"
        self.client.defaults["wsgi.url_scheme"] = "https"
        self.client.defaults["HTTP_X_FORWARDED_PROTO"] = "https"

        self.user = get_user_model().objects.create_user(
            username="daily_user",
            email="daily@example.com",
            password="DailyPass123!",
        )
        self.profile = self.user.profile
        Profile.objects.filter(pk=self.profile.pk).update(
            coins=0,
            last_daily_reward_at=None,
        )
        self.profile.refresh_from_db()

    def test_daily_reward_granted_on_first_request(self):
        self.client.force_login(self.user)

        first_response = self.client.get(reverse("my_profile"))
        self.assertEqual(first_response.status_code, 200)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.coins, DAILY_LOGIN_REWARD_COINS)
        self.assertEqual(self.profile.last_daily_reward_at, timezone.localdate())

        messages = [message.message for message in get_messages(first_response.wsgi_request)]
        self.assertTrue(
            any(
                f"Вы получили {DAILY_LOGIN_REWARD_COINS} монет" in message
                for message in messages
            ),
            msg="Daily reward success message was not added to the request",
        )

        second_response = self.client.get(reverse("my_profile"))
        self.assertEqual(second_response.status_code, 200)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.coins, DAILY_LOGIN_REWARD_COINS)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    MOBILE_APP_CLIENT_HEADER="X-Test-App",
    MOBILE_APP_ALLOWED_CLIENTS=["flutter-test"],
    YANDEX_REWARDED_AD_UNIT_ID="demo-yandex-unit",
)
class RewardAdApiTests(TestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = "localhost"
        self.client.defaults["wsgi.url_scheme"] = "https"
        self.client.defaults["HTTP_X_FORWARDED_PROTO"] = "https"

        header_key = "HTTP_" + settings.MOBILE_APP_CLIENT_HEADER.upper().replace("-", "_")
        self.client.defaults[header_key] = "flutter-test"
        self.app_header_key = header_key

        self.user = get_user_model().objects.create_user(
            username="reward_user",
            email="reward@example.com",
            password="RewardPass123!",
        )
        self.profile = self.user.profile
        self.initial_balance = self.profile.coins

    def test_config_requires_mobile_client_header(self):
        self.client.defaults.pop(self.app_header_key, None)
        response = self.client.get(reverse("reward_ad_config"))
        self.assertEqual(response.status_code, 404)

    def test_config_returns_expected_payload(self):
        response = self.client.get(reverse("reward_ad_config"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["placement_id"], "demo-yandex-unit")
        self.assertEqual(payload["reward_amount"], YANDEX_AD_REWARD_COINS)
        self.assertTrue(payload["requires_authentication"])

    def test_claim_requires_authentication(self):
        response = self.client.post(
            reverse("reward_ad_claim"),
            data=json.dumps({"ad_unit_id": "demo-yandex-unit"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_claim_awards_coins_via_api(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("reward_ad_claim"),
            data=json.dumps({"ad_unit_id": "demo-yandex-unit", "reward_id": "abc-123"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.coins, self.initial_balance + YANDEX_AD_REWARD_COINS)
        self.assertEqual(data["coins_awarded"], YANDEX_AD_REWARD_COINS)
        self.assertEqual(data["balance_after"], self.profile.coins)
        self.assertEqual(data["reward_id"], "abc-123")

    def test_claim_rejects_unknown_ad_unit(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("reward_ad_claim"),
            data=json.dumps({"ad_unit_id": "wrong"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.coins, self.initial_balance)

    @override_settings(YANDEX_REWARDED_AD_UNIT_ID="")
    def test_claim_returns_service_unavailable_when_disabled(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("reward_ad_claim"),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "reward_unavailable")