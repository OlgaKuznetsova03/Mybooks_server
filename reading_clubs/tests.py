from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from books.models import Book, Author, Genre
from .models import (
    DiscussionPost,
    DiscussionPostReport,
    ReadingClub,
    ReadingNorm,
    ReadingParticipant,
)

User = get_user_model()


class ReadingClubModelTests(TestCase):
    def setUp(self):
        self.author = Author.objects.create(name="Автор")
        self.genre = Genre.objects.create(name="Жанр")
        self.book = Book.objects.create(title="Книга")
        self.book.authors.add(self.author)
        self.book.genres.add(self.genre)
        self.creator = User.objects.create_user(username="creator", password="pass12345")

    def test_status_transitions(self):
        today = date.today()
        club = ReadingClub.objects.create(
            book=self.book,
            creator=self.creator,
            title="Чтение",
            start_date=today,
            end_date=today + timedelta(days=3),
        )
        self.assertEqual(club.status, "active")

        club.start_date = today + timedelta(days=2)
        club.save(update_fields=["start_date"])
        self.assertEqual(club.status, "upcoming")

        club.start_date = today - timedelta(days=5)
        club.end_date = today - timedelta(days=1)
        club.save(update_fields=["start_date", "end_date"])
        self.assertEqual(club.status, "past")

    def test_message_count_uses_related_posts(self):
        club = ReadingClub.objects.create(
            book=self.book,
            creator=self.creator,
            title="Чтение",
            start_date=date.today(),
        )
        topic = ReadingNorm.objects.create(
            reading=club,
            title="Глава 1",
            order=1,
            discussion_opens_at=date.today(),
        )
        user = User.objects.create_user(username="reader", password="secret123")
        DiscussionPost.objects.create(topic=topic, author=self.creator, content="Первое сообщение")
        DiscussionPost.objects.create(topic=topic, author=user, content="Второе сообщение")

        annotated = ReadingClub.objects.with_message_count().get(pk=club.pk)
        self.assertEqual(annotated.message_count, 2)
        # Property should use cached annotated value without hitting the database again
        with self.assertNumQueries(0):
            self.assertEqual(annotated.message_count, 2)

    def test_unique_participation(self):
        club = ReadingClub.objects.create(
            book=self.book,
            creator=self.creator,
            title="Чтение",
            start_date=date.today(),
        )
        ReadingParticipant.objects.create(
            reading=club,
            user=self.creator,
            status=ReadingParticipant.Status.APPROVED,
        )
        with self.assertRaises(IntegrityError):
            ReadingParticipant.objects.create(
                reading=club,
                user=self.creator,
                status=ReadingParticipant.Status.APPROVED,
            )


class ReadingClubJoinViewTests(TestCase):
    def setUp(self):
        self.author = Author.objects.create(name="Автор")
        self.genre = Genre.objects.create(name="Жанр")
        self.book = Book.objects.create(title="Книга")
        self.book.authors.add(self.author)
        self.book.genres.add(self.genre)
        self.creator = User.objects.create_user(username="creator", password="pass12345")
        self.reader = User.objects.create_user(username="reader", password="pass12345")

    def test_open_join_auto_approved(self):
        club = ReadingClub.objects.create(
            book=self.book,
            creator=self.creator,
            title="Чтение",
            start_date=date.today(),
            join_policy=ReadingClub.JoinPolicy.OPEN,
        )
        self.client.login(username="reader", password="pass12345")
        response = self.client.post(reverse("reading_clubs:join", args=[club.slug]))
        self.assertEqual(response.status_code, 302)
        participation = ReadingParticipant.objects.get(reading=club, user=self.reader)
        self.assertEqual(participation.status, ReadingParticipant.Status.APPROVED)

    def test_request_join_creates_pending(self):
        club = ReadingClub.objects.create(
            book=self.book,
            creator=self.creator,
            title="Чтение",
            start_date=date.today(),
            join_policy=ReadingClub.JoinPolicy.REQUEST,
        )
        self.client.login(username="reader", password="pass12345")
        response = self.client.post(reverse("reading_clubs:join", args=[club.slug]))
        self.assertEqual(response.status_code, 302)
        participation = ReadingParticipant.objects.get(reading=club, user=self.reader)
        self.assertEqual(participation.status, ReadingParticipant.Status.PENDING)


class ReadingTopicDetailViewTests(TestCase):
    def setUp(self):
        self.author = Author.objects.create(name="Автор")
        self.genre = Genre.objects.create(name="Жанр")
        self.book = Book.objects.create(title="Книга")
        self.book.authors.add(self.author)
        self.book.genres.add(self.genre)
        self.creator = User.objects.create_user(username="creator", password="pass12345")
        self.reader = User.objects.create_user(username="reader", password="pass12345")
        self.reading = ReadingClub.objects.create(
            book=self.book,
            creator=self.creator,
            title="Чтение",
            start_date=date.today(),
        )
        self.topic = ReadingNorm.objects.create(
            reading=self.reading,
            title="Глава 1",
            order=1,
            discussion_opens_at=date.today(),
        )

    def test_posts_in_context(self):
        parent = DiscussionPost.objects.create(
            topic=self.topic,
            author=self.creator,
            content="Первое сообщение",
        )
        reply = DiscussionPost.objects.create(
            topic=self.topic,
            author=self.reader,
            content="Ответ",
            parent=parent,
        )
        response = self.client.get(
            reverse("reading_clubs:topic_detail", args=[self.reading.slug, self.topic.pk])
        )
        self.assertEqual(response.status_code, 200)
        posts = list(response.context["posts"])
        self.assertEqual([post.pk for post in posts], [parent.pk, reply.pk])


class DiscussionPostReportViewTests(TestCase):
    def setUp(self):
        author = Author.objects.create(name="Автор")
        genre = Genre.objects.create(name="Жанр")
        book = Book.objects.create(title="Книга")
        book.authors.add(author)
        book.genres.add(genre)
        self.creator = User.objects.create_user(username="creator", password="pass12345")
        self.reader = User.objects.create_user(username="reader", password="pass12345")
        self.reading = ReadingClub.objects.create(
            book=book,
            creator=self.creator,
            title="Чтение",
            start_date=date.today(),
        )
        self.topic = ReadingNorm.objects.create(
            reading=self.reading,
            title="Глава 1",
            order=1,
            discussion_opens_at=date.today(),
        )
        self.post = DiscussionPost.objects.create(
            topic=self.topic,
            author=self.creator,
            content="Сообщение для проверки",
        )

    def test_authenticated_user_can_report_foreign_post_once(self):
        self.client.login(username="reader", password="pass12345")
        url = reverse(
            "reading_clubs:post_report",
            args=[self.reading.slug, self.topic.pk, self.post.pk],
        )

        first_response = self.client.post(url, {"reason": "spam", "details": "Реклама"})
        second_response = self.client.post(url, {"reason": "spam", "details": "Повтор"})

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 302)
        self.assertEqual(DiscussionPostReport.objects.count(), 1)
        report = DiscussionPostReport.objects.get()
        self.assertEqual(report.reported_user, self.creator)
        self.assertEqual(report.content_snapshot, self.post.content)

    def test_user_cannot_report_own_post(self):
        self.client.login(username="creator", password="pass12345")
        url = reverse(
            "reading_clubs:post_report",
            args=[self.reading.slug, self.topic.pk, self.post.pk],
        )

        response = self.client.post(url, {"reason": "other"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(DiscussionPostReport.objects.exists())
