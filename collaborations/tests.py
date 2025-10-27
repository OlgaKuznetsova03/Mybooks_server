from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from books.models import Book

from .forms import AuthorOfferForm
from .models import (
    AuthorOffer,
    AuthorOfferResponse,
    AuthorOfferResponseComment,
    BloggerPlatformPresence,
    BloggerRequest,
    Collaboration,
    ReviewPlatform,
)


class OfferFormTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.author = user_model.objects.create_user(
            username="author", password="password123", email="author@example.com"
        )
        self.other_user = user_model.objects.create_user(
            username="outsider",
            password="password123",
            email="outsider@example.com",
        )

        author_group, _ = Group.objects.get_or_create(name="author")
        self.author.groups.add(author_group)

        self.own_book = Book.objects.create(title="Моя книга")
        self.own_book.contributors.add(self.author)
        self.other_book = Book.objects.create(title="Чужая книга")
        self.other_book.contributors.add(self.other_user)

    def test_author_offer_form_limits_books_to_contributors(self):
        form = AuthorOfferForm(author=self.author)
        books = list(form.fields["book"].queryset)
        self.assertEqual(books, [self.own_book])

    def test_author_offer_form_without_author_has_empty_queryset(self):
        form = AuthorOfferForm()
        books = list(form.fields["book"].queryset)
        self.assertEqual(books, [])



class OfferUpdateViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        author_group, _ = Group.objects.get_or_create(name="author")

        self.author = user_model.objects.create_user(
            username="main_author", password="password123", email="main@example.com"
        )
        self.author.groups.add(author_group)

        self.other_author = user_model.objects.create_user(
            username="other_author", password="password123", email="other@example.com"
        )
        self.other_author.groups.add(author_group)

        self.book = Book.objects.create(title="Книга автора")
        self.book.contributors.add(self.author)

        self.offer = AuthorOffer.objects.create(
            author=self.author,
            title="Первое предложение",
            review_requirements="Опубликовать отзыв",
            book=self.book,
        )

    def _payload(self, **extra):
        data = {
            "title": "Обновлённое предложение",
            "book": self.book.pk,
            "offered_format": AuthorOffer.BookFormat.ELECTRONIC,
            "synopsis": "Новые детали",
            "review_requirements": "Обновлённые требования",
            "text_review_length": 0,
            "expected_platforms": [],
            "video_review_type": AuthorOffer.VideoReviewType.NONE,
            "video_requires_unboxing": "",
            "video_requires_aesthetics": "",
            "video_requires_review": "on",
            "considers_paid_collaboration": "",
            "allow_regular_users": "",
            "is_active": "on",
        }
        data.update(extra)
        return data

    def test_author_can_update_own_offer(self):
        self.client.force_login(self.author)
        response = self.client.post(
            reverse("collaborations:offer_edit", args=[self.offer.pk]),
            self._payload(synopsis="Свежие детали"),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.synopsis, "Свежие детали")
        self.assertEqual(self.offer.title, "Обновлённое предложение")

    def test_other_author_gets_404(self):
        self.client.force_login(self.other_author)
        response = self.client.get(reverse("collaborations:offer_edit", args=[self.offer.pk]))
        self.assertEqual(response.status_code, 404)


class BloggerRequestUpdateViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        blogger_group, _ = Group.objects.get_or_create(name="blogger")

        self.blogger = user_model.objects.create_user(
            username="blogger_main",
            password="password123",
            email="blogger@example.com",
        )
        self.blogger.groups.add(blogger_group)

        self.other_blogger = user_model.objects.create_user(
            username="blogger_other",
            password="password123",
            email="other_blogger@example.com",
        )
        self.other_blogger.groups.add(blogger_group)

        self.platform = ReviewPlatform.objects.create(name="Телеграм")

        self.request_obj = BloggerRequest.objects.create(
            blogger=self.blogger,
            title="Ищу новинки",
            review_platform_links="https://t.me/old",
        )
        self.request_obj.review_formats.add(self.platform)
        self.platform_presence = BloggerPlatformPresence.objects.create(
            request=self.request_obj,
            platform=self.platform,
            followers_count=1200,
        )

    def _form_payload(self, **extra):
        data = {
            "title": "Обновлённая заявка",
            "preferred_genres": [],
            "accepts_paper": "on",
            "accepts_electronic": "on",
            "review_formats": [str(self.platform.pk)],
            "review_platform_links": "https://t.me/new",
            "additional_info": "Новые условия сотрудничества",
            "collaboration_type": BloggerRequest.CollaborationType.BARTER_OR_PAID,
            "collaboration_terms": "Свяжитесь для обсуждения",
            "is_active": "on",
            "bloggerplatformpresence_set-TOTAL_FORMS": "1",
            "bloggerplatformpresence_set-INITIAL_FORMS": "1",
            "bloggerplatformpresence_set-MIN_NUM_FORMS": "0",
            "bloggerplatformpresence_set-MAX_NUM_FORMS": "1000",
            "bloggerplatformpresence_set-0-id": str(self.platform_presence.pk),
            "bloggerplatformpresence_set-0-platform": str(self.platform.pk),
            "bloggerplatformpresence_set-0-custom_platform_name": "",
            "bloggerplatformpresence_set-0-followers_count": "2000",
            "bloggerplatformpresence_set-0-DELETE": "",
        }
        data.update(extra)
        return data

    def test_blogger_can_update_own_request(self):
        self.client.force_login(self.blogger)
        url = reverse("collaborations:blogger_request_edit", args=[self.request_obj.pk])
        response = self.client.post(
            url,
            self._form_payload(additional_info="Актуальные условия"),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        self.request_obj.refresh_from_db()
        self.platform_presence.refresh_from_db()

        self.assertEqual(self.request_obj.title, "Обновлённая заявка")
        self.assertEqual(
            self.request_obj.review_platform_links,
            "https://t.me/new",
        )
        self.assertEqual(self.platform_presence.followers_count, 2000)
        self.assertEqual(
            self.request_obj.additional_info,
            "Актуальные условия",
        )

    def test_other_blogger_receives_404(self):
        self.client.force_login(self.other_blogger)
        url = reverse("collaborations:blogger_request_edit", args=[self.request_obj.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class OfferResponseViewsTests(TestCase):
    def setUp(self):
        self.UserModel = get_user_model()
        self.author = self.UserModel.objects.create_user(
            username="author",
            password="password123",
            email="author@example.com",
        )
        self.blogger = self.UserModel.objects.create_user(
            username="blogger",
            password="password123",
            email="blogger@example.com",
        )
        self.reader = self.UserModel.objects.create_user(
            username="reader",
            password="password123",
            email="reader@example.com",
        )

        author_group, _ = Group.objects.get_or_create(name="author")
        blogger_group, _ = Group.objects.get_or_create(name="blogger")
        self.author.groups.add(author_group)
        self.blogger.groups.add(blogger_group)

        self.offer = AuthorOffer.objects.create(
            author=self.author,
            title="Test Offer",
            review_requirements="Post an honest review",
        )

        self.response = AuthorOfferResponse.objects.create(
            offer=self.offer,
            respondent=self.blogger,
            message="Готов рассказать о книге",
            platform_links="https://example.com/profile",
        )

    def test_author_can_accept_response_and_create_collaboration(self):
        self.client.force_login(self.author)
        deadline = date.today() + timedelta(days=7)
        url = reverse("collaborations:offer_response_accept", args=[self.response.pk])

        response = self.client.post(url, {"deadline": deadline.isoformat()})

        self.assertRedirects(response, reverse("collaborations:offer_responses"))

        self.response.refresh_from_db()
        self.assertEqual(self.response.status, AuthorOfferResponse.Status.ACCEPTED)

        collaboration = Collaboration.objects.get(offer=self.offer, partner=self.blogger)
        self.assertEqual(collaboration.author, self.author)
        self.assertEqual(collaboration.deadline, deadline)
        self.assertEqual(collaboration.status, Collaboration.Status.NEGOTIATION)
        self.assertFalse(collaboration.author_confirmed)
        self.assertFalse(collaboration.partner_confirmed)
        self.assertTrue(collaboration.author_approved)
        self.assertFalse(collaboration.partner_approved)
        self.assertEqual(collaboration.review_links, "")

    def test_author_can_decline_response_and_cancel_collaboration(self):
        collaboration = Collaboration.objects.create(
            offer=self.offer,
            author=self.author,
            partner=self.blogger,
            deadline=date.today() + timedelta(days=14),
            status=Collaboration.Status.ACTIVE,
        )

        self.client.force_login(self.author)
        url = reverse("collaborations:offer_response_decline", args=[self.response.pk])
        response = self.client.post(url)

        self.assertRedirects(response, reverse("collaborations:offer_responses"))

        self.response.refresh_from_db()
        self.assertEqual(self.response.status, AuthorOfferResponse.Status.DECLINED)

        collaboration.refresh_from_db()
        self.assertEqual(collaboration.status, Collaboration.Status.CANCELLED)
        self.assertFalse(collaboration.author_approved)
        self.assertFalse(collaboration.partner_approved)

    def test_partner_can_confirm_collaboration_after_author_accepts(self):
        self.client.force_login(self.author)
        deadline = date.today() + timedelta(days=7)
        accept_url = reverse("collaborations:offer_response_accept", args=[self.response.pk])
        self.client.post(accept_url, {"deadline": deadline.isoformat()})

        collaboration = Collaboration.objects.get(offer=self.offer, partner=self.blogger)

        self.client.force_login(self.blogger)
        approval_url = reverse("collaborations:collaboration_approval", args=[collaboration.pk])
        new_deadline = date.today() + timedelta(days=10)
        response = self.client.post(
            approval_url,
            {"deadline": new_deadline.isoformat()},
        )

        self.assertRedirects(
            response,
            reverse("collaborations:collaboration_detail", args=[collaboration.pk]),
        )

        collaboration.refresh_from_db()
        self.assertTrue(collaboration.author_approved)
        self.assertTrue(collaboration.partner_approved)
        self.assertEqual(collaboration.deadline, new_deadline)

    def test_non_author_redirected_from_response_list(self):
        self.client.force_login(self.blogger)
        url = reverse("collaborations:offer_responses")
        response = self.client.get(url)
        self.assertRedirects(response, reverse("collaborations:offer_list"))

    def test_participants_can_open_discussion(self):
        self.client.force_login(self.author)
        url = reverse("collaborations:offer_response_detail", args=[self.response.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        self.client.force_login(self.blogger)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_author_can_post_comment_on_pending_response(self):
        self.client.force_login(self.author)
        url = reverse("collaborations:offer_response_detail", args=[self.response.pk])
        response = self.client.post(url, {"text": "Уточните формат и сроки"})
        self.assertRedirects(response, url)

        comment_exists = AuthorOfferResponseComment.objects.filter(
            response=self.response,
            author=self.author,
            text="Уточните формат и сроки",
        ).exists()
        self.assertTrue(comment_exists)

    def test_cannot_comment_when_response_not_pending(self):
        self.response.status = AuthorOfferResponse.Status.ACCEPTED
        self.response.save(update_fields=["status"])

        self.client.force_login(self.author)
        url = reverse("collaborations:offer_response_detail", args=[self.response.pk])
        response = self.client.post(url, {"text": "Попробуем договориться"})
        self.assertRedirects(response, url)
        self.assertFalse(
            AuthorOfferResponseComment.objects.filter(
                response=self.response,
                text="Попробуем договориться",
            ).exists()
        )

    def test_non_participant_cannot_access_discussion(self):
        outsider = self.UserModel.objects.create_user(
            username="outsider",
            password="password123",
            email="outsider@example.com",
        )
        self.client.force_login(outsider)
        url = reverse("collaborations:offer_response_detail", args=[self.response.pk])
        response = self.client.get(url)
        self.assertRedirects(response, reverse("collaborations:offer_list"))

    def test_reader_can_respond_when_offer_allows(self):
        self.offer.allow_regular_users = True
        self.offer.save(update_fields=["allow_regular_users"])

        self.client.force_login(self.reader)
        response = self.client.post(
            reverse("collaborations:offer_respond", args=[self.offer.pk]),
            {"platform_links": "", "message": "Готов поделиться впечатлениями"},
        )

        self.assertRedirects(
            response,
            reverse("collaborations:offer_detail", args=[self.offer.pk]),
        )
        exists = AuthorOfferResponse.objects.filter(
            offer=self.offer,
            respondent=self.reader,
        ).exists()
        self.assertTrue(exists)