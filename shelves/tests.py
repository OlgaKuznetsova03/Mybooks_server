from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import localdate

from books.models import Book, ISBNModel
from .models import BookProgress, ReadingLog


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

    def test_increment_updates_current_page_and_creates_log(self):
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
        log = progress.logs.get()
        self.assertEqual(log.pages_read, 15)
        self.assertEqual(log.log_date, localdate())

    def test_mark_finished_sets_to_total_pages_and_logs_delta(self):
        progress = self._create_progress()

        response = self.client.post(reverse("reading_mark_finished", args=[progress.pk]))

        self.assertRedirects(response, reverse("reading_track", args=[self.book.pk]))
        progress.refresh_from_db()
        self.assertEqual(progress.current_page, 200)
        self.assertEqual(progress.percent, Decimal("100"))
        log = progress.logs.get()
        self.assertEqual(log.pages_read, 200)

    def test_percent_uses_related_isbn_when_no_primary(self):
        isbn = ISBNModel.objects.create(
            isbn="9780000000001",
            isbn13="9780000000001",
            title="Fallback ISBN",
            total_pages=120,
        )
        book_without_primary = Book.objects.create(title="No Primary", synopsis="")
        book_without_primary.isbn.add(isbn)

        self.client.get(reverse("reading_track", args=[book_without_primary.pk]))
        progress = BookProgress.objects.get(user=self.user, book=book_without_primary, event=None)

        response = self.client.post(
            reverse("reading_set_page", args=[progress.pk]),
            {"page": 60},
        )

# Create your tests here.
        self.assertRedirects(response, reverse("reading_track", args=[book_without_primary.pk]))
        progress.refresh_from_db()
        self.assertEqual(progress.percent, Decimal("50"))

    def test_set_page_accumulates_daily_log(self):
        progress = self._create_progress()

        self.client.post(reverse("reading_set_page", args=[progress.pk]), {"page": 30})
        self.client.post(reverse("reading_set_page", args=[progress.pk]), {"page": 45})

        progress.refresh_from_db()
        log = progress.logs.get()
        self.assertEqual(log.pages_read, 45)

    def test_average_speed_and_estimate(self):
        progress = self._create_progress()
        ReadingLog.objects.create(
            progress=progress,
            log_date=localdate() - timedelta(days=1),
            pages_read=40,
        )
        ReadingLog.objects.create(
            progress=progress,
            log_date=localdate(),
            pages_read=60,
        )
        progress.current_page = 100
        progress.save(update_fields=["current_page"])
        progress.recalc_percent()

        self.assertEqual(progress.average_pages_per_day, Decimal("50.00"))
        self.assertEqual(progress.estimated_days_remaining, 2)

    def test_track_view_context_includes_logs(self):
        progress = self._create_progress()
        ReadingLog.objects.create(progress=progress, log_date=localdate(), pages_read=20)

        response = self.client.get(reverse("reading_track", args=[self.book.pk]))

        self.assertIn("daily_logs", response.context)
        self.assertIn("average_pages_per_day", response.context)
        self.assertIn("estimated_days_remaining", response.context)
        logs = list(response.context["daily_logs"])
        self.assertIn("chart_scale", response.context)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].pages_read, 20)
        self.assertGreater(response.context["chart_scale"], 0)

    def test_update_notes_persists_text(self):
        progress = self._create_progress()
        payload = {
            "character_notes": "Гарри — избранный, Гермиона — мозг команды",
            "reading_notes": "Глава 1: сильные эмоции, цитата про дружбу",
        }

        response = self.client.post(
            reverse("reading_update_notes", args=[progress.pk]),
            payload,
        )

        self.assertRedirects(response, reverse("reading_track", args=[self.book.pk]))

        progress.refresh_from_db()
        self.assertEqual(progress.character_notes, payload["character_notes"])
        self.assertEqual(progress.reading_notes, payload["reading_notes"])