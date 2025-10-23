from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import localdate

from books.models import Book
from shelves.models import BookProgress, HomeLibraryEntry, ProgressAnnotation, Shelf, ShelfItem
from shelves.services import DEFAULT_HOME_LIBRARY_SHELF, DEFAULT_READ_SHELF


class BookDetailQuickAddShelfTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="reader", password="secret")
        self.book = Book.objects.create(title="Test Book")
        self.read_shelf = Shelf.objects.create(
            user=self.user,
            name=DEFAULT_READ_SHELF,
            is_default=True,
            is_public=True,
        )
        # ensure the home library shelf exists for subsequent checks
        self.home_shelf, _ = Shelf.objects.get_or_create(
            user=self.user,
            name=DEFAULT_HOME_LIBRARY_SHELF,
            defaults={"is_default": True, "is_public": False},
        )
        self.client.login(username="reader", password="secret")

    def test_add_to_read_shelf_stores_details(self):
        target_date = localdate() - timedelta(days=7)

        response = self.client.post(
            reverse("book_detail", args=[self.book.pk]),
            data={
                "action": "quick-add-shelf",
                "shelf": str(self.read_shelf.pk),
                "read_at": target_date.strftime("%Y-%m-%d"),
                "quote": "Важная цитата",
                "note": "Мысли после прочтения",
            },
        )

        self.assertRedirects(response, reverse("book_detail", args=[self.book.pk]))

        self.assertTrue(
            ShelfItem.objects.filter(shelf=self.read_shelf, book=self.book).exists(),
        )

        self.assertFalse(
            ShelfItem.objects.filter(shelf=self.home_shelf, book=self.book).exists(),
        )

        progress = BookProgress.objects.get(user=self.user, book=self.book, event__isnull=True)
        annotations = list(progress.annotations.order_by("kind", "pk"))
        self.assertEqual(len(annotations), 2)
        self.assertTrue(
            any(
                entry.kind == ProgressAnnotation.KIND_QUOTE and entry.body == "Важная цитата"
                for entry in annotations
            )
        )
        self.assertTrue(
            any(
                entry.kind == ProgressAnnotation.KIND_NOTE and entry.body == "Мысли после прочтения"
                for entry in annotations
            )
         )

    def test_read_date_respected_for_existing_home_library_entry(self):
        home_item = ShelfItem.objects.create(shelf=self.home_shelf, book=self.book)
        entry = HomeLibraryEntry.objects.create(shelf_item=home_item)
        target_date = localdate() - timedelta(days=14)

        response = self.client.post(
            reverse("book_detail", args=[self.book.pk]),
            data={
                "action": "quick-add-shelf",
                "shelf": str(self.read_shelf.pk),
                "read_at": target_date.strftime("%Y-%m-%d"),
            },
        )

        self.assertRedirects(response, reverse("book_detail", args=[self.book.pk]))

        entry.refresh_from_db()
        self.assertEqual(entry.read_at, target_date)
