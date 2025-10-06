from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import localdate

from books.models import Book, ISBNModel
from .models import (
    BookProgress,
    ReadingLog,
    CharacterNote,
    Shelf,
    ShelfItem,
)


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
        self.assertEqual(log.pages_equivalent, Decimal("15"))
        self.assertEqual(log.medium, BookProgress.FORMAT_PAPER)
        self.assertEqual(log.log_date, localdate())

    def test_mark_finished_sets_to_total_pages_and_logs_delta(self):
        progress = self._create_progress()

        response = self.client.post(reverse("reading_mark_finished", args=[progress.pk]))

        self.assertRedirects(response, reverse("reading_track", args=[self.book.pk]))
        progress.refresh_from_db()
        self.assertEqual(progress.current_page, 200)
        self.assertEqual(progress.percent, Decimal("100"))
        log = progress.logs.get()
        self.assertEqual(log.pages_equivalent, Decimal("200"))

    def test_mark_finished_moves_book_between_default_shelves(self):
        progress = self._create_progress()
        reading_shelf = Shelf.objects.get(user=self.user, name="Читаю")
        read_shelf = Shelf.objects.get(user=self.user, name="Прочитал")
        want_shelf = Shelf.objects.get(user=self.user, name="Хочу прочитать")
        ShelfItem.objects.get_or_create(shelf=reading_shelf, book=self.book)
        ShelfItem.objects.get_or_create(shelf=want_shelf, book=self.book)

        self.client.post(reverse("reading_mark_finished", args=[progress.pk]))

        self.assertFalse(
            ShelfItem.objects.filter(shelf=reading_shelf, book=self.book).exists()
        )
        self.assertFalse(
            ShelfItem.objects.filter(shelf=want_shelf, book=self.book).exists()
        )
        self.assertTrue(
            ShelfItem.objects.filter(shelf=read_shelf, book=self.book).exists()
        )

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
        self.assertEqual(log.pages_equivalent, Decimal("45"))

    def test_average_speed_and_estimate(self):
        progress = self._create_progress()
        ReadingLog.objects.create(
            progress=progress,
            log_date=localdate() - timedelta(days=1),
            pages_equivalent=Decimal("40"),
        )
        ReadingLog.objects.create(
            progress=progress,
            log_date=localdate(),
            pages_equivalent=Decimal("60"),
        )
        progress.current_page = 100
        progress.save(update_fields=["current_page"])
        progress.recalc_percent()

        self.assertEqual(progress.average_pages_per_day, Decimal("50.00"))
        self.assertEqual(progress.estimated_days_remaining, 2)

    def test_track_view_context_includes_logs(self):
        progress = self._create_progress()
        ReadingLog.objects.create(progress=progress, log_date=localdate(), pages_equivalent=Decimal("20"))

        response = self.client.get(reverse("reading_track", args=[self.book.pk]))

        self.assertIn("daily_logs", response.context)
        self.assertIn("average_pages_per_day", response.context)
        self.assertIn("estimated_days_remaining", response.context)
        logs = list(response.context["daily_logs"])
        self.assertIn("chart_scale", response.context)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].pages_equivalent, Decimal("20"))
        self.assertGreater(response.context["chart_scale"], 0)

    def test_update_notes_persists_text(self):
        progress = self._create_progress()
        payload = {
            "reading_notes": "Глава 1: сильные эмоции, цитата про дружбу",
        }

        response = self.client.post(
            reverse("reading_update_notes", args=[progress.pk]),
            payload,
        )

        self.assertRedirects(response, reverse("reading_track", args=[self.book.pk]))

        progress.refresh_from_db()
        self.assertEqual(progress.reading_notes, payload["reading_notes"])

    def test_add_character_creates_entry(self):
        progress = self._create_progress()

        response = self.client.post(
            reverse("reading_add_character", args=[progress.pk]),
            {"name": "Гарри Поттер", "description": "Главный герой, волшебник"},
        )

        self.assertRedirects(response, reverse("reading_track", args=[self.book.pk]))
        character = CharacterNote.objects.get(progress=progress)
        self.assertEqual(character.name, "Гарри Поттер")
        self.assertEqual(character.description, "Главный герой, волшебник")

    def test_audio_increment_updates_current_page_and_logs_audio(self):
        progress = self._create_progress()
        progress.media.get_or_create(
            medium=BookProgress.FORMAT_PAPER,
            defaults={"current_page": 0},
        )
        progress.media.get_or_create(
            medium=BookProgress.FORMAT_AUDIO,
            defaults={
                "audio_length": timedelta(minutes=200),
                "audio_position": timedelta(),
            },
        )

        response = self.client.post(
            reverse("reading_increment", args=[progress.pk, 0]),
            {"medium": BookProgress.FORMAT_AUDIO, "minutes": 30},
        )

        self.assertRedirects(response, reverse("reading_track", args=[self.book.pk]))

        progress.refresh_from_db()
        self.assertEqual(progress.current_page, 30)
        self.assertEqual(progress.media.get(medium=BookProgress.FORMAT_PAPER).current_page, 30)

        audio_medium = progress.media.get(medium=BookProgress.FORMAT_AUDIO)
        self.assertEqual(audio_medium.audio_position, timedelta(minutes=30))

        log = progress.logs.get()
        self.assertEqual(log.medium, BookProgress.FORMAT_AUDIO)
        self.assertEqual(log.pages_equivalent, Decimal("30"))
        self.assertEqual(log.audio_seconds, 1800)

    def test_audio_increment_respects_playback_speed(self):
        progress = self._create_progress()
        progress.audio_length = timedelta(minutes=200)
        progress.audio_playback_speed = Decimal("2.0")
        progress.save(update_fields=["audio_length", "audio_playback_speed"])

        paper_medium, _ = progress.media.get_or_create(
            medium=BookProgress.FORMAT_PAPER,
            defaults={"current_page": 0},
        )
        audio_medium, _ = progress.media.get_or_create(
            medium=BookProgress.FORMAT_AUDIO,
            defaults={
                "audio_length": timedelta(minutes=200),
                "audio_position": timedelta(),
                "playback_speed": Decimal("2.0"),
            },
        )

        response = self.client.post(
            reverse("reading_increment", args=[progress.pk, 0]),
            {"medium": BookProgress.FORMAT_AUDIO, "minutes": 15},
        )

        self.assertRedirects(response, reverse("reading_track", args=[self.book.pk]))

        progress.refresh_from_db()
        audio_medium.refresh_from_db()
        paper_medium.refresh_from_db()

        self.assertEqual(audio_medium.audio_position, timedelta(minutes=30))
        self.assertEqual(progress.current_page, 30)
        self.assertEqual(paper_medium.current_page, 30)

        log = progress.logs.get()
        self.assertEqual(log.medium, BookProgress.FORMAT_AUDIO)
        self.assertEqual(log.pages_equivalent, Decimal("30"))
        self.assertEqual(log.audio_seconds, 1800)
        
    def test_page_increment_updates_audio_medium_position(self):
        progress = self._create_progress()
        paper_medium, _ = progress.media.get_or_create(
            medium=BookProgress.FORMAT_PAPER,
            defaults={"current_page": 0},
        )
        audio_medium, _ = progress.media.get_or_create(
            medium=BookProgress.FORMAT_AUDIO,
            defaults={
                "audio_length": timedelta(minutes=200),
                "audio_position": timedelta(),
            },
        )

        response = self.client.post(
            reverse("reading_increment", args=[progress.pk, 20]),
            {"medium": BookProgress.FORMAT_PAPER},
        )

        self.assertRedirects(response, reverse("reading_track", args=[self.book.pk]))

        audio_medium.refresh_from_db()
        progress.refresh_from_db()
        paper_medium.refresh_from_db()

        self.assertEqual(progress.current_page, 20)
        self.assertEqual(paper_medium.current_page, 20)
        self.assertEqual(audio_medium.audio_position, timedelta(minutes=20))
        self.assertEqual(progress.audio_position, timedelta(minutes=20))

        log = progress.logs.get()
        self.assertEqual(log.medium, BookProgress.FORMAT_PAPER)
        self.assertEqual(log.pages_equivalent, Decimal("20"))
        self.assertEqual(log.audio_seconds, 0)

    def test_add_character_invalid_shows_errors(self):
        progress = self._create_progress()

        response = self.client.post(
            reverse("reading_add_character", args=[progress.pk]),
            {"name": "", "description": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "reading/track.html")
        form = response.context["character_form"]
        self.assertTrue(form.errors)


class ShelfDefaultActionsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="pass1234")
        self.client.login(username="owner", password="pass1234")
        self.book = Book.objects.create(title="Default Book", synopsis="")

    def test_quick_add_reading_removes_from_want(self):
        want_shelf = Shelf.objects.get(user=self.user, name="Хочу прочитать")
        reading_shelf = Shelf.objects.get(user=self.user, name="Читаю")
        ShelfItem.objects.create(shelf=want_shelf, book=self.book)

        response = self.client.post(reverse("quick_add_shelf", args=[self.book.pk, "reading"]))

        self.assertRedirects(response, reverse("reading_track", args=[self.book.pk]))
        self.assertTrue(
            ShelfItem.objects.filter(shelf=reading_shelf, book=self.book).exists()
        )
        self.assertFalse(
            ShelfItem.objects.filter(shelf=want_shelf, book=self.book).exists()
        )

    def test_quick_add_read_removes_from_other_defaults(self):
        want_shelf = Shelf.objects.get(user=self.user, name="Хочу прочитать")
        reading_shelf = Shelf.objects.get(user=self.user, name="Читаю")
        read_shelf = Shelf.objects.get(user=self.user, name="Прочитал")
        ShelfItem.objects.create(shelf=want_shelf, book=self.book)
        ShelfItem.objects.create(shelf=reading_shelf, book=self.book)

        response = self.client.post(reverse("quick_add_shelf", args=[self.book.pk, "read"]))

        self.assertRedirects(response, reverse("book_detail", args=[self.book.pk]))
        self.assertTrue(
            ShelfItem.objects.filter(shelf=read_shelf, book=self.book).exists()
        )
        self.assertFalse(
            ShelfItem.objects.filter(shelf=reading_shelf, book=self.book).exists()
        )
        self.assertFalse(
            ShelfItem.objects.filter(shelf=want_shelf, book=self.book).exists()
        )

    def test_add_to_reading_form_removes_from_want(self):
        want_shelf = Shelf.objects.get(user=self.user, name="Хочу прочитать")
        reading_shelf = Shelf.objects.get(user=self.user, name="Читаю")
        ShelfItem.objects.create(shelf=want_shelf, book=self.book)

        response = self.client.post(
            reverse("add_book_to_shelf", args=[self.book.pk]),
            {"shelf": reading_shelf.id},
        )

        self.assertRedirects(response, reverse("book_detail", args=[self.book.pk]))
        self.assertTrue(
            ShelfItem.objects.filter(shelf=reading_shelf, book=self.book).exists()
        )
        self.assertFalse(
            ShelfItem.objects.filter(shelf=want_shelf, book=self.book).exists()
        )