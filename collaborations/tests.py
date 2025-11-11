from datetime import date, timedelta
from io import BytesIO
import shutil
import tempfile
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from books.models import Book

from .forms import AuthorOfferForm, BloggerRequestForm
from .models import (
    AuthorOffer,
    AuthorOfferResponse,
    AuthorOfferResponseComment,
    BloggerPlatformPresence,
    BloggerRequest,
    BloggerRequestResponse,
    BloggerRequestResponseComment,
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


class BloggerRequestFormTests(TestCase):
    def setUp(self):
        self.platform = ReviewPlatform.objects.create(name="Instagram")

    def test_requires_platform_and_goal_for_bloggers(self):
        form = BloggerRequestForm(
            data={
                "title": "Совместный проект",
                "preferred_genres": [],
                "accepts_paper": "on",
                "accepts_electronic": "on",
                "review_formats": [],
                "review_platform_links": "",
                "additional_info": "",
                "collaboration_type": BloggerRequest.CollaborationType.BARTER,
                "collaboration_terms": "",
                "target_audience": BloggerRequest.TargetAudience.BLOGGERS,
                "blogger_collaboration_platform": "",
                "blogger_collaboration_platform_other": "",
                "blogger_collaboration_goal": "",
                "blogger_collaboration_goal_other": "",
                "is_active": "on",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("blogger_collaboration_platform", form.errors)
        self.assertIn("blogger_collaboration_goal", form.errors)

    def test_validates_goal_details_for_other_option(self):
        form = BloggerRequestForm(
            data={
                "title": "Совместный проект",
                "preferred_genres": [],
                "accepts_paper": "on",
                "accepts_electronic": "on",
                "review_formats": [],
                "review_platform_links": "",
                "additional_info": "",
                "collaboration_type": BloggerRequest.CollaborationType.BARTER,
                "collaboration_terms": "",
                "target_audience": BloggerRequest.TargetAudience.BLOGGERS,
                "blogger_collaboration_platform": str(self.platform.pk),
                "blogger_collaboration_platform_other": "",
                "blogger_collaboration_goal": BloggerRequest.BloggerCollaborationGoal.OTHER,
                "blogger_collaboration_goal_other": "",
                "is_active": "on",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("blogger_collaboration_goal_other", form.errors)

    def test_accepts_known_goal_with_platform(self):
        form = BloggerRequestForm(
            data={
                "title": "Совместный проект",
                "preferred_genres": [],
                "accepts_paper": "on",
                "accepts_electronic": "on",
                "review_formats": [],
                "review_platform_links": "",
                "additional_info": "",
                "collaboration_type": BloggerRequest.CollaborationType.BARTER,
                "collaboration_terms": "",
                "target_audience": BloggerRequest.TargetAudience.BLOGGERS,
                "blogger_collaboration_platform": str(self.platform.pk),
                "blogger_collaboration_platform_other": "",
                "blogger_collaboration_goal": BloggerRequest.BloggerCollaborationGoal.GIVEAWAY,
                "blogger_collaboration_goal_other": "",
                "is_active": "on",
            }
        )
        self.assertTrue(form.is_valid())


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
            "target_audience": BloggerRequest.TargetAudience.AUTHORS,
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

    def test_acceptance_moves_discussion_to_collaboration(self):
        AuthorOfferResponseComment.objects.create(
            response=self.response,
            author=self.author,
            text="Проверим дедлайны",
        )
        AuthorOfferResponseComment.objects.create(
            response=self.response,
            author=self.blogger,
            text="Могу успеть к концу месяца",
        )

        self.client.force_login(self.author)
        deadline = date.today() + timedelta(days=5)
        accept_url = reverse("collaborations:offer_response_accept", args=[self.response.pk])
        self.client.post(accept_url, {"deadline": deadline.isoformat()})

        collaboration = Collaboration.objects.get(offer=self.offer, partner=self.blogger)
        messages = list(collaboration.messages.order_by("created_at"))

        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0].author, self.blogger)
        self.assertEqual(messages[0].text, self.response.message)
        self.assertEqual(messages[1].author, self.author)
        self.assertEqual(messages[1].text, "Проверим дедлайны")
        self.assertEqual(messages[2].author, self.blogger)
        self.assertEqual(messages[2].text, "Могу успеть к концу месяца")

        self.assertFalse(
            AuthorOfferResponseComment.objects.filter(response=self.response).exists()
        )

    def test_accepted_response_hidden_from_my_responses(self):
        self.client.force_login(self.author)
        deadline = date.today() + timedelta(days=3)
        accept_url = reverse("collaborations:offer_response_accept", args=[self.response.pk])
        self.client.post(accept_url, {"deadline": deadline.isoformat()})

        self.response.refresh_from_db()
        self.assertEqual(self.response.status, AuthorOfferResponse.Status.ACCEPTED)

        self.client.force_login(self.blogger)
        list_url = reverse("collaborations:collaboration_list")
        response = self.client.get(list_url)

        my_responses = list(response.context["my_offer_responses"])
        self.assertFalse(any(item.pk == self.response.pk for item in my_responses))
        self.assertEqual(response.context["pending_response_count"], 0)

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

    def test_unread_offer_response_comment_shows_in_notifications(self):
        self.client.force_login(self.blogger)
        detail_url = reverse("collaborations:offer_response_detail", args=[self.response.pk])
        self.client.post(detail_url, {"text": "Есть пара вопросов по срокам"})

        self.response.refresh_from_db()
        self.assertEqual(self.response.last_activity_by_id, self.blogger.id)
        self.assertIsNotNone(self.response.last_activity_at)

        self.client.force_login(self.author)
        notifications_url = reverse("collaborations:collaboration_notifications")
        response = self.client.get(notifications_url)
        unread_threads = list(response.context["unread_offer_threads"])
        self.assertTrue(any(item.pk == self.response.pk for item in unread_threads))

        # Просмотр обсуждения снимает уведомление
        self.client.get(detail_url)
        response = self.client.get(notifications_url)
        self.assertFalse(response.context["unread_offer_threads"])

    def test_collaboration_message_triggers_notification(self):
        self.client.force_login(self.author)
        deadline = date.today() + timedelta(days=5)
        accept_url = reverse("collaborations:offer_response_accept", args=[self.response.pk])
        self.client.post(accept_url, {"deadline": deadline.isoformat()})

        collaboration = Collaboration.objects.get(offer=self.offer, partner=self.blogger)

        self.client.force_login(self.blogger)
        collaboration_url = reverse("collaborations:collaboration_detail", args=[collaboration.pk])
        self.client.post(collaboration_url, {"text": "Готов обсудить план работы"})

        collaboration.refresh_from_db()
        self.assertEqual(collaboration.last_activity_by_id, self.blogger.id)

        self.client.force_login(self.author)
        notifications_url = reverse("collaborations:collaboration_notifications")
        response = self.client.get(notifications_url)
        unread_collaborations = list(response.context["unread_collaborations"])
        self.assertTrue(any(item.pk == collaboration.pk for item in unread_collaborations))

        # Ответ автора убирает уведомление
        self.client.post(collaboration_url, {"text": "Получил сообщение"})
        response = self.client.get(notifications_url)
        self.assertFalse(response.context["unread_collaborations"])


class BloggerRequestResponseWorkflowTests(TestCase):
    def setUp(self):
        self.UserModel = get_user_model()
        self.author_group, _ = Group.objects.get_or_create(name="author")
        self.blogger_group, _ = Group.objects.get_or_create(name="blogger")

        self.blogger = self.UserModel.objects.create_user(
            username="owner",
            password="password123",
            email="owner@example.com",
        )
        self.blogger.groups.add(self.blogger_group)

        self.author = self.UserModel.objects.create_user(
            username="author_user",
            password="password123",
            email="author@example.com",
        )
        self.author.groups.add(self.author_group)

        self.other_blogger = self.UserModel.objects.create_user(
            username="partner_blogger",
            password="password123",
            email="partner@example.com",
        )
        self.other_blogger.groups.add(self.blogger_group)

        self.book = Book.objects.create(title="Книга для сотрудничества")
        self.book.contributors.add(self.author)

        self.request = BloggerRequest.objects.create(
            blogger=self.blogger,
            title="Ищу новых авторов",
            collaboration_terms="Обсудим условия",
        )

    def test_author_response_saves_book_and_activity(self):
        self.client.force_login(self.author)
        url = reverse("collaborations:blogger_request_respond", args=[self.request.pk])
        response = self.client.post(
            url,
            {"message": "Готов предложить роман", "book": self.book.pk},
        )

        self.assertRedirects(
            response,
            reverse("collaborations:blogger_request_detail", args=[self.request.pk]),
        )

        response_obj = BloggerRequestResponse.objects.get(
            request=self.request, responder=self.author
        )
        self.assertEqual(response_obj.book, self.book)
        self.assertEqual(
            response_obj.responder_type,
            BloggerRequestResponse.ResponderType.AUTHOR,
        )
        self.assertEqual(response_obj.platform_link, "")
        self.assertEqual(response_obj.last_activity_by, self.author)
        self.assertIsNotNone(response_obj.responder_last_read_at)
        self.assertIsNone(response_obj.blogger_last_read_at)

    def test_blogger_can_respond_with_platform_link(self):
        blogger_request = BloggerRequest.objects.create(
            blogger=self.blogger,
            title="Ищу блогеров",
            target_audience=BloggerRequest.TargetAudience.BLOGGERS,
        )

        self.client.force_login(self.other_blogger)
        url = reverse("collaborations:blogger_request_respond", args=[blogger_request.pk])
        response = self.client.post(
            url,
            {
                "message": "Готов обсудить совместный проект",
                "platform_link": "https://t.me/example",
            },
        )

        self.assertRedirects(
            response,
            reverse("collaborations:blogger_request_detail", args=[blogger_request.pk]),
        )

        response_obj = BloggerRequestResponse.objects.get(
            request=blogger_request, responder=self.other_blogger
        )
        self.assertEqual(
            response_obj.responder_type,
            BloggerRequestResponse.ResponderType.BLOGGER,
        )
        self.assertEqual(response_obj.platform_link, "https://t.me/example")
        self.assertIsNone(response_obj.book)

    def test_acceptance_creates_collaboration_and_moves_history(self):
        response_obj = BloggerRequestResponse.objects.create(
            request=self.request,
            responder=self.author,
            responder_type=BloggerRequestResponse.ResponderType.AUTHOR,
            message="Предлагаю роман месяца",
            book=self.book,
        )
        BloggerRequestResponseComment.objects.create(
            response=response_obj,
            author=self.author,
            text="Готов обсудить дедлайн",
        )
        BloggerRequestResponseComment.objects.create(
            response=response_obj,
            author=self.blogger,
            text="Предлагаю до конца месяца",
        )

        self.client.force_login(self.blogger)
        url = reverse("collaborations:blogger_request_response_accept", args=[response_obj.pk])
        deadline = date.today() + timedelta(days=10)
        response = self.client.post(url, {"deadline": deadline.isoformat()})
        self.assertRedirects(response, reverse("collaborations:blogger_request_responses"))

        response_obj.refresh_from_db()
        self.assertEqual(response_obj.status, BloggerRequestResponse.Status.ACCEPTED)

        collaboration = Collaboration.objects.get(request=self.request, author=self.author)
        self.assertEqual(collaboration.partner, self.blogger)
        self.assertEqual(collaboration.deadline, deadline)
        self.assertEqual(collaboration.status, Collaboration.Status.NEGOTIATION)

        messages = list(collaboration.messages.order_by("created_at"))
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0].author, self.author)
        self.assertEqual(messages[0].text, "Предлагаю роман месяца")
        self.assertEqual(messages[1].author, self.author)
        self.assertEqual(messages[1].text, "Готов обсудить дедлайн")
        self.assertEqual(messages[2].author, self.blogger)
        self.assertEqual(messages[2].text, "Предлагаю до конца месяца")
        self.assertFalse(
            BloggerRequestResponseComment.objects.filter(response=response_obj).exists()
        )

    def test_notifications_include_unread_response_threads(self):
        response_obj = BloggerRequestResponse.objects.create(
            request=self.request,
            responder=self.author,
            responder_type=BloggerRequestResponse.ResponderType.AUTHOR,
            message="Предлагаю обзор",
            book=self.book,
        )
        BloggerRequestResponseComment.objects.create(
            response=response_obj,
            author=self.author,
            text="Какие сроки вам подходят?",
        )
        response_obj.register_activity(self.author)

        self.client.force_login(self.blogger)
        notifications_url = reverse("collaborations:collaboration_notifications")
        response = self.client.get(notifications_url)
        unread_threads = list(response.context["unread_blogger_request_threads"])
        self.assertTrue(any(item.pk == response_obj.pk for item in unread_threads))

        detail_url = reverse(
            "collaborations:blogger_request_response_detail", args=[response_obj.pk]
        )
        self.client.get(detail_url)
        response = self.client.get(notifications_url)
        self.assertFalse(response.context["unread_blogger_request_threads"])

    def test_pending_responses_listed_in_notifications(self):
        response_obj = BloggerRequestResponse.objects.create(
            request=self.request,
            responder=self.author,
            responder_type=BloggerRequestResponse.ResponderType.AUTHOR,
            message="Готов принять участие",
            book=self.book,
        )

        self.client.force_login(self.blogger)
        notifications_url = reverse("collaborations:collaboration_notifications")
        response = self.client.get(notifications_url)
        pending_responses = list(response.context["pending_blogger_request_responses"])
        self.assertTrue(any(item.pk == response_obj.pk for item in pending_responses))


class CollaborationMessageAttachmentTests(TestCase):
    def setUp(self):
        super().setUp()
        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tempdir, ignore_errors=True)
        self.override = override_settings(MEDIA_ROOT=self.tempdir)
        self.override.enable()
        self.addCleanup(self.override.disable)

        user_model = get_user_model()
        self.author = user_model.objects.create_user(
            username="attachment_author",
            password="password123",
            email="attach-author@example.com",
        )
        self.partner = user_model.objects.create_user(
            username="attachment_partner",
            password="password123",
            email="attach-partner@example.com",
        )

        self.collaboration = Collaboration.objects.create(
            author=self.author,
            partner=self.partner,
            deadline=date.today() + timedelta(days=7),
            status=Collaboration.Status.ACTIVE,
            author_approved=True,
            partner_approved=True,
        )

    def _build_epub(self, name: str = "book.epub", extra_files: dict[str, str] | None = None):
        extra_files = extra_files or {}
        buffer = BytesIO()
        with ZipFile(buffer, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip")
            archive.writestr("META-INF/container.xml", "<container />")
            archive.writestr("OEBPS/content.opf", "<package></package>")
            for path, content in extra_files.items():
                archive.writestr(path, content)
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="application/epub+zip")

    def test_author_can_attach_valid_epub(self):
        self.client.force_login(self.author)
        response = self.client.post(
            reverse("collaborations:collaboration_detail", args=[self.collaboration.pk]),
            {"text": "Файл во вложении.", "epub_file": self._build_epub()},
        )
        self.assertEqual(response.status_code, 302)
        message = self.collaboration.messages.get()
        self.assertEqual(message.author, self.author)
        self.assertTrue(message.epub_file.name.endswith(".epub"))

    def test_partner_cannot_attach_epub(self):
        self.client.force_login(self.partner)
        response = self.client.post(
            reverse("collaborations:collaboration_detail", args=[self.collaboration.pk]),
            {"text": "Попытка", "epub_file": self._build_epub()},
        )
        self.assertEqual(response.status_code, 400)
        form = response.context["form"]
        self.assertIn("epub_file", form.errors)
        self.assertEqual(self.collaboration.messages.count(), 0)

    def test_author_can_attach_epub_during_negotiation(self):
        self.collaboration.status = Collaboration.Status.NEGOTIATION
        self.collaboration.partner_approved = False
        self.collaboration.save(update_fields=["status", "partner_approved"])

        self.client.force_login(self.author)
        response = self.client.post(
            reverse("collaborations:collaboration_detail", args=[self.collaboration.pk]),
            {"text": "Файл во время переговоров", "epub_file": self._build_epub()},
        )
        self.assertEqual(response.status_code, 302)
        message = self.collaboration.messages.get()
        self.assertEqual(message.author, self.author)
        self.assertTrue(message.epub_file.name.endswith(".epub"))

    def test_rejects_epub_with_dangerous_content(self):
        self.client.force_login(self.author)
        dangerous_epub = self._build_epub(extra_files={"OEBPS/virus.exe": "malware"})
        response = self.client.post(
            reverse("collaborations:collaboration_detail", args=[self.collaboration.pk]),
            {"text": "Будьте осторожны", "epub_file": dangerous_epub},
        )
        self.assertEqual(response.status_code, 400)
        form = response.context["form"]
        self.assertIn("epub_file", form.errors)
        self.assertEqual(self.collaboration.messages.count(), 0)


class CollaborationStatusUpdateTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.author = user_model.objects.create_user(
            username="status_author",
            password="password123",
            email="status-author@example.com",
        )
        self.partner = user_model.objects.create_user(
            username="status_partner",
            password="password123",
            email="status-partner@example.com",
        )
        self.collaboration = Collaboration.objects.create(
            author=self.author,
            partner=self.partner,
            deadline=date.today() + timedelta(days=5),
            status=Collaboration.Status.NEGOTIATION,
        )

    def test_author_can_update_status_to_active(self):
        self.client.force_login(self.author)
        response = self.client.post(
            reverse("collaborations:collaboration_detail", args=[self.collaboration.pk]),
            {"action": "update_status", "status": Collaboration.Status.ACTIVE},
        )
        self.assertEqual(response.status_code, 302)
        self.collaboration.refresh_from_db()
        self.assertEqual(self.collaboration.status, Collaboration.Status.ACTIVE)

    def test_partner_cannot_update_status(self):
        self.client.force_login(self.partner)
        response = self.client.post(
            reverse("collaborations:collaboration_detail", args=[self.collaboration.pk]),
            {"action": "update_status", "status": Collaboration.Status.ACTIVE},
        )
        self.assertEqual(response.status_code, 302)
        self.collaboration.refresh_from_db()
        self.assertEqual(self.collaboration.status, Collaboration.Status.NEGOTIATION)

    def test_author_cannot_set_disallowed_status(self):
        self.client.force_login(self.author)
        response = self.client.post(
            reverse("collaborations:collaboration_detail", args=[self.collaboration.pk]),
            {"action": "update_status", "status": Collaboration.Status.COMPLETED},
        )
        self.assertEqual(response.status_code, 400)
        form = response.context["status_form"]
        self.assertIn("status", form.errors)
        self.collaboration.refresh_from_db()
        self.assertEqual(self.collaboration.status, Collaboration.Status.NEGOTIATION)