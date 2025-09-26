from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

# Create your tests here.
from .models import Author, Genre, Publisher, Book


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

