from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from books.models import Author, Book

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