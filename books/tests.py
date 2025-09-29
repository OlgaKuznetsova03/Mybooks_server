import tempfile

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from shelves.models import Shelf, ShelfItem

from .models import Author, Genre, Publisher, Book, ISBNModel
from .services import register_book_edition


class ISBNModelGetImageURLTests(TestCase):
    def _create_isbn(self, suffix: int, image: str = "book_covers/sample.jpg") -> ISBNModel:
        return ISBNModel.objects.create(
            isbn=f"123456789{suffix}",
            isbn13=f"123456789012{suffix}",
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

        isbn = ISBNModel.objects.create(isbn="1234567890", title="Старое издание")
        book.isbn.add(isbn)
        book.primary_isbn = isbn
        book.save(update_fields=["primary_isbn"])

        new_isbn = ISBNModel.objects.create(isbn="1234567890123", title="Новое издание")

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

        isbn_existing = ISBNModel.objects.create(isbn="0000000000", title="Издание")
        existing.isbn.add(isbn_existing)

        isbn_new = ISBNModel.objects.create(isbn="0000000000000", title="Новое издание")

        result = register_book_edition(
            title="Книга",
            authors=[self.author],
            isbn_entries=[isbn_new],
            force_new=True,
        )

        self.assertTrue(result.created)
        self.assertNotEqual(result.book.pk, existing.pk)
        self.assertEqual(result.added_isbns, [isbn_new])


class RateBookMovesShelfTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="reader", password="pass12345")
        self.client.login(username="reader", password="pass12345")
        self.book = Book.objects.create(title="Shelfed Book", synopsis="")

    def test_rating_moves_book_from_reading_to_read_shelf(self):
        reading_shelf = Shelf.objects.get(user=self.user, name="Читаю")
        read_shelf = Shelf.objects.get(user=self.user, name="Прочитал")
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