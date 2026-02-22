from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from books.models import Author, Book, Genre
from reading_clubs.models import ReadingClub
from reading_marathons.models import MarathonParticipant, MarathonTheme, ReadingMarathon
from shelves.models import Shelf, ShelfItem
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

    def test_home_feed_populates_all_sections_with_active_entities(self):
        today = timezone.localdate()

        reading_shelf = Shelf.objects.create(
            user=self.user,
            name='Читаю',
            is_default=True,
            is_public=True,
        )
        ShelfItem.objects.create(shelf=reading_shelf, book=self.book)

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

        self.client.force_authenticate(self.user)
        response = self.client.get('/api/v1/home/', secure=True)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload['active_clubs'][0]['id'], club.id)
        self.assertEqual(payload['active_marathons'][0]['id'], marathon.id)
        self.assertEqual(payload['reading_items'][0]['book']['title'], 'Книга в процессе')
        self.assertIn('reading_metrics', payload)

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