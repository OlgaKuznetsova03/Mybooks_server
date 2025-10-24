from __future__ import annotations

from unittest import mock

from django.test import TestCase
from django.urls import reverse


class BookListISBNDBSuggestionsTests(TestCase):
    def _build_external_result(self) -> dict[str, object]:
        return {
            "title": "Remote Book",
            "subtitle": "",
            "authors": ["Jane Roe"],
            "publishers": ["Example Publisher"],
            "publish_date": "2024",
            "number_of_pages": 320,
            "physical_format": "Печатная книга",
            "format_canonical": None,
            "format_kind": None,
            "subjects": ["Fiction"],
            "languages": ["Русский"],
            "description": "Test description",
            "cover_url": "https://example.com/cover.jpg",
            "source_url": "https://example.com/books/remote",
            "isbn_list": ["9781234567890"],
            "metadata": {
                "9781234567890": {
                    "title": "Remote Book",
                    "authors": ["Jane Roe"],
                }
            },
            "matching_editions": [],
        }

    def test_renders_isbndb_suggestions_from_lookup_helper(self) -> None:
        fake_payload = {
            "query": {"title": "Remote Book", "author": "", "isbn": ""},
            "local_results": [],
            "external_results": [self._build_external_result()],
            "external_error": None,
            "force_external": True,
        }

        with mock.patch("books.views._perform_book_lookup", return_value=fake_payload) as lookup_mock:
            response = self.client.get(reverse("book_list"), {"q": "Remote Book"})

        lookup_mock.assert_called_once_with(
            title="Remote Book",
            author="",
            isbn_raw="",
            force_external=True,
            local_limit=0,
            external_limit=6,
        )

        self.assertContains(response, "Remote Book")
        self.assertContains(response, "Предложения из ISBNdb")
        self.assertContains(response, "Открыть в ISBNdb")

    def test_displays_error_message_when_lookup_reports_failure(self) -> None:
        fake_payload = {
            "query": {"title": "Remote Book", "author": "", "isbn": ""},
            "local_results": [],
            "external_results": [],
            "external_error": "Не удалось получить данные из ISBNdb. Попробуйте позже.",
            "force_external": True,
        }

        with mock.patch("books.views._perform_book_lookup", return_value=fake_payload):
            response = self.client.get(reverse("book_list"), {"q": "Remote Book"})

        self.assertContains(response, "Не удалось получить данные из ISBNdb. Попробуйте позже.")
        self.assertContains(response, "Предложения из ISBNdb")