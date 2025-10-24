from __future__ import annotations

from unittest import mock

from django.test import TestCase

from books import views
from books.api_clients import ExternalBookData
from books.models import Author, Book, Genre, ISBNModel, Publisher


class BookLookupTests(TestCase):
    def _create_local_book(self) -> Book:
        author = Author.objects.create(name="Local Author")
        genre = Genre.objects.create(name="Локальная фантастика")
        publisher = Publisher.objects.create(name="Local Publisher")
        isbn_entry = ISBNModel.objects.create(
            isbn="1234567890",
            isbn13="1234567890123",
            title="Existing Local Book",
        )
        book = Book.objects.create(title="Existing Local Book")
        book.authors.add(author)
        book.genres.add(genre)
        book.publisher.add(publisher)
        book.isbn.add(isbn_entry)
        return book

    def test_missing_api_key_sets_external_error(self) -> None:
        with mock.patch.object(views.isbndb_client, "api_key", "", create=True), mock.patch.object(
            views.isbndb_client, "search", side_effect=AssertionError("external search should be skipped")
        ):
            payload = views._perform_book_lookup(
                title="Remote Book",
                author="",
                isbn_raw="9781234567897",
                force_external=True,
            )

        self.assertEqual(payload["external_results"], [])
        self.assertEqual(payload["external_error"], views.ISBNDB_MISSING_KEY_ERROR)

    def test_local_results_do_not_trigger_external_lookup(self) -> None:
        self._create_local_book()

        with mock.patch.object(views.isbndb_client, "api_key", "test-key", create=True), mock.patch.object(
            views.isbndb_client, "search", side_effect=AssertionError("should not search when local results exist")
        ):
            payload = views._perform_book_lookup(
                title="Existing Local Book",
                author="Local Author",
                isbn_raw="",
                force_external=False,
            )

        self.assertEqual(len(payload["local_results"]), 1)
        self.assertIsNone(payload["external_error"])

    def test_external_results_returned_when_api_key_available(self) -> None:
        remote_item = ExternalBookData(
            title="Remote Book",
            subtitle=None,
            authors=["Jane Roe"],
            isbn_13=["9789876543210"],
            description="Remote description",
        )

        with mock.patch.object(views.isbndb_client, "api_key", "live-key", create=True), mock.patch.object(
            views.isbndb_client, "search", return_value=[remote_item]
        ) as search_mock:
            payload = views._perform_book_lookup(
                title="Remote Book",
                author="Jane Roe",
                isbn_raw="978-9876543210",
                force_external=True,
            )

        search_mock.assert_called_once_with(
            title="Remote Book",
            author="Jane Roe",
            isbn="9789876543210",
            limit=5,
        )
        self.assertEqual(len(payload["external_results"]), 1)
        self.assertIsNone(payload["external_error"])
        self.assertEqual(payload["external_results"][0]["title"], "Remote Book")