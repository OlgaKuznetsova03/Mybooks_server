from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.template import Context
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import localdate

from books.models import Book, ISBNModel
from .models import (
    BookProgress,
    ReadingLog,
    CharacterNote,
    ProgressAnnotation,
    Shelf,
    ShelfItem,
    ReadingFeedEntry,
    HomeLibraryEntry,
)
from .services import (
    DEFAULT_HOME_LIBRARY_SHELF,
    DEFAULT_READ_SHELF,
    ALL_DEFAULT_READ_SHELF_NAMES,
    get_default_shelf_status_map,
    move_book_to_read_shelf,
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
        self.client.get(reverse("shelves:reading_track", args=[self.book.pk]))
        return BookProgress.objects.get(user=self.user, book=self.book, event=None)

    def test_set_page_persists_progress(self):
        progress = self._create_progress()

        response = self.client.post(
            reverse("shelves:reading_set_page", args=[progress.pk]),
            {"page": 50},
        )

        self.assertRedirects(response, reverse("shelves:reading_track", args=[self.book.pk]))

        progress.refresh_from_db()
        self.assertEqual(progress.current_page, 50)
        self.assertEqual(progress.percent, Decimal("25"))

        response = self.client.get(reverse("shelves:reading_track", args=[self.book.pk]))
        self.assertEqual(response.context["progress"].current_page, 50)

    def test_increment_updates_current_page_and_creates_log(self):
        progress = self._create_progress()
        progress.current_page = 10
        progress.save(update_fields=["current_page"])

        response = self.client.post(
            reverse("shelves:reading_increment", args=[progress.pk, 15])
        )

        self.assertRedirects(response, reverse("shelves:reading_track", args=[self.book.pk]))
        progress.refresh_from_db()
        self.assertEqual(progress.current_page, 25)
        self.assertEqual(progress.percent, Decimal("12.5"))
        log = progress.logs.get()
        self.assertEqual(log.pages_equivalent, Decimal("15"))
        self.assertEqual(log.medium, BookProgress.FORMAT_PAPER)
        self.assertEqual(log.log_date, localdate())

    def test_mark_finished_sets_to_total_pages_and_logs_delta(self):
        progress = self._create_progress()

        response = self.client.post(reverse("shelves:reading_mark_finished", args=[progress.pk]))

        self.assertRedirects(response, reverse("shelves:reading_track", args=[self.book.pk]))
        progress.refresh_from_db()
        self.assertEqual(progress.current_page, 200)
        self.assertEqual(progress.percent, Decimal("100"))
        log = progress.logs.get()
        self.assertEqual(log.pages_equivalent, Decimal("200"))

    def test_mark_finished_moves_book_between_default_shelves(self):
        progress = self._create_progress()
        reading_shelf = Shelf.objects.get(user=self.user, name="Читаю")
        read_shelf = Shelf.objects.filter(
            user=self.user,
            name__in=ALL_DEFAULT_READ_SHELF_NAMES,
        ).first()
        self.assertIsNotNone(read_shelf)
        want_shelf = Shelf.objects.get(user=self.user, name="Хочу прочитать")
        ShelfItem.objects.get_or_create(shelf=reading_shelf, book=self.book)
        ShelfItem.objects.get_or_create(shelf=want_shelf, book=self.book)

        self.client.post(reverse("shelves:reading_mark_finished", args=[progress.pk]))

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

        self.client.get(reverse("shelves:reading_track", args=[book_without_primary.pk]))
        progress = BookProgress.objects.get(user=self.user, book=book_without_primary, event=None)

        response = self.client.post(
            reverse("shelves:reading_set_page", args=[progress.pk]),
            {"page": 60},
        )

# Create your tests here.
        self.assertRedirects(response, reverse("shelves:reading_track", args=[book_without_primary.pk]))
        progress.refresh_from_db()
        self.assertEqual(progress.percent, Decimal("50"))

    def test_set_page_accumulates_daily_log(self):
        progress = self._create_progress()

        self.client.post(reverse("shelves:reading_set_page", args=[progress.pk]), {"page": 30})
        self.client.post(reverse("shelves:reading_set_page", args=[progress.pk]), {"page": 45})

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

        response = self.client.get(reverse("shelves:reading_track", args=[self.book.pk]))

        self.assertIn("daily_logs", response.context)
        self.assertIn("average_pages_per_day", response.context)
        self.assertIn("estimated_days_remaining", response.context)
        logs = list(response.context["daily_logs"])
        self.assertIn("chart_scale", response.context)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].pages_equivalent, Decimal("20"))
        self.assertGreater(response.context["chart_scale"], 0)

    def test_chart_breakdown_includes_medium_details(self):
        progress = self._create_progress()
        today = localdate()
        ReadingLog.objects.create(
            progress=progress,
            log_date=today,
            medium=BookProgress.FORMAT_PAPER,
            pages_equivalent=Decimal("12"),
        )
        ReadingLog.objects.create(
            progress=progress,
            log_date=today,
            medium=BookProgress.FORMAT_EBOOK,
            pages_equivalent=Decimal("8"),
        )
        ReadingLog.objects.create(
            progress=progress,
            log_date=today,
            medium=BookProgress.FORMAT_AUDIO,
            pages_equivalent=Decimal("5"),
        )

        response = self.client.get(reverse("shelves:reading_track", args=[self.book.pk]))

        self.assertIn("chart_mediums", response.context)
        self.assertIn("chart_medium_pages", response.context)
        self.assertIn("audio_logs", response.context)
        mediums = response.context["chart_mediums"]
        medium_codes = {medium["code"] for medium in mediums}
        self.assertIn(BookProgress.FORMAT_PAPER, medium_codes)
        self.assertIn(BookProgress.FORMAT_EBOOK, medium_codes)
        self.assertNotIn(BookProgress.FORMAT_AUDIO, medium_codes)

        medium_pages = response.context["chart_medium_pages"]
        labels = response.context["chart_labels"]
        self.assertEqual(labels, [today.strftime("%d.%m.%Y")])
        self.assertEqual(response.context["chart_pages"], [20.0])
        self.assertEqual(medium_pages[BookProgress.FORMAT_PAPER], [12.0])
        self.assertEqual(medium_pages[BookProgress.FORMAT_EBOOK], [8.0])
        self.assertNotIn(BookProgress.FORMAT_AUDIO, medium_pages)

        audio_logs = list(response.context["audio_logs"])
        self.assertEqual(len(audio_logs), 1)
        self.assertEqual(audio_logs[0].medium, BookProgress.FORMAT_AUDIO)

    def test_public_update_creates_feed_entry(self):
        progress = self._create_progress()

        response = self.client.post(
            reverse("shelves:reading_set_page", args=[progress.pk]),
            {"page": 40, "reaction": "От книги не оторваться!", "is_public": "on"},
        )

        self.assertRedirects(response, reverse("shelves:reading_track", args=[self.book.pk]))
        entry = ReadingFeedEntry.objects.get()
        self.assertEqual(entry.book, self.book)
        self.assertEqual(entry.reaction, "От книги не оторваться!")
        self.assertEqual(entry.current_page_display, 40)

    def test_user_can_comment_on_feed_entry(self):
        progress = self._create_progress()
        self.client.post(
            reverse("shelves:reading_set_page", args=[progress.pk]),
            {"page": 30, "is_public": "on"},
        )
        entry = ReadingFeedEntry.objects.get()

        friend = User.objects.create_user(username="friend", password="secret-pass")
        self.client.logout()
        self.client.login(username="friend", password="secret-pass")

        response = self.client.post(
            reverse("shelves:reading_feed_comment", args=[entry.pk]),
            {"body": "Отличное продвижение!"},
        )

        self.assertRedirects(response, reverse("shelves:reading_feed"))
        entry.refresh_from_db()
        self.assertEqual(entry.comments.count(), 1)
        self.assertEqual(entry.comments.first().body, "Отличное продвижение!")

    def test_update_notes_persists_text(self):
        progress = self._create_progress()
        payload = {
            "reading_notes": "Глава 1: сильные эмоции, цитата про дружбу",
        }

        response = self.client.post(
            reverse("shelves:reading_update_notes", args=[progress.pk]),
            payload,
        )

        self.assertRedirects(response, reverse("shelves:reading_track", args=[self.book.pk]))

        progress.refresh_from_db()
        self.assertEqual(progress.reading_notes, payload["reading_notes"])

    def test_add_character_creates_entry(self):
        progress = self._create_progress()

        response = self.client.post(
            reverse("shelves:reading_add_character", args=[progress.pk]),
            {"name": "Гарри Поттер", "description": "Главный герой, волшебник"},
        )

        self.assertRedirects(response, reverse("shelves:reading_track", args=[self.book.pk]))
        character = CharacterNote.objects.get(progress=progress)
        self.assertEqual(character.name, "Гарри Поттер")
        self.assertEqual(character.description, "Главный герой, волшебник")

    def test_update_character_changes_existing_entry(self):
        progress = self._create_progress()
        character = CharacterNote.objects.create(
            progress=progress,
            name="Гермиона",
            description="Подруга главного героя",
        )

        response = self.client.post(
            reverse("shelves:reading_update_character", args=[progress.pk, character.pk]),
            {
                f"character-{character.pk}-name": "Гермиона Грейнджер",
                f"character-{character.pk}-description": "Лучший друг и голос разума",
            },
        )

        self.assertRedirects(response, reverse("shelves:reading_track", args=[self.book.pk]))
        character.refresh_from_db()
        self.assertEqual(character.name, "Гермиона Грейнджер")
        self.assertEqual(character.description, "Лучший друг и голос разума")

    def test_add_quote_creates_annotation(self):
        progress = self._create_progress()

        response = self.client.post(
            reverse("shelves:reading_add_quote", args=[progress.pk]),
            {
                "location": "Стр. 42",
                "body": "Счастье можно найти даже в самые тёмные времена...",
                "comment": "Любимая цитата Дамблдора",
            },
        )

        self.assertRedirects(response, reverse("shelves:reading_track", args=[self.book.pk]))
        quote = ProgressAnnotation.objects.get(progress=progress)
        self.assertEqual(quote.kind, ProgressAnnotation.KIND_QUOTE)
        self.assertEqual(quote.location, "Стр. 42")
        self.assertIn("Счастье можно найти", quote.body)

    def test_update_quote_changes_existing_annotation(self):
        progress = self._create_progress()
        quote = ProgressAnnotation.objects.create(
            progress=progress,
            kind=ProgressAnnotation.KIND_QUOTE,
            body="Первоначальная цитата",
            location="Стр. 10",
        )

        response = self.client.post(
            reverse("shelves:reading_update_quote", args=[progress.pk, quote.pk]),
            {
                f"quote-{quote.pk}-location": "Стр. 120",
                f"quote-{quote.pk}-body": "Обновлённая цитата",
                f"quote-{quote.pk}-comment": "Отмечаю кульминацию",
            },
        )

        self.assertRedirects(response, reverse("shelves:reading_track", args=[self.book.pk]))
        quote.refresh_from_db()
        self.assertEqual(quote.location, "Стр. 120")
        self.assertEqual(quote.body, "Обновлённая цитата")
        self.assertEqual(quote.comment, "Отмечаю кульминацию")

    def test_add_note_entry_creates_annotation(self):
        progress = self._create_progress()

        response = self.client.post(
            reverse("shelves:reading_add_note_entry", args=[progress.pk]),
            {
                "location": "Глава 3",
                "body": "Автор раскрывает второстепенную линию",
                "comment": "Понравилась динамика",
            },
        )

        self.assertRedirects(response, reverse("shelves:reading_track", args=[self.book.pk]))
        note = ProgressAnnotation.objects.get(progress=progress)
        self.assertEqual(note.kind, ProgressAnnotation.KIND_NOTE)
        self.assertEqual(note.location, "Глава 3")
        self.assertIn("второстепенную", note.body)

    def test_update_note_entry_changes_annotation(self):
        progress = self._create_progress()
        note = ProgressAnnotation.objects.create(
            progress=progress,
            kind=ProgressAnnotation.KIND_NOTE,
            body="Черновик заметки",
        )

        response = self.client.post(
            reverse("shelves:reading_update_note_entry", args=[progress.pk, note.pk]),
            {
                f"note-{note.pk}-location": "Эпилог",
                f"note-{note.pk}-body": "Финал удивил",
                f"note-{note.pk}-comment": "Жду продолжение",
            },
        )

        self.assertRedirects(response, reverse("shelves:reading_track", args=[self.book.pk]))
        note.refresh_from_db()
        self.assertEqual(note.location, "Эпилог")
        self.assertEqual(note.body, "Финал удивил")
        self.assertEqual(note.comment, "Жду продолжение")

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
            reverse("shelves:reading_increment", args=[progress.pk, 0]),
            {"medium": BookProgress.FORMAT_AUDIO, "minutes": 30},
        )

        self.assertRedirects(response, reverse("shelves:reading_track", args=[self.book.pk]))

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
            reverse("shelves:reading_increment", args=[progress.pk, 0]),
            {"medium": BookProgress.FORMAT_AUDIO, "minutes": 15},
        )

        self.assertRedirects(response, reverse("shelves:reading_track", args=[self.book.pk]))

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

    def test_audio_increment_scales_medium_with_custom_total(self):
        progress = self._create_progress()
        paper_medium, _ = progress.media.get_or_create(
            medium=BookProgress.FORMAT_PAPER,
            defaults={"current_page": 0},
        )
        ebook_medium, _ = progress.media.get_or_create(
            medium=BookProgress.FORMAT_EBOOK,
            defaults={
                "current_page": 0,
                "total_pages_override": 250,
            },
        )
        audio_medium, _ = progress.media.get_or_create(
            medium=BookProgress.FORMAT_AUDIO,
            defaults={
                "audio_length": timedelta(minutes=200),
                "audio_position": timedelta(),
            },
        )

        response = self.client.post(
            reverse("shelves:reading_increment", args=[progress.pk, 0]),
            {"medium": BookProgress.FORMAT_AUDIO, "minutes": 60},
        )

        self.assertRedirects(response, reverse("shelves:reading_track", args=[self.book.pk]))

        progress.refresh_from_db()
        paper_medium.refresh_from_db()
        ebook_medium.refresh_from_db()
        audio_medium.refresh_from_db()

        self.assertEqual(paper_medium.current_page, 60)
        self.assertEqual(ebook_medium.current_page, 75)
        self.assertEqual(ebook_medium.total_pages_override, 250)
        self.assertEqual(audio_medium.audio_position, timedelta(minutes=60))
        self.assertEqual(progress.current_page, 60)

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
            reverse("shelves:reading_increment", args=[progress.pk, 20]),
            {"medium": BookProgress.FORMAT_PAPER},
        )

        self.assertRedirects(response, reverse("shelves:reading_track", args=[self.book.pk]))

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
            reverse("shelves:reading_add_character", args=[progress.pk]),
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

        response = self.client.post(reverse("shelves:quick_add_shelf", args=[self.book.pk, "reading"]))

        self.assertRedirects(response, reverse("shelves:reading_track", args=[self.book.pk]))
        self.assertTrue(
            ShelfItem.objects.filter(shelf=reading_shelf, book=self.book).exists()
        )
        self.assertFalse(
            ShelfItem.objects.filter(shelf=want_shelf, book=self.book).exists()
        )

    def test_quick_add_read_removes_from_other_defaults(self):
        want_shelf = Shelf.objects.get(user=self.user, name="Хочу прочитать")
        reading_shelf = Shelf.objects.get(user=self.user, name="Читаю")
        read_shelf = Shelf.objects.filter(
            user=self.user,
            name__in=ALL_DEFAULT_READ_SHELF_NAMES,
        ).first()
        self.assertIsNotNone(read_shelf)
        ShelfItem.objects.create(shelf=want_shelf, book=self.book)
        ShelfItem.objects.create(shelf=reading_shelf, book=self.book)

        response = self.client.post(reverse("shelves:quick_add_shelf", args=[self.book.pk, "read"]))

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
            reverse("shelves:add_book_to_shelf", args=[self.book.pk]),
            {"shelf": reading_shelf.id},
        )

        self.assertRedirects(response, reverse("book_detail", args=[self.book.pk]))
        self.assertTrue(
            ShelfItem.objects.filter(shelf=reading_shelf, book=self.book).exists()
        )
        self.assertFalse(
            ShelfItem.objects.filter(shelf=want_shelf, book=self.book).exists()
               )

    def test_move_book_to_reading_redirects_back_when_next_provided(self):
        want_shelf = Shelf.objects.get(user=self.user, name="Хочу прочитать")
        reading_shelf = Shelf.objects.get(user=self.user, name="Читаю")
        ShelfItem.objects.create(shelf=want_shelf, book=self.book)

        response = self.client.post(
            reverse("shelves:move_book_to_reading", args=[self.book.pk]),
            {"next": "/profile/owner/"},
        )

        self.assertRedirects(
            response,
            "/profile/owner/",
            fetch_redirect_response=False,
        )
        self.assertTrue(
            ShelfItem.objects.filter(shelf=reading_shelf, book=self.book).exists()
        )
        self.assertFalse(
            ShelfItem.objects.filter(shelf=want_shelf, book=self.book).exists()
        )

    def test_move_book_to_reading_without_next_redirects_to_track(self):
        reading_shelf = Shelf.objects.get(user=self.user, name="Читаю")

        response = self.client.post(
            reverse("shelves:move_book_to_reading", args=[self.book.pk])
        )

        self.assertRedirects(
            response,
            reverse("shelves:reading_track", args=[self.book.pk]),
        )
        self.assertTrue(
            ShelfItem.objects.filter(shelf=reading_shelf, book=self.book).exists()
        )


class DefaultShelfStatusMapTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="map-user", password="pass")
        self.book = Book.objects.create(title="Status Book")
        self.factory = RequestFactory()

    def test_completed_progress_marks_book_as_read(self):
        progress = BookProgress.objects.create(
            user=self.user,
            book=self.book,
            percent=Decimal("100"),
        )

        status_map = get_default_shelf_status_map(self.user, [self.book.pk])

        self.assertIn(self.book.pk, status_map)
        status = status_map[self.book.pk]
        self.assertEqual(status["code"], "read")
        self.assertEqual(status["label"], DEFAULT_READ_SHELF)
        self.assertEqual(status["added_at"], progress.updated_at)
        
    def test_book_on_read_shelf_is_detected(self):
        read_shelf = Shelf.objects.filter(
            user=self.user,
            name__in=ALL_DEFAULT_READ_SHELF_NAMES,
        ).first()
        self.assertIsNotNone(read_shelf)
        shelf_item = ShelfItem.objects.create(shelf=read_shelf, book=self.book)

        status_map = get_default_shelf_status_map(self.user, [self.book.pk])

        status = status_map[self.book.pk]
        self.assertEqual(status["code"], "read")
        self.assertEqual(status["label"], read_shelf.name)
        self.assertEqual(status["added_at"], shelf_item.added_at)

    def test_home_library_read_date_marks_book_as_read(self):
        home_shelf = Shelf.objects.get(user=self.user, name=DEFAULT_HOME_LIBRARY_SHELF)
        home_item = ShelfItem.objects.create(shelf=home_shelf, book=self.book)
        read_date = localdate() - timedelta(days=5)
        HomeLibraryEntry.objects.create(shelf_item=home_item, read_at=read_date)

        status_map = get_default_shelf_status_map(self.user, [self.book.pk])

        status = status_map[self.book.pk]
        self.assertEqual(status["code"], "read")
        self.assertEqual(status["label"], DEFAULT_READ_SHELF)
        self.assertEqual(status["added_at"], read_date)

    def test_home_library_read_date_prefers_earliest_completion(self):
        read_shelf = Shelf.objects.filter(
            user=self.user,
            name__in=ALL_DEFAULT_READ_SHELF_NAMES,
        ).first()
        self.assertIsNotNone(read_shelf)
        read_item = ShelfItem.objects.create(shelf=read_shelf, book=self.book)

        home_shelf = Shelf.objects.get(user=self.user, name=DEFAULT_HOME_LIBRARY_SHELF)
        home_item = ShelfItem.objects.create(shelf=home_shelf, book=self.book)
        earlier_date = localdate() - timedelta(days=10)
        HomeLibraryEntry.objects.create(shelf_item=home_item, read_at=earlier_date)

        status_map = get_default_shelf_status_map(self.user, [self.book.pk])

        status = status_map[self.book.pk]
        self.assertEqual(status["code"], "read")
        self.assertEqual(status["label"], read_shelf.name)
        self.assertEqual(status["added_at"], earlier_date)


class HomeLibraryEntryReadDateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="home-user", password="pass")
        self.book = Book.objects.create(title="Home Book")

    def test_move_to_read_sets_read_date(self):
        home_shelf = Shelf.objects.get(user=self.user, name=DEFAULT_HOME_LIBRARY_SHELF)
        shelf_item = ShelfItem.objects.create(shelf=home_shelf, book=self.book)
        entry = HomeLibraryEntry.objects.create(shelf_item=shelf_item)

        move_book_to_read_shelf(self.user, self.book)

        entry.refresh_from_db()
        self.assertEqual(entry.read_at, localdate())

    def test_entry_created_with_read_date_if_missing(self):
        home_shelf = Shelf.objects.get(user=self.user, name=DEFAULT_HOME_LIBRARY_SHELF)

        move_book_to_read_shelf(self.user, self.book)

        entry = HomeLibraryEntry.objects.get(shelf_item__shelf=home_shelf, shelf_item__book=self.book)
        self.assertEqual(entry.read_at, localdate())

    def test_move_to_read_respects_custom_read_date(self):
        target_date = localdate() - timedelta(days=10)

        move_book_to_read_shelf(self.user, self.book, read_date=target_date)

        home_shelf = Shelf.objects.get(user=self.user, name=DEFAULT_HOME_LIBRARY_SHELF)
        entry = HomeLibraryEntry.objects.get(shelf_item__shelf=home_shelf, shelf_item__book=self.book)
        self.assertEqual(entry.read_at, target_date)
        
    def test_move_to_read_sets_shelf_item_added_at_date(self):
        target_date = localdate() - timedelta(days=7)

        move_book_to_read_shelf(self.user, self.book, read_date=target_date)

        read_shelf = Shelf.objects.filter(
            user=self.user,
            name__in=ALL_DEFAULT_READ_SHELF_NAMES,
        ).first()
        self.assertIsNotNone(read_shelf)

        shelf_item = ShelfItem.objects.get(shelf=read_shelf, book=self.book)
        added_at_local = timezone.localtime(shelf_item.added_at)
        self.assertEqual(added_at_local.date(), target_date)
        
    def test_template_tag_handles_shelf_items(self):
        read_shelf = Shelf.objects.filter(
            user=self.user,
            name__in=ALL_DEFAULT_READ_SHELF_NAMES,
        ).first()
        self.assertIsNotNone(read_shelf)
        shelf_item = ShelfItem.objects.create(shelf=read_shelf, book=self.book)

        request = self.factory.get("/")
        request.user = self.user
        context = Context({"request": request})

        from shelves.templatetags.shelf_extras import default_shelf_status_map

        status_map = default_shelf_status_map(context, [shelf_item])

        status = status_map[self.book.pk]
        self.assertEqual(status["code"], "read")
        self.assertEqual(status["label"], read_shelf.name)
        self.assertEqual(status["added_at"], shelf_item.added_at)

    def test_home_library_add_uses_read_shelf_date(self):
        target_date = localdate() - timedelta(days=4)

        move_book_to_read_shelf(self.user, self.book, read_date=target_date)

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("book_detail", args=[self.book.pk]),
            {
                "action": "home-library-add",
                "purchase_date": "",
                "read_date": "",
            },
        )

        self.assertEqual(response.status_code, 302)

        home_shelf = Shelf.objects.get(user=self.user, name=DEFAULT_HOME_LIBRARY_SHELF)
        entry = HomeLibraryEntry.objects.get(
            shelf_item__shelf=home_shelf,
            shelf_item__book=self.book,
        )
        self.assertEqual(entry.read_at, target_date)

    def test_home_library_add_with_read_date_adds_read_shelf_entry(self):
        target_date = localdate() - timedelta(days=2)

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("book_detail", args=[self.book.pk]),
            {
                "action": "home-library-add",
                "mark_as_read": "on",
                "read_date": target_date.isoformat(),
                "purchase_date": "",
            },
        )

        self.assertEqual(response.status_code, 302)

        home_shelf = Shelf.objects.get(user=self.user, name=DEFAULT_HOME_LIBRARY_SHELF)
        entry = HomeLibraryEntry.objects.get(
            shelf_item__shelf=home_shelf,
            shelf_item__book=self.book,
        )
        self.assertEqual(entry.read_at, target_date)

        read_shelf = Shelf.objects.filter(
            user=self.user,
            name__in=ALL_DEFAULT_READ_SHELF_NAMES,
        ).first()
        self.assertIsNotNone(read_shelf)

        shelf_item = ShelfItem.objects.filter(shelf=read_shelf, book=self.book).first()
        self.assertIsNotNone(shelf_item)
        added_at = shelf_item.added_at
        self.assertIsNotNone(added_at)
        if timezone.is_aware(added_at):
            added_date = timezone.localtime(added_at).date()
        else:
            added_date = added_at.date()
        self.assertEqual(added_date, target_date)

    def test_read_shelf_alias_supported(self):
        Shelf.objects.filter(user=self.user, name=DEFAULT_READ_SHELF).update(name="Прочитано")
        read_shelf = Shelf.objects.get(user=self.user, name="Прочитано")
        shelf_item = ShelfItem.objects.create(shelf=read_shelf, book=self.book)

        status_map = get_default_shelf_status_map(self.user, [self.book.pk])

        status = status_map[self.book.pk]
        self.assertEqual(status["code"], "read")
        self.assertEqual(status["label"], read_shelf.name)
        self.assertEqual(status["added_at"], shelf_item.added_at)

    def test_remove_from_read_shelf_clears_user_data(self):
        read_shelf = Shelf.objects.filter(
            user=self.user,
            name__in=ALL_DEFAULT_READ_SHELF_NAMES,
        ).first()
        self.assertIsNotNone(read_shelf)

        home_shelf = Shelf.objects.get(user=self.user, name=DEFAULT_HOME_LIBRARY_SHELF)
        home_item = ShelfItem.objects.create(shelf=home_shelf, book=self.book)
        entry, _ = HomeLibraryEntry.objects.get_or_create(shelf_item=home_item)
        entry.read_at = localdate()
        entry.save(update_fields=["read_at"])

        ShelfItem.objects.create(shelf=read_shelf, book=self.book)
        BookProgress.objects.create(user=self.user, book=self.book, percent=100)

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("shelves:remove_book_from_shelf", args=[read_shelf.pk, self.book.pk]),
            follow=True,
        )

        self.assertIn(response.status_code, (200, 302))
        self.assertFalse(
            ShelfItem.objects.filter(shelf__user=self.user, book=self.book).exists()
        )
        self.assertFalse(
            HomeLibraryEntry.objects.filter(
                shelf_item__shelf__user=self.user,
                shelf_item__book=self.book,
            ).exists()
        )
        self.assertFalse(BookProgress.objects.filter(user=self.user, book=self.book).exists())

    def test_home_library_view_marks_entry_as_read_via_read_at(self):
        home_shelf = Shelf.objects.get(user=self.user, name=DEFAULT_HOME_LIBRARY_SHELF)
        shelf_item = ShelfItem.objects.create(shelf=home_shelf, book=self.book)
        read_date = localdate() - timedelta(days=3)
        entry = HomeLibraryEntry.objects.create(shelf_item=shelf_item, read_at=read_date)

        self.client.force_login(self.user)
        response = self.client.get(reverse("shelves:home_library"))

        self.assertEqual(response.status_code, 200)
        entries = response.context["entries"]
        self.assertTrue(entries)
        context_entry = next((e for e in entries if e.shelf_item_id == entry.shelf_item_id), None)
        self.assertIsNotNone(context_entry)
        self.assertTrue(getattr(context_entry, "is_read", False))
        self.assertEqual(context_entry.date_read, read_date)