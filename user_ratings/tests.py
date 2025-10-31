from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from books.models import Author, Book, Rating

from .models import LeaderboardPeriod, UserPointEvent
from .services import award_for_book_completion, award_for_review

User = get_user_model()


class UserRatingAwardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="reader", password="test-pass")
        self.author = Author.objects.create(name="Test Author")

    def _create_book(self, title: str) -> Book:
        book = Book.objects.create(title=title)
        book.authors.add(self.author)
        return book

    def test_book_completion_limited_per_day(self):
        first = self._create_book("Book One")
        second = self._create_book("Book Two")
        third = self._create_book("Book Three")

        created_events = [
            award_for_book_completion(self.user, first),
            award_for_book_completion(self.user, second),
            award_for_book_completion(self.user, third),
        ]
        events = [event for event in created_events if event is not None]
        self.assertEqual(len(events), 2)
        self.assertEqual(
            UserPointEvent.objects.filter(
                user=self.user,
                event_type=UserPointEvent.EventType.BOOK_COMPLETED,
            ).count(),
            2,
        )

    def test_review_award_limited_per_day(self):
        events = []
        for index in range(4):
            book = self._create_book(f"Review Book {index}")
            rating = Rating.objects.create(
                book=book,
                user=self.user,
                review="Отлично!",
                score=8,
            )
            events.append(award_for_review(self.user, rating))
        stored = UserPointEvent.objects.filter(
            user=self.user,
            event_type=UserPointEvent.EventType.REVIEW_WRITTEN,
        )
        self.assertEqual(stored.count(), 3)
        self.assertEqual(len([event for event in events if event is not None]), 3)

    def test_book_award_unique_per_book(self):
        book = self._create_book("Unique Book")
        first_event = award_for_book_completion(self.user, book)
        second_event = award_for_book_completion(self.user, book)
        self.assertIsNotNone(first_event)
        self.assertIsNone(second_event)


class UserRatingLeaderboardTests(TestCase):
    def setUp(self):
        self.user_one = User.objects.create_user(username="first", password="pass1")
        self.user_two = User.objects.create_user(username="second", password="pass2")

    def _create_event(self, *, user, points: int, delta: timedelta) -> UserPointEvent:
        event = UserPointEvent.objects.create(
            user=user,
            event_type=UserPointEvent.EventType.CLUB_DISCUSSION,
            points=points,
        )
        event.created_at = timezone.now() - delta
        event.save(update_fields=["created_at"])
        return event

    def test_leaderboard_period_filters(self):
        events = [
            self._create_event(user=self.user_one, points=10, delta=timedelta(minutes=10)),
            self._create_event(user=self.user_one, points=20, delta=timedelta(days=3)),
            self._create_event(user=self.user_one, points=30, delta=timedelta(days=40)),
            self._create_event(user=self.user_two, points=25, delta=timedelta(days=1)),
            self._create_event(user=self.user_two, points=5, delta=timedelta(days=400)),
        ]
        for period in LeaderboardPeriod:
            start = period.period_start()
            expected_totals: dict[int, int] = {}
            for event in events:
                if event.created_at >= start:
                    expected_totals[event.user_id] = expected_totals.get(event.user_id, 0) + event.points
            leaderboard = UserPointEvent.get_leaderboard(period)
            result_totals = {row["user"].id: row["points"] for row in leaderboard}
            self.assertEqual(result_totals, expected_totals)