from django.contrib.auth import get_user_model
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
from accounts.models import CoinTransaction, PremiumSubscription
from books.models import Author, Book


class SignUpPageTests(TestCase):
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


class PasswordResetFlowTests(TestCase):
    def setUp(self):
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

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        new_password = "NewPass123!"
        response = self.client.post(
            url,
            {
                "new_password1": new_password,
                "new_password2": new_password,
            },
        )
        self.assertRedirects(response, reverse("password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))


class AuthorProfileBooksTests(TestCase):
    def setUp(self):
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


class CoinEconomyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="coins_user",
            email="coins@example.com",
            password="CoinsPass123!",
        )
        self.profile = self.user.profile

    def test_credit_coins_records_transaction(self):
        tx = self.profile.credit_coins(
            15,
            transaction_type=CoinTransaction.Type.ADMIN_ADJUSTMENT,
            description="Начисление",
        )

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.coins, 15)
        self.assertEqual(tx.balance_after, 15)
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
        self.assertEqual(self.profile.coins, 15)
        self.assertEqual(tx.change, -5)
        self.assertEqual(tx.balance_after, 15)

    def test_spend_coins_raises_when_insufficient(self):
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
        self.assertEqual(self.profile.coins, 0)
        self.assertTrue(tx.unlimited)
        self.assertIsNone(tx.balance_after)

    def test_reward_ad_view_credits_coins(self):
        tx = self.profile.reward_ad_view(7)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.coins, 7)
        self.assertEqual(tx.transaction_type, CoinTransaction.Type.AD_REWARD)
        self.assertGreater(len(tx.description), 0)