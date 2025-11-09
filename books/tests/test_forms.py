import json

from django.test import TestCase

from books.forms import BookForm
from books.models import Genre


class BookFormGenresTests(TestCase):
    def test_uses_metadata_subjects_when_field_empty(self):
        metadata = {
            "9781234567890": {
                "subjects": ["Фэнтези", "Приключения"],
            }
        }

        form = BookForm(
            data={
                "title": "Тестовая книга",
                "authors": "Автор Один",
                "genres": "",
                "isbn_metadata": json.dumps(metadata, ensure_ascii=False),
            }
        )

        self.assertTrue(form.is_valid())
        genres = form.cleaned_data["genres"]
        self.assertEqual({genre.name for genre in genres}, {"Фэнтези", "Приключения"})

    def test_normalizes_genre_input(self):
        form = BookForm(
            data={
                "title": "Тестовая книга",
                "authors": "Автор Один",
                "genres": "детективы, современная проза",
            }
        )

        self.assertTrue(form.is_valid())
        genres = form.cleaned_data["genres"]
        self.assertEqual({genre.name for genre in genres}, {"Детектив", "Современная литература"})
        self.assertEqual(Genre.objects.count(), 2)


class BookFormPageCountTests(TestCase):
    def test_accepts_valid_page_count(self):
        form = BookForm(
            data={
                "title": "Тест",
                "authors": "Автор",
                "genres": "Фэнтези",
                "page_count": 350,
            }
        )

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["page_count"], 350)

    def test_rejects_zero_page_count(self):
        form = BookForm(
            data={
                "title": "Тест",
                "authors": "Автор",
                "genres": "Фэнтези",
                "page_count": 0,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("page_count", form.errors)