from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from books.models import Book, ISBNModel
from shelves.models import ShelfItem
from shelves.services import get_home_library_shelf

from .models import GameShelfBook, GameShelfPurchase, GameShelfState
from .services.book_journey import BookJourneyMap
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

        self.home_shelf = get_home_library_shelf(self.user)
        self.state = ReadBeforeBuyGame.enable_for_shelf(self.user, self.home_shelf)
        ShelfItem.objects.get_or_create(shelf=self.home_shelf, book=self.book)

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
        success, _, level = ReadBeforeBuyGame.add_book_to_shelf(self.user, self.home_shelf, new_book)
        self.assertTrue(success)
        self.assertEqual(level, "success")
        self.assertTrue(ShelfItem.objects.filter(shelf=self.home_shelf, book=new_book).exists())
        state = GameShelfState.objects.get(pk=self.state.pk)
        self.assertEqual(state.books_purchased, 1)

    def test_ensure_completion_awarded_adds_missing_pages(self):
        # книга уже находится на полке, но страницы ещё не засчитаны
        ReadBeforeBuyGame.ensure_completion_awarded(self.user, self.home_shelf, self.book)
        state = GameShelfState.objects.get(pk=self.state.pk)
        self.assertEqual(state.points_balance, self.isbn.total_pages)

        # повторный вызов не должен менять баланс
        ReadBeforeBuyGame.ensure_completion_awarded(self.user, self.home_shelf, self.book)
        state.refresh_from_db()
        self.assertEqual(state.points_balance, self.isbn.total_pages)

    def test_bulk_purchase_spends_points_and_creates_records(self):
        ReadBeforeBuyGame.award_pages(self.user, self.book, ReadBeforeBuyGame.PURCHASE_COST * 2)
        state = GameShelfState.objects.get(pk=self.state.pk)

        success, _, level = ReadBeforeBuyGame.spend_points_for_bulk_purchase(state, 2)

        self.assertTrue(success)
        self.assertEqual(level, "success")
        state.refresh_from_db()
        self.assertEqual(state.points_balance, 0)
        self.assertEqual(state.books_purchased, 2)
        self.assertEqual(GameShelfPurchase.objects.filter(state=state).count(), 2)

    def test_purchase_via_view_blocks_without_points(self):
        other_book = Book.objects.create(title="Недостаточно баллов", synopsis="")
        response = self.client.post(
            reverse("add_book_to_shelf", args=[other_book.pk]),
            {"shelf": self.home_shelf.id},
        )
        self.assertRedirects(response, reverse("book_detail", args=[other_book.pk]))
        self.assertFalse(ShelfItem.objects.filter(shelf=self.home_shelf, book=other_book).exists())

    def test_bulk_purchase_action_via_dashboard(self):
        ReadBeforeBuyGame.award_pages(self.user, self.book, ReadBeforeBuyGame.PURCHASE_COST * 2)
        state = GameShelfState.objects.get(pk=self.state.pk)

        response = self.client.post(
            reverse("games:read_before_buy"),
            {"action": "bulk_purchase", "state_id": state.pk, "count": 2},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        state.refresh_from_db()
        self.assertEqual(state.points_balance, 0)
        self.assertEqual(state.books_purchased, 2)

    def test_pages_before_game_start_are_ignored(self):
        started_at = timezone.now()
        GameShelfState.objects.filter(pk=self.state.pk).update(started_at=started_at)
        state = GameShelfState.objects.get(pk=self.state.pk)
        earlier = started_at - timedelta(days=3)

        ReadBeforeBuyGame.award_pages(
            self.user,
            self.book,
            120,
            occurred_at=earlier,
        )

        state.refresh_from_db()
        self.assertEqual(state.points_balance, 0)
        self.assertFalse(GameShelfBook.objects.filter(state=state, book=self.book).exists())

    def test_dashboard_view_renders(self):
        response = self.client.get(reverse("games:read_before_buy"))
        self.assertEqual(response.status_code, 200)
        game = ReadBeforeBuyGame.get_game()
        self.assertContains(response, game.title)


class BookJourneyMapTests(TestCase):
    def test_stage_count_is_30(self):
        self.assertEqual(BookJourneyMap.get_stage_count(), 30)

    def test_journey_map_view_renders(self):
        response = self.client.get(reverse("games:book_journey_map"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, BookJourneyMap.TITLE)
        self.assertContains(response, "30 этапов")