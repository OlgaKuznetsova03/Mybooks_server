from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from books.models import Book, ISBNModel
from shelves.models import Shelf, ShelfItem

from .models import GameShelfBook, GameShelfState
from .services.read_before_buy import ReadBeforeBuyGame


class ReadBeforeBuyGameTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="gamer", password="secret123")
        self.client.login(username="gamer", password="secret123")
        self.isbn = ISBNModel.objects.create(
            isbn="9789999999999",
            isbn13="9789999999999",
            title="Epic Tome",
            total_pages=620,
        )
        self.book = Book.objects.create(title="Epic Tome", synopsis="")
        self.book.primary_isbn = self.isbn
        self.book.save()
        self.book.isbn.add(self.isbn)

        self.shelf = Shelf.objects.create(user=self.user, name="Бумажные книги", is_public=False)
        self.state = ReadBeforeBuyGame.enable_for_shelf(self.user, self.shelf)
        ShelfItem.objects.create(shelf=self.shelf, book=self.book)

    def test_award_pages_accumulates_points_and_logs(self):
        ReadBeforeBuyGame.award_pages(self.user, self.book, 150)

        state = GameShelfState.objects.get(pk=self.state.pk)
        self.assertEqual(state.points_balance, 150)
        entry = GameShelfBook.objects.get(state=state, book=self.book)
        self.assertEqual(entry.pages_logged, 150)

    def test_handle_review_adds_bonus_once(self):
        ReadBeforeBuyGame.award_pages(self.user, self.book, 200)
        ReadBeforeBuyGame.handle_review(self.user, self.book, "Отличная книга!")
        state = GameShelfState.objects.get(pk=self.state.pk)
        self.assertEqual(state.books_reviewed, 1)
        entry = GameShelfBook.objects.get(state=state, book=self.book)
        self.assertTrue(entry.bonus_awarded)
        self.assertGreater(state.points_balance, 200)

        # повторная обработка не должна увеличивать показатели
        ReadBeforeBuyGame.handle_review(self.user, self.book, "Повторно")
        state.refresh_from_db()
        self.assertEqual(state.books_reviewed, 1)

    def test_purchase_requires_points(self):
        ReadBeforeBuyGame.award_pages(self.user, self.book, ReadBeforeBuyGame.PURCHASE_COST)
        new_book = Book.objects.create(title="Новая книга", synopsis="")
        success, _, level = ReadBeforeBuyGame.add_book_to_shelf(self.user, self.shelf, new_book)
        self.assertTrue(success)
        self.assertEqual(level, "success")
        self.assertTrue(ShelfItem.objects.filter(shelf=self.shelf, book=new_book).exists())
        state = GameShelfState.objects.get(pk=self.state.pk)
        self.assertEqual(state.books_purchased, 1)

    def test_purchase_via_view_blocks_without_points(self):
        other_book = Book.objects.create(title="Недостаточно баллов", synopsis="")
        response = self.client.post(
            reverse("add_book_to_shelf", args=[other_book.pk]),
            {"shelf": self.shelf.id},
        )
        self.assertRedirects(response, reverse("book_detail", args=[other_book.pk]))
        self.assertFalse(ShelfItem.objects.filter(shelf=self.shelf, book=other_book).exists())

    def test_dashboard_view_renders(self):
        response = self.client.get(reverse("games:read_before_buy"))
        self.assertEqual(response.status_code, 200)
        game = ReadBeforeBuyGame.get_game()
        self.assertContains(response, game.title)