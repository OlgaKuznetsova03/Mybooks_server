from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from .models import AuthorOffer, AuthorOfferResponse, Collaboration


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

    def test_non_author_redirected_from_response_list(self):
        self.client.force_login(self.blogger)
        url = reverse("collaborations:offer_responses")
        response = self.client.get(url)
        self.assertRedirects(response, reverse("collaborations:offer_list"))