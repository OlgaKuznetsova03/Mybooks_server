from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from collaborations.models import Collaboration


class VKCollaborationConfirmationApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.author = user_model.objects.create_user(
            username="deadline_author",
            email="deadline_author@example.com",
            password="StrongPass123!",
        )
        self.blogger = user_model.objects.create_user(
            username="deadline_blogger",
            email="deadline_blogger@example.com",
            password="StrongPass123!",
        )
        self.deadline = timezone.localdate() + timedelta(days=14)
        self.collaboration = Collaboration.objects.create(
            author=self.author,
            partner=self.blogger,
            deadline=self.deadline,
            status=Collaboration.Status.NEGOTIATION,
            author_approved=True,
            partner_approved=False,
        )

    def _approve_url(self):
        return f"/api/v1/vk-app/collaborations/{self.collaboration.pk}/approve/"

    def _status_url(self):
        return f"/api/v1/vk-app/collaborations/{self.collaboration.pk}/status/"

    def test_overview_exposes_both_deadline_approvals(self):
        self.client.force_authenticate(self.blogger)

        response = self.client.get("/api/v1/vk-app/collaborations/", secure=True)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = response.json()["collaborations"][0]
        self.assertTrue(item["author_approved"])
        self.assertFalse(item["partner_approved"])
        self.assertTrue(item["can_approve"])
        self.assertTrue(item["waiting_for_me"])

    def test_blogger_can_change_date_and_author_confirms_it_finally(self):
        changed_deadline = self.deadline + timedelta(days=7)
        self.client.force_authenticate(self.blogger)

        response = self.client.post(
            self._approve_url(),
            {"deadline": changed_deadline.isoformat()},
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.collaboration.refresh_from_db()
        self.assertEqual(self.collaboration.deadline, changed_deadline)
        self.assertFalse(self.collaboration.author_approved)
        self.assertTrue(self.collaboration.partner_approved)
        self.assertEqual(self.collaboration.status, Collaboration.Status.NEGOTIATION)

        self.client.force_authenticate(self.author)
        response = self.client.post(
            self._approve_url(),
            {"deadline": changed_deadline.isoformat()},
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.collaboration.refresh_from_db()
        self.assertTrue(self.collaboration.author_approved)
        self.assertTrue(self.collaboration.partner_approved)
        self.assertEqual(self.collaboration.status, Collaboration.Status.ACTIVE)

    def test_status_cannot_bypass_second_participant_approval(self):
        self.client.force_authenticate(self.author)

        response = self.client.post(
            self._status_url(),
            {"status": Collaboration.Status.ACTIVE},
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("оба участника", response.json()["detail"])
        self.collaboration.refresh_from_db()
        self.assertEqual(self.collaboration.status, Collaboration.Status.NEGOTIATION)
