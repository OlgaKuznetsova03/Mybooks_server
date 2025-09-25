from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from books.models import Book, ISBNModel
from .models import BookProgress


class ReadingTrackViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="reader", password="test-pass")
        self.client.login(username="reader", password="test-pass")

        self.isbn = ISBNModel.objects.create(
            isbn="9780000000000",
            isbn13="9780000000000",
            title="Test ISBN",
            total_pages=200,
        )
        self.book = Book.objects.create(title="Test Book", synopsis="")
        self.book.primary_isbn = self.isbn
        self.book.save()
        self.book.isbn.add(self.isbn)

    def _create_progress(self):
        self.client.get(reverse("reading_track", args=[self.book.pk]))
        return BookProgress.objects.get(user=self.user, book=self.book, event=None)

    def test_set_page_persists_progress(self):
        progress = self._create_progress()

        response = self.client.post(
            reverse("reading_set_page", args=[progress.pk]),
            {"page": 50},
        )

        self.assertRedirects(response, reverse("reading_track", args=[self.book.pk]))

        progress.refresh_from_db()
        self.assertEqual(progress.current_page, 50)
        self.assertEqual(progress.percent, Decimal("25"))

        response = self.client.get(reverse("reading_track", args=[self.book.pk]))
        self.assertEqual(response.context["progress"].current_page, 50)

    def test_increment_updates_current_page(self):
        progress = self._create_progress()
        progress.current_page = 10
        progress.save(update_fields=["current_page"])

        response = self.client.post(
            reverse("reading_increment", args=[progress.pk, 15])
        )

        self.assertRedirects(response, reverse("reading_track", args=[self.book.pk]))
        progress.refresh_from_db()
        self.assertEqual(progress.current_page, 25)
        self.assertEqual(progress.percent, Decimal("12.5"))

    def test_mark_finished_sets_to_total_pages(self):
        progress = self._create_progress()

        response = self.client.post(reverse("reading_mark_finished", args=[progress.pk]))

# Create your tests here.
        self.assertRedirects(response, reverse("reading_track", args=[self.book.pk]))
        progress.refresh_from_db()
        self.assertEqual(progress.current_page, 200)
        self.assertEqual(progress.percent, Decimal("100"))


