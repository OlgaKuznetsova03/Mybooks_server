from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from books.models import Author, Book, Genre, ISBNModel
from reading_clubs.models import ReadingClub
from reading_marathons.models import MarathonParticipant, MarathonTheme, ReadingMarathon
from decimal import Decimal

from accounts.models import Profile
from shelves.models import BookProgress, ReadingLog, Shelf, ShelfItem
from shelves.services import READING_PROGRESS_LABEL


class HomeFeedApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username='reader',
            email='reader@example.com',
            password='StrongPass123!'
        )

        author = Author.objects.create(name='Автор Теста')
        genre = Genre.objects.create(name='Фэнтези')
        self.book = Book.objects.create(title='Книга в процессе')
        self.book.authors.add(author)
        self.book.genres.add(genre)

    def test_home_feed_returns_reading_items_from_legacy_reading_shelf_name(self):
        legacy_shelf = Shelf.objects.create(
            user=self.user,
            name=READING_PROGRESS_LABEL,
            is_default=True,
            is_public=True,
        )
        ShelfItem.objects.create(shelf=legacy_shelf, book=self.book)

        self.client.force_authenticate(self.user)
        response = self.client.get('/api/v1/home/', secure=True)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(len(payload['reading_items']), 1)
        self.assertEqual(payload['reading_items'][0]['book']['title'], 'Книга в процессе')
        self.assertIn('tracker_url', payload['reading_items'][0])

    def test_home_feed_populates_all_sections_with_active_entities(self):
        today = timezone.localdate()

        reading_shelf = Shelf.objects.create(
            user=self.user,
            name='Читаю',
            is_default=True,
            is_public=True,
        )
        ShelfItem.objects.create(shelf=reading_shelf, book=self.book)
        progress = BookProgress.objects.create(
            user=self.user,
            book=self.book,
            percent=Decimal('37.5'),
            current_page=120,
        )

        club = ReadingClub.objects.create(
            book=self.book,
            creator=self.user,
            title='Совместное чтение',
            start_date=today - timedelta(days=1),
        )

        marathon = ReadingMarathon.objects.create(
            creator=self.user,
            title='Осенний марафон',
            start_date=today - timedelta(days=1),
            slug='autumn-marathon',
        )
        MarathonTheme.objects.create(marathon=marathon, title='Тема 1', order=1)
        MarathonParticipant.objects.create(marathon=marathon, user=self.user)

        Profile.objects.get_or_create(user=self.user)
        ReadingLog.objects.create(
            progress=progress,
            pages_equivalent=Decimal('22'),
            log_date=today,
        )

        self.client.force_authenticate(self.user)
        response = self.client.get('/api/v1/home/', secure=True)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload['active_clubs'][0]['id'], club.id)
        self.assertEqual(payload['active_marathons'][0]['id'], marathon.id)
        self.assertEqual(payload['reading_items'][0]['book']['title'], 'Книга в процессе')
        self.assertEqual(payload['reading_items'][0]['progress_id'], progress.id)
        self.assertEqual(payload['reading_items'][0]['tracker_url'], f'/tracker/{progress.id}/')
        self.assertEqual(len(payload['reading_updates']), 1)
        self.assertEqual(payload['reading_updates'][0]['book_title'], 'Книга в процессе')
        self.assertIn('reading_metrics', payload)

    def test_home_feed_falls_back_to_upcoming_entities_when_no_active(self):
        today = timezone.localdate()

        upcoming_club = ReadingClub.objects.create(
            book=self.book,
            creator=self.user,
            title='Скоро стартуем',
            start_date=today + timedelta(days=2),
        )

        upcoming_marathon = ReadingMarathon.objects.create(
            creator=self.user,
            title='Скоро марафон',
            start_date=today + timedelta(days=3),
            slug='soon-marathon',
        )

        self.client.force_authenticate(self.user)
        response = self.client.get('/api/v1/home/', secure=True)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload['active_clubs'][0]['id'], upcoming_club.id)
        self.assertEqual(payload['active_marathons'][0]['id'], upcoming_marathon.id)

class ApiUrlsCompatibilityTests(APITestCase):
    def test_mobile_endpoints_work_without_trailing_slash(self):
        endpoints = [
            '/api/v1/home',
            '/api/v1/books',
            '/api/v1/reading-clubs',
            '/api/v1/marathons',
        ]

        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                response = self.client.get(endpoint, secure=True)
                self.assertEqual(response.status_code, status.HTTP_200_OK)


class InvalidMobileTokenFallbackTests(APITestCase):
    def setUp(self):
        author = Author.objects.create(name='Проверка токена')
        genre = Genre.objects.create(name='Роман')
        book = Book.objects.create(title='Книга из каталога')
        book.authors.add(author)
        book.genres.add(genre)

    def test_get_books_works_with_invalid_token_header(self):
        self.client.credentials(HTTP_AUTHORIZATION='Token invalid-token')

        response = self.client.get('/api/v1/books/', secure=True)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload['count'], 1)

    def test_post_books_still_rejects_invalid_token_header(self):
        self.client.credentials(HTTP_AUTHORIZATION='Token invalid-token')

        response = self.client.post(
            '/api/v1/books/',
            {
                'title': 'Новая книга',
                'author_names': ['Автор'],
                'genre_names': ['Жанр'],
            },
            format='json',
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

class BookListSearchTests(APITestCase):
    def setUp(self):
        self.author = Author.objects.create(name='Найденный Автор')
        self.genre = Genre.objects.create(name='Детектив')

        self.book = Book.objects.create(title='Тайна старого маяка')
        self.book.authors.add(self.author)
        self.book.genres.add(self.genre)

    def test_books_search_supports_q_param(self):
        response = self.client.get('/api/v1/books/?q=маяка', secure=True)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(payload['results'][0]['id'], self.book.id)

    def test_books_search_supports_isbn_value(self):
        isbn = ISBNModel.objects.create(
            isbn='1234567890',
            isbn13='9781234567897',
            title=self.book.title,
        )
        self.book.isbn.add(isbn)

        response = self.client.get('/api/v1/books/?q=9781234567897', secure=True)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(payload['results'][0]['id'], self.book.id)