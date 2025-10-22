import json

from django.test import TestCase

from books.forms import BookForm


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