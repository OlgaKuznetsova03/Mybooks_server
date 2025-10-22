import sys
import types
from unittest import TestCase, mock


# Provide a minimal django.conf.settings stub so that importing the client works
django_module = types.ModuleType("django")
django_conf_module = types.ModuleType("django.conf")
django_conf_module.settings = types.SimpleNamespace()
django_module.conf = django_conf_module
sys.modules.setdefault("django", django_module)
sys.modules.setdefault("django.conf", django_conf_module)

from books.api_clients import ISBNDBClient, ISBNDB_SEARCH_BOOKS_URL


class ISBNDBClientSearchTests(TestCase):
    def setUp(self) -> None:
        self.client = ISBNDBClient(api_key="test")

    def _mock_response(self) -> dict:
        return {
            "books": [
                {
                    "title": "Sample Book",
                    "authors": ["Jane Doe"],
                    "language": "en",
                }
            ]
        }

    def test_search_uses_search_books_endpoint_for_title_and_author(self) -> None:
        response = self._mock_response()
        with mock.patch.object(self.client, "_fetch_json_url", return_value=response) as fetch_mock:
            results = self.client.search(title="Harry Potter", author="Rowling", limit=3)

        self.assertEqual(len(results), 1)
        fetch_mock.assert_called_once()
        called_url, called_params = fetch_mock.call_args[0]
        self.assertEqual(called_url, ISBNDB_SEARCH_BOOKS_URL)
        self.assertEqual(called_params["q"], "Harry Potter")
        self.assertEqual(called_params["author"], "Rowling")
        self.assertEqual(called_params["pageSize"], 3)

    def test_search_with_author_only_builds_query(self) -> None:
        response = self._mock_response()
        with mock.patch.object(self.client, "_fetch_json_url", return_value=response) as fetch_mock:
            results = self.client.search(author="Orwell", limit=2)

        self.assertEqual(len(results), 1)
        fetch_mock.assert_called_once()
        called_url, called_params = fetch_mock.call_args[0]
        self.assertEqual(called_url, ISBNDB_SEARCH_BOOKS_URL)
        self.assertEqual(called_params["q"], "Orwell")
        self.assertEqual(called_params["author"], "Orwell")
        self.assertEqual(called_params["pageSize"], 2)