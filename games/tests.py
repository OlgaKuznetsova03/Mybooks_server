from decimal import Decimal
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from books.models import Book, Genre, ISBNModel, Rating
from shelves.models import BookProgress, Shelf, ShelfItem
from shelves.services import (
    DEFAULT_READ_SHELF,
    DEFAULT_READING_SHELF,
    get_home_library_shelf,
)

from .models import (
    BookExchangeAcceptedBook,
    BookExchangeChallenge,
    BookExchangeOffer,
    BookJourneyAssignment,
    ForgottenBookEntry,
    GameShelfBook,
    GameShelfPurchase,
    GameShelfState,
)
from .forms import BookJourneyAssignForm
from .services.book_exchange import BookExchangeGame
from .services.book_journey import BookJourneyMap
from .services.forgotten_books import ForgottenBooksGame
from .services.read_before_buy import ReadBeforeBuyGame


class GameCatalogViewTests(TestCase):
    def test_catalog_lists_active_and_upcoming_games(self):
        response = self.client.get(reverse("games:index"))
        self.assertEqual(response.status_code, 200)

        active_game = ReadBeforeBuyGame.get_game()
        self.assertContains(response, active_game.title)
        self.assertContains(response, BookJourneyMap.TITLE)
        self.assertContains(response, "Скоро появятся")
        self.assertContains(response, reverse("games:read_before_buy"))



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
            reverse("shelves:add_book_to_shelf", args=[other_book.pk]),
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
    def test_stage_count_is_15(self):
        self.assertEqual(BookJourneyMap.get_stage_count(), 15)

    def test_journey_map_view_renders(self):
        response = self.client.get(reverse("games:book_journey_map"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, BookJourneyMap.TITLE)
        self.assertContains(response, "15 заданий")


class BookJourneyInteractionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="explorer", password="secret123")
        self.client.login(username="explorer", password="secret123")
        self.book = Book.objects.create(title="Путешествие", synopsis="")
        self.other_book = Book.objects.create(title="Роман", synopsis="")
        self.home_shelf = get_home_library_shelf(self.user)
        ShelfItem.objects.get_or_create(shelf=self.home_shelf, book=self.book)
        ShelfItem.objects.get_or_create(shelf=self.home_shelf, book=self.other_book)

    def _get_default_shelf(self, name):
        return Shelf.objects.get(user=self.user, name=name)
    
    def test_assign_book_creates_assignment(self):
        response = self.client.post(
            reverse("games:book_journey_map"),
            {"action": "assign", "stage_number": 1, "book": self.book.pk},
        )
        self.assertRedirects(response, reverse("games:book_journey_map"))
        assignment = BookJourneyAssignment.objects.get(user=self.user, stage_number=1)
        self.assertEqual(assignment.book, self.book)
        self.assertEqual(assignment.status, BookJourneyAssignment.Status.IN_PROGRESS)

    def test_assign_book_moves_entry_to_reading_shelf(self):
        reading_shelf = self._get_default_shelf(DEFAULT_READING_SHELF)
        want_shelf = self._get_default_shelf(DEFAULT_WANT_SHELF)
        ShelfItem.objects.get_or_create(shelf=want_shelf, book=self.book)

        response = self.client.post(
            reverse("games:book_journey_map"),
            {"action": "assign", "stage_number": 1, "book": self.book.pk},
        )

        self.assertRedirects(response, reverse("games:book_journey_map"))
        self.assertTrue(
            ShelfItem.objects.filter(shelf=reading_shelf, book=self.book).exists()
        )
        self.assertFalse(
            ShelfItem.objects.filter(shelf=want_shelf, book=self.book).exists()
        )

    def test_assign_form_excludes_books_outside_allowed_shelves(self):
        custom_book = Book.objects.create(title="Секретная книга", synopsis="")
        custom_shelf = Shelf.objects.create(user=self.user, name="Любимые книги")
        ShelfItem.objects.create(shelf=custom_shelf, book=custom_book)
        reading_shelf = self._get_default_shelf(DEFAULT_READING_SHELF)
        ShelfItem.objects.get_or_create(shelf=reading_shelf, book=self.book)

        form = BookJourneyAssignForm(user=self.user)
        book_ids = set(form.fields["book"].queryset.values_list("id", flat=True))

        self.assertIn(self.book.id, book_ids)
        self.assertNotIn(custom_book.id, book_ids)

    def test_read_books_are_not_listed_in_assignment_form(self):
        read_book = Book.objects.create(title="Прочитанная", synopsis="")
        ShelfItem.objects.create(shelf=self.home_shelf, book=read_book)
        read_shelf = self._get_default_shelf(DEFAULT_READ_SHELF)
        ShelfItem.objects.get_or_create(shelf=read_shelf, book=read_book)

        form = BookJourneyAssignForm(user=self.user)
        book_ids = set(form.fields["book"].queryset.values_list("id", flat=True))

        self.assertNotIn(read_book.id, book_ids)

    def test_read_books_cannot_be_assigned(self):
        read_book = Book.objects.create(title="Архив", synopsis="")
        ShelfItem.objects.create(shelf=self.home_shelf, book=read_book)
        read_shelf = self._get_default_shelf(DEFAULT_READ_SHELF)
        ShelfItem.objects.get_or_create(shelf=read_shelf, book=read_book)

        form = BookJourneyAssignForm(
            {"stage_number": "1", "book": read_book.pk}, user=self.user
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            "Прочитанные книги нельзя прикреплять к заданию.",
            form.errors.get("__all__", []),
        )

    def test_only_one_active_assignment_allowed(self):
        self.client.post(
            reverse("games:book_journey_map"),
            {"action": "assign", "stage_number": 1, "book": self.book.pk},
        )
        response = self.client.post(
            reverse("games:book_journey_map"),
            {"action": "assign", "stage_number": 2, "book": self.other_book.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "У вас уже есть активное задание")
        self.assertFalse(
            BookJourneyAssignment.objects.filter(user=self.user, stage_number=2).exists()
        )

    def test_release_assignment(self):
        self.client.post(
            reverse("games:book_journey_map"),
            {"action": "assign", "stage_number": 1, "book": self.book.pk},
        )
        response = self.client.post(
            reverse("games:book_journey_map"),
            {"action": "release", "stage_number": 1},
        )
        self.assertRedirects(response, reverse("games:book_journey_map"))
        self.assertFalse(
            BookJourneyAssignment.objects.filter(user=self.user, stage_number=1).exists()
        )

    def test_assignment_completes_after_progress_and_review(self):
        self.client.post(
            reverse("games:book_journey_map"),
            {"action": "assign", "stage_number": 1, "book": self.book.pk},
        )
        BookProgress.objects.create(
            user=self.user,
            book=self.book,
            percent=Decimal("100"),
            current_page=0,
        )
        Rating.objects.create(book=self.book, user=self.user, review="Готово!")
        assignment = BookJourneyAssignment.objects.get(user=self.user, stage_number=1)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, BookJourneyAssignment.Status.COMPLETED)

    def test_release_blocked_for_completed_stage(self):
        self.client.post(
            reverse("games:book_journey_map"),
            {"action": "assign", "stage_number": 1, "book": self.book.pk},
        )
        BookProgress.objects.create(
            user=self.user,
            book=self.book,
            percent=Decimal("100"),
            current_page=0,
        )
        Rating.objects.create(book=self.book, user=self.user, review="Финал")
        assignment = BookJourneyAssignment.objects.get(user=self.user, stage_number=1)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, BookJourneyAssignment.Status.COMPLETED)
        response = self.client.post(
            reverse("games:book_journey_map"),
            {"action": "release", "stage_number": 1},
            follow=True,
        )
        self.assertContains(response, "Завершённое задание нельзя отменить")
        self.assertTrue(
            BookJourneyAssignment.objects.filter(user=self.user, stage_number=1).exists()
        )


class ForgottenBooksGameTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="collector", password="secret123")
        self.client.login(username="collector", password="secret123")
        self.home_shelf = get_home_library_shelf(self.user)
        self.books = []
        for index in range(1, 13):
            book = Book.objects.create(title=f"Книга {index}", synopsis="")
            ShelfItem.objects.get_or_create(shelf=self.home_shelf, book=book)
            self.books.append(book)

    def _fill_challenge(self):
        for book in self.books:
            success, _, _ = ForgottenBooksGame.add_book(self.user, book)
            self.assertTrue(success)

    def test_add_book_requires_home_library(self):
        outsider = Book.objects.create(title="Чужая книга", synopsis="")
        success, _, level = ForgottenBooksGame.add_book(self.user, outsider)
        self.assertFalse(success)
        self.assertEqual(level, "danger")

    def test_selection_waits_until_full_list(self):
        ForgottenBooksGame.add_book(self.user, self.books[0])
        selection = ForgottenBooksGame.ensure_monthly_selection(
            self.user, reference_date=date(2024, 1, 10)
        )
        self.assertIsNone(selection)

    def test_selection_assigns_unique_books_per_month(self):
        self._fill_challenge()
        with patch("games.services.forgotten_books.random.choice", side_effect=lambda seq: seq[0]):
            january = ForgottenBooksGame.ensure_monthly_selection(
                self.user, reference_date=date(2024, 1, 5)
            )
            february = ForgottenBooksGame.ensure_monthly_selection(
                self.user, reference_date=date(2024, 2, 5)
            )
        self.assertIsNotNone(january)
        self.assertIsNotNone(february)
        self.assertNotEqual(january.entry.pk, february.entry.pk)
        self.assertEqual(january.entry.selected_month, date(2024, 1, 1))
        self.assertEqual(february.entry.selected_month, date(2024, 2, 1))
        current = ForgottenBooksGame.get_current_selection(
            self.user, reference_date=date(2024, 1, 15)
        )
        self.assertEqual(current.entry.pk, january.entry.pk)

    def test_remove_entry_blocked_after_selection(self):
        self._fill_challenge()
        with patch("games.services.forgotten_books.random.choice", side_effect=lambda seq: seq[0]):
            selection = ForgottenBooksGame.ensure_monthly_selection(
                self.user, reference_date=date(2024, 1, 3)
            )
        entry = selection.entry
        success, _, level = ForgottenBooksGame.remove_entry(entry)
        self.assertFalse(success)
        self.assertEqual(level, "warning")

    def test_sync_updates_completion_fields(self):
        book = self.books[0]
        ForgottenBooksGame.add_book(self.user, book)
        entry = ForgottenBookEntry.objects.get(user=self.user, book=book)
        BookProgress.objects.create(user=self.user, book=book, percent=100)
        ForgottenBookEntry.sync_for_user_book(self.user, book)
        entry.refresh_from_db()
        self.assertIsNotNone(entry.finished_at)
        Rating.objects.create(user=self.user, book=book, review="Отличная книга")
        ForgottenBookEntry.sync_for_user_book(self.user, book)
        entry.refresh_from_db()
        self.assertTrue(entry.is_completed)

    def test_dashboard_view_requires_authentication(self):
        self.client.logout()
        response = self.client.get(reverse("games:forgotten_books"))
        self.assertEqual(response.status_code, 302)
        self.client.login(username="collector", password="secret123")
        response = self.client.get(reverse("games:forgotten_books"))
        self.assertEqual(response.status_code, 200)
        game = ForgottenBooksGame.get_game()
        self.assertContains(response, game.title)

class BookExchangeChallengeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="trader", password="secret123")
        self.other = User.objects.create_user(username="helper", password="secret123")
        self.genre = Genre.objects.create(name="Фэнтези")
        self.book = Book.objects.create(title="Драконья тропа", synopsis="Путь героя и дракона.")
        self.book.genres.add(self.genre)
        self.second_book = Book.objects.create(title="Город среди звёзд", synopsis="Покорение космоса")
        self.second_book.genres.add(self.genre)
        self.third_book = Book.objects.create(title="Тайна архива", synopsis="Старинные рукописи и тайны")
        self.third_book.genres.add(self.genre)

        self.read_shelf = Shelf.objects.create(
            user=self.other,
            name=DEFAULT_READ_SHELF,
            is_default=True,
        )
        ShelfItem.objects.create(shelf=self.read_shelf, book=self.book)
        ShelfItem.objects.create(shelf=self.read_shelf, book=self.second_book)
        ShelfItem.objects.create(shelf=self.read_shelf, book=self.third_book)

    def test_start_new_challenge_creates_managed_shelf(self):
        challenge = BookExchangeGame.start_new_challenge(
            self.user,
            target_books=3,
            genres=[self.genre],
        )
        self.assertEqual(challenge.round_number, 1)
        self.assertFalse(challenge.shelf.is_public)
        self.assertTrue(challenge.shelf.is_managed)
        self.assertEqual(challenge.shelf.name, BookExchangeGame.SHELF_NAME)
        self.assertEqual(challenge.genres.count(), 1)
        self.assertTrue(BookExchangeGame.has_active_challenge(self.user))

    def test_start_new_challenge_reuses_managed_shelf(self):
        first = BookExchangeGame.start_new_challenge(
            self.user,
            target_books=1,
            genres=[self.genre],
        )
        first.shelf.refresh_from_db()
        self.assertTrue(first.shelf.is_managed)
        BookExchangeChallenge.objects.filter(pk=first.pk).update(
            status=BookExchangeChallenge.Status.COMPLETED
        )

        second = BookExchangeGame.start_new_challenge(
            self.user,
            target_books=2,
            genres=[],
        )
        self.assertEqual(second.round_number, 2)
        self.assertEqual(second.shelf_id, first.shelf_id)
        
    def test_decline_limit_enforced(self):
        challenge = BookExchangeGame.start_new_challenge(
            self.user, target_books=3, genres=[self.genre]
        )
        BookExchangeGame.offer_book(challenge, offered_by=self.other, book=self.book)
        BookExchangeGame.offer_book(challenge, offered_by=self.other, book=self.second_book)
        BookExchangeGame.offer_book(challenge, offered_by=self.other, book=self.third_book)

        offers = list(
            BookExchangeOffer.objects.filter(challenge=challenge)
            .order_by("created_at")
        )
        success, _, level = BookExchangeGame.decline_offer(
            offers[0], acting_user=self.user
        )
        self.assertTrue(success)
        self.assertEqual(level, "info")
        success, message, level = BookExchangeGame.decline_offer(
            offers[1], acting_user=self.user
        )
        self.assertFalse(success)
        self.assertEqual(level, "warning")
        self.assertIn("Нельзя отклонить", message)

    def test_accept_offer_sets_deadline_and_creates_entry(self):
        challenge = BookExchangeGame.start_new_challenge(
            self.user, target_books=1, genres=[self.genre]
        )
        BookExchangeGame.offer_book(challenge, offered_by=self.other, book=self.book)
        offer = BookExchangeOffer.objects.get(challenge=challenge, book=self.book)
        success, _, level = BookExchangeGame.accept_offer(offer, acting_user=self.user)
        self.assertTrue(success)
        self.assertEqual(level, "success")
        challenge.refresh_from_db()
        self.assertIsNotNone(challenge.deadline_at)
        entry = BookExchangeAcceptedBook.objects.get(challenge=challenge, book=self.book)
        self.assertIsNotNone(entry)
        self.assertTrue(
            ShelfItem.objects.filter(shelf=challenge.shelf, book=self.book).exists()
        )

    def test_completion_requires_review_and_progress(self):
        challenge = BookExchangeGame.start_new_challenge(
            self.user, target_books=1, genres=[self.genre]
        )
        BookExchangeGame.offer_book(challenge, offered_by=self.other, book=self.book)
        offer = BookExchangeOffer.objects.get(challenge=challenge, book=self.book)
        BookExchangeGame.accept_offer(offer, acting_user=self.user)
        entry = BookExchangeAcceptedBook.objects.get(challenge=challenge, book=self.book)

        BookProgress.objects.create(user=self.user, book=self.book, percent=Decimal("100"))
        BookExchangeAcceptedBook.sync_for_user_book(self.user, self.book)
        entry.refresh_from_db()
        self.assertIsNotNone(entry.finished_at)
        self.assertFalse(entry.is_completed)

        Rating.objects.create(user=self.user, book=self.book, review="Прочитано")
        BookExchangeAcceptedBook.sync_for_user_book(self.user, self.book)
        entry.refresh_from_db()
        challenge.refresh_from_db()
        self.assertTrue(entry.is_completed)
        self.assertEqual(challenge.status, BookExchangeChallenge.Status.COMPLETED)

    def test_dashboard_view_renders(self):
        self.client.login(username="trader", password="secret123")
        response = self.client.get(reverse("games:book_exchange"))
        self.assertEqual(response.status_code, 200)
        game = BookExchangeGame.get_game()
        self.assertContains(response, game.title)