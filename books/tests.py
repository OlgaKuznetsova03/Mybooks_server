from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

# Create your tests here.
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from .models import Author, Genre, Publisher, Book, ISBNModel


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
                "authors": [str(self.author.pk)],
                "genres": [str(self.genre.pk)],
                "publisher": [str(self.publisher.pk)],
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
