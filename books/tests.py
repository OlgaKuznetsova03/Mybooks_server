import tempfile
from unittest import mock
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from shelves.models import Shelf, ShelfItem
from shelves.services import ALL_DEFAULT_READ_SHELF_NAMES

from .models import Author, Genre, Publisher, Book, ISBNModel
from .services import register_book_edition
from .api_clients import ExternalBookData, ISBNDBClient


def make_isbn13(seed: int) -> str:
    """Generate a deterministic valid ISBN-13 for tests."""

    prefix = f"9780000{seed:07d}"
    prefix12 = prefix[:12]
    total = 0
    for index, char in enumerate(prefix12):
        digit = int(char)
        total += digit if index % 2 == 0 else digit * 3
    check = (10 - (total % 10)) % 10
    return f"{prefix12}{check}"


class ISBNDBClientTests(TestCase):
    def test_parse_book_transliterates_russian_entries(self):
        client = ISBNDBClient()
        payload = {
            "title": "Moskva i Peterburg",
            "title_long": "Puteshestvie po Rossii",
            "authors": ["Ivan Ivanov", "Petr Petrov"],
            "publisher": "Izdatelstvo Nauka",
            "date_published": "2020",
            "pages": "320",
            "binding": "Tverdyi pereplet",
            "subjects": ["Science Fiction"],
            "language": "Russian",
            "synopsis": "Podrobnoe opisanie knigi",
            "isbn": "1234567890",
            "isbn13": "9781234567897",
            "isbns": ["9781234567897"],
            "image": "https://example.com/cover.jpg",
            "image_l": "https://example.com/cover-large.jpg",
            "url": "https://isbndb.com/book/9781234567897",
        }

        result = client._parse_book(payload)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.title, "Москва и Петербург")
        self.assertEqual(result.subtitle, "Путешествие по России")
        self.assertEqual(result.authors, ["Иван Иванов", "Петр Петров"])
        self.assertEqual(result.publishers, ["Издателство Наука"])
        self.assertEqual(result.languages, ["Русский"])
        self.assertEqual(result.subjects, ["Научная фантастика"])
        self.assertEqual(result.description, "Подробное описание книги")
        self.assertEqual(result.physical_format, "Твердый переплет")
        self.assertEqual(result.cover_url, "https://example.com/cover-large.jpg")
        self.assertEqual(result.source_url, "https://isbndb.com/book/9781234567897")
        self.assertIn("1234567890", result.isbn_10)
        self.assertIn("9781234567897", result.isbn_13)

    def test_translate_subjects_to_russian(self):
        client = ISBNDBClient()
        payload = {
            "title": "Test title",
            "authors": ["Author"],
            "publisher": "Publisher",
            "date_published": "2023",
            "subjects": [
                "Science Fiction",
                "sci-fi",
                "Unknown Topic",
                "Space Opera & Fantasy",
            ],
            "language": "English",
            "isbn": "1234567890",
        }

        result = client._parse_book(payload)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.subjects, ["Научная фантастика", "Космическая опера"])


class GenreModelTests(TestCase):
    def test_slug_generated_from_name(self):
        genre = Genre.objects.create(name="Научная фантастика")
        self.assertEqual(genre.slug, "nauchnaya-fantastika")
        self.assertTrue(genre.slug.isascii())
        self.assertEqual(
            genre.get_absolute_url(),
            reverse("genre_detail", args=[genre.slug]),
        )

    def test_slug_uniqueness_suffix(self):
        base = Genre.objects.create(name="Фэнтези")
        variant = Genre.objects.create(name="Фэнтези!")

        self.assertEqual(base.slug, "fentezi")
        self.assertTrue(variant.slug.startswith("fentezi"))
        self.assertNotEqual(base.slug, variant.slug)


class ISBNModelGetImageURLTests(TestCase):
    def _create_isbn(self, suffix: int, image: str = "book_covers/sample.jpg") -> ISBNModel:
        value = make_isbn13(100 + suffix)
        return ISBNModel.objects.create(
            isbn=value,
            isbn13=value,
            title=f"Edition {suffix}",
            image=image,
        )

    @override_settings(MEDIA_URL="/media/")
    def test_returns_absolute_path_with_default_media_url(self):
        isbn = self._create_isbn(0)
        self.assertEqual(isbn.get_image_url(), "/media/book_covers/sample.jpg")

    @override_settings(MEDIA_URL="media/")
    def test_relative_media_url_is_prefixed_with_slash(self):
        isbn = self._create_isbn(1)
        self.assertEqual(isbn.get_image_url(), "/media/book_covers/sample.jpg")

    @override_settings(MEDIA_URL="https://cdn.example.com/media")
    def test_absolute_media_url_kept_absolute(self):
        isbn = self._create_isbn(2)
        self.assertEqual(
            isbn.get_image_url(),
            "https://cdn.example.com/media/book_covers/sample.jpg",
        )

    @override_settings(MEDIA_URL="//cdn.example.com/media/")
    def test_protocol_relative_media_url_kept_protocol_relative(self):
        isbn = self._create_isbn(3)
        self.assertEqual(
            isbn.get_image_url(),
            "//cdn.example.com/media/book_covers/sample.jpg",
        )


class BookCreateViewTests(TestCase):
    def setUp(self):
        self.author = Author.objects.create(name="Тестовый автор")
        self.genre = Genre.objects.create(name="Фантастика")
        self.publisher = Publisher.objects.create(name="Тестовое издательство")

    def test_login_required(self):
        response = self.client.get(reverse("book_create"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_authenticated_user_can_create_book(self):
        user = User.objects.create_user(username="reader", password="pass12345")
        self.client.login(username="reader", password="pass12345")

        response = self.client.post(
            reverse("book_create"),
            {
                "title": "Новая книга",
                "authors": "Тестовый автор",
                "genres": "Фантастика",
                "publisher": "Тестовое издательство",
                "synopsis": "Краткое описание",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Book.objects.count(), 1)
        book = Book.objects.get()
        self.assertRedirects(response, reverse("book_detail", args=[book.pk]))
        self.assertContains(response, "Новая книга")

    def test_adding_new_edition_preserves_existing_cover(self):
        user = User.objects.create_user(username="editor", password="pass12345")
        self.client.login(username="editor", password="pass12345")

        author = Author.objects.create(name="Автор")
        genre = Genre.objects.create(name="Жанр")
        publisher = Publisher.objects.create(name="Издательство")
        existing_isbn = ISBNModel.objects.create(
            isbn="9785171020590",
            isbn13="9785171020590",
            title="Первое издание",
            image="book_covers/original.jpg",
        )

        with tempfile.TemporaryDirectory() as tmpdir, override_settings(MEDIA_ROOT=tmpdir):
            book = Book.objects.create(title="Книга", synopsis="Описание", language="ru")
            book.authors.add(author)
            book.genres.add(genre)
            book.publisher.add(publisher)
            book.isbn.add(existing_isbn)
            book.primary_isbn = existing_isbn
            book.cover.save(
                "orig.jpg",
                SimpleUploadedFile("orig.jpg", b"old-cover", content_type="image/jpeg"),
                save=True,
            )

            response = self.client.post(
                reverse("book_create"),
                data={
                    "title": "Книга",
                    "authors": "Автор",
                    "genres": "Жанр",
                    "publisher": "Издательство",
                    "isbn": "9785171020590, 9785171209162",
                    "duplicate_resolution": f"edition:{book.pk}",
                    "cover": SimpleUploadedFile(
                        "new.jpg",
                        b"new-cover",
                        content_type="image/jpeg",
                    ),
                },
                follow=True,
            )

            self.assertEqual(response.status_code, 200)

            book.refresh_from_db()
            self.assertTrue(book.cover.name.endswith("orig.jpg"))

            new_isbn = ISBNModel.objects.get(isbn="9785171209162")
            self.assertTrue(new_isbn.image)
            self.assertTrue(new_isbn.image.endswith("new.jpg"))

            existing_isbn.refresh_from_db()
            self.assertEqual(existing_isbn.image, "book_covers/original.jpg")


class GenreDetailViewTests(TestCase):
    def setUp(self):
        self.author = Author.objects.create(name="Автор")
        self.genre = Genre.objects.create(name="Детектив")

        self.book = Book.objects.create(title="Первое дело")
        self.book.authors.add(self.author)
        self.book.genres.add(self.genre)

        self.another_book = Book.objects.create(title="Второе дело")
        self.another_book.authors.add(self.author)
        self.another_book.genres.add(self.genre)

    def test_genre_detail_lists_books(self):
        response = self.client.get(self.genre.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.book.title)
        self.assertContains(response, self.another_book.title)

    def test_book_detail_displays_genre_shelf(self):
        response = self.client.get(reverse("book_detail", args=[self.book.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ещё книги в этих жанрах")
        self.assertContains(response, self.another_book.title)


class RegisterBookEditionTests(TestCase):
    def setUp(self):
        self.author = Author.objects.create(name="Автор")
        self.genre = Genre.objects.create(name="Жанр")
        self.publisher = Publisher.objects.create(name="Издательство")

    def test_attaches_new_isbn_to_existing_book(self):
        book = Book.objects.create(title="Книга", synopsis="Описание")
        book.authors.add(self.author)
        book.genres.add(self.genre)
        book.publisher.add(self.publisher)

        old_value = make_isbn13(1)
        isbn = ISBNModel.objects.create(isbn=old_value, isbn13=old_value, title="Старое издание")
        book.isbn.add(isbn)
        book.primary_isbn = isbn
        book.save(update_fields=["primary_isbn"])

        new_value = make_isbn13(2)
        new_isbn = ISBNModel.objects.create(isbn=new_value, isbn13=new_value, title="Новое издание")

        result = register_book_edition(
            title="Книга",
            authors=[self.author],
            genres=[self.genre],
            publishers=[self.publisher],
            isbn_entries=[new_isbn],
            synopsis="Описание",
        )

        self.assertFalse(result.created)
        self.assertEqual(result.book.pk, book.pk)
        self.assertEqual(result.added_isbns, [new_isbn])
        self.assertEqual(book.isbn.count(), 2)

    def test_force_new_creates_separate_book(self):
        existing = Book.objects.create(title="Книга", synopsis="Описание")
        existing.authors.add(self.author)

        existing_value = make_isbn13(3)
        isbn_existing = ISBNModel.objects.create(isbn=existing_value, isbn13=existing_value, title="Издание")
        existing.isbn.add(isbn_existing)

        new_value = make_isbn13(4)
        isbn_new = ISBNModel.objects.create(isbn=new_value, isbn13=new_value, title="Новое издание")

        result = register_book_edition(
            title="Книга",
            authors=[self.author],
            isbn_entries=[isbn_new],
            force_new=True,
        )

        self.assertTrue(result.created)
        self.assertNotEqual(result.book.pk, existing.pk)
        self.assertEqual(result.added_isbns, [isbn_new])

    def test_manual_publisher_overrides_metadata(self):
        isbn_value = make_isbn13(9)
        isbn = ISBNModel.objects.create(isbn=isbn_value, isbn13=isbn_value)
        user_publisher = Publisher.objects.create(name="Пользовательское издательство")

        metadata = {
            isbn_value: {
                "publishers": ["API Publisher"],
            }
        }

        result = register_book_edition(
            title="Книга",
            authors=[self.author],
            publishers=[user_publisher],
            isbn_entries=[isbn],
            isbn_metadata=metadata,
        )

        self.assertIn(isbn, result.added_isbns)
        isbn.refresh_from_db()
        self.assertEqual(isbn.publisher, user_publisher.name)

    def test_applies_isbn_metadata(self):
        isbn_value = make_isbn13(5)
        isbn = ISBNModel.objects.create(isbn=isbn_value, isbn13=isbn_value)

        metadata = {
            isbn_value: {
                "title": "API Title",
                "authors": ["Новый Автор"],
                "publishers": ["API Publisher"],
                "publish_date": "2021",
                "number_of_pages": 320,
                "physical_format": "Hardcover",
                "subjects": ["Фэнтези", "Приключения"],
                "languages": ["rus"],
                "description": "Описание из API",
                "cover_url": "https://example.org/cover.jpg",
                "isbn_13_list": [isbn_value],
            }
        }

        result = register_book_edition(
            title="API Title",
            authors=[self.author],
            isbn_entries=[isbn],
            isbn_metadata=metadata,
        )

        self.assertIn(isbn, result.added_isbns)

        isbn.refresh_from_db()
        self.assertEqual(isbn.title, "API Title")
        self.assertEqual(isbn.publisher, "API Publisher")
        self.assertEqual(isbn.publish_date, "2021")
        self.assertEqual(isbn.total_pages, 320)
        self.assertEqual(isbn.binding, "Hardcover")
        self.assertEqual(isbn.subjects, "Фэнтези, Приключения")
        self.assertEqual(isbn.language, "Русский")
        self.assertEqual(isbn.synopsis, "Описание из API")
        self.assertEqual(isbn.image, "https://example.org/cover.jpg")
        self.assertEqual(isbn.isbn13, "9781234567897")
        self.assertIn("Новый Автор", list(isbn.authors.values_list("name", flat=True)))

    @mock.patch("books.services.download_cover_from_url")
    def test_downloads_cover_from_metadata_when_no_upload(self, mock_download):
        isbn_value = make_isbn13(6)
        isbn = ISBNModel.objects.create(isbn=isbn_value, isbn13=isbn_value)

        metadata = {
            isbn_value: {
                "cover_url": "https://covers.example.com/api.jpg",
            }
        }

        mock_download.return_value = ContentFile(b"image-bytes", name="api-cover.jpg")

        with tempfile.TemporaryDirectory() as tmpdir, override_settings(MEDIA_ROOT=tmpdir):
            result = register_book_edition(
                title="API Title",
                authors=[self.author],
                isbn_entries=[isbn],
                isbn_metadata=metadata,
            )

            mock_download.assert_called_once_with("https://covers.example.com/api.jpg")

            book = result.book
            book.refresh_from_db()
            self.assertTrue(book.cover.name)
            self.assertTrue(book.cover.name.startswith("book_covers/"))
            self.assertTrue(book.cover.storage.exists(book.cover.name))

            isbn.refresh_from_db()
            self.assertEqual(isbn.image, book.cover.name)


class BookLookupViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="lookup", password="pass12345")
        self.client.login(username="lookup", password="pass12345")
        self.author = Author.objects.create(name="Автор Поиска")
        self.book = Book.objects.create(title="Поисковая книга", synopsis="")
        self.book.authors.add(self.author)
        isbn_value = make_isbn13(7)
        self.isbn = ISBNModel.objects.create(
            isbn=isbn_value,
            isbn13=isbn_value,
            title="Существующее издание",
        )
        self.book.isbn.add(self.isbn)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("book_lookup"), {"title": "Поисковая"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_rejects_empty_query(self):
        response = self.client.get(reverse("book_lookup"))
        self.assertEqual(response.status_code, 400)

    def test_returns_local_results(self):
        response = self.client.get(reverse("book_lookup"), {"title": "Поисковая"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["local_results"]), 1)
        self.assertEqual(data["local_results"][0]["title"], "Поисковая книга")
        self.assertEqual(data["external_results"], [])

    @mock.patch("books.views.isbndb_client")
    def test_fetches_external_results_when_forced(self, mock_client):
        mock_client.search.return_value = [
            ExternalBookData(
                title="API Книга",
                authors=["API Автор"],
                publishers=["API Издательство"],
                publish_date="2020",
                number_of_pages=250,
                physical_format="Paperback",
                subjects=["Приключения"],
                languages=["eng"],
                isbn_10=["1234567890"],
                isbn_13=["1234567890123"],
                description="Описание", 
                cover_url="https://example.com/cover.jpg",
                source_url="https://isbndb.com/book/123",
            )
        ]

        response = self.client.get(
            reverse("book_lookup"),
            {"title": "Неизвестная", "force_external": "1"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["local_results"], [])
        self.assertEqual(len(data["external_results"]), 1)
        self.assertEqual(data["external_results"][0]["title"], "API Книга")
        self.assertIn("metadata", data["external_results"][0])
        mock_client.search.assert_called_once()


class BookLookupAPIViewTests(TestCase):
    def setUp(self):
        self.author = Author.objects.create(name="Автор Поиска")
        self.book = Book.objects.create(title="Поисковая книга", synopsis="")
        self.book.authors.add(self.author)
        isbn_value = make_isbn13(8)
        self.isbn = ISBNModel.objects.create(
            isbn=isbn_value,
            isbn13=isbn_value,
            title="Существующее издание",
        )
        self.book.isbn.add(self.isbn)
        self.isbn.authors.add(self.author)

    def test_rejects_empty_query(self):
        response = self.client.get(reverse("book_lookup_api"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Укажите название, автора или ISBN.")

    def test_search_by_author(self):
        response = self.client.get(reverse("book_lookup_api"), {"author": "Поиска"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["local_results"]), 1)
        self.assertEqual(data["local_results"][0]["title"], "Поисковая книга")

    def test_search_by_title(self):
        response = self.client.get(reverse("book_lookup_api"), {"title": "Поисковая"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["local_results"]), 1)
        self.assertEqual(data["local_results"][0]["title"], "Поисковая книга")

    def test_search_by_isbn_metadata_title(self):
        self.isbn.title = "Особое издание поиска"
        self.isbn.save(update_fields=["title"])

        response = self.client.get(
            reverse("book_lookup_api"),
            {"title": "Особое"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["local_results"]), 1)
        self.assertEqual(data["local_results"][0]["title"], "Поисковая книга")

    def test_search_by_isbn_metadata_author(self):
        edition_author = Author.objects.create(name="Редактор Поиска")
        self.isbn.authors.add(edition_author)

        response = self.client.get(reverse("book_lookup_api"), {"author": "Редактор"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["local_results"]), 1)
        self.assertEqual(data["local_results"][0]["title"], "Поисковая книга")

    @mock.patch("books.views.isbndb_client")
    def test_external_results_when_forced(self, mock_client):
        mock_client.search.return_value = [
            ExternalBookData(
                title="API Книга",
                authors=["API Автор"],
                publishers=["API Издательство"],
                publish_date="2020",
                number_of_pages=250,
                physical_format="Paperback",
                subjects=["Приключения"],
                languages=["eng"],
                isbn_10=["1234567890"],
                isbn_13=["1234567890123"],
                description="Описание",
                cover_url="https://example.com/cover.jpg",
                source_url="https://isbndb.com/book/123",
            )
        ]

        response = self.client.get(
            reverse("book_lookup_api"),
            {"author": "Неизвестный", "force_external": "1", "external_limit": "3"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["local_results"], [])
        self.assertEqual(len(data["external_results"]), 1)
        self.assertEqual(data["external_results"][0]["title"], "API Книга")
        mock_client.search.assert_called_once()


class RateBookMovesShelfTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="reader", password="pass12345")
        self.client.login(username="reader", password="pass12345")
        self.book = Book.objects.create(title="Shelfed Book", synopsis="")

    def test_rating_moves_book_from_reading_to_read_shelf(self):
        reading_shelf = Shelf.objects.get(user=self.user, name="Читаю")
        read_shelf = Shelf.objects.filter(
            user=self.user,
            name__in=ALL_DEFAULT_READ_SHELF_NAMES,
        ).first()
        self.assertIsNotNone(read_shelf)
        ShelfItem.objects.get_or_create(shelf=reading_shelf, book=self.book)

        response = self.client.post(
            reverse("rate_book", args=[self.book.pk]),
            {
                "book": self.book.pk,
                "score": 8,
                "review": "Отличная книга!",
            },
        )

        self.assertRedirects(response, reverse("book_detail", args=[self.book.pk]))
        self.assertFalse(
            ShelfItem.objects.filter(shelf=reading_shelf, book=self.book).exists()
        )
        self.assertTrue(
            ShelfItem.objects.filter(shelf=read_shelf, book=self.book).exists()
        )