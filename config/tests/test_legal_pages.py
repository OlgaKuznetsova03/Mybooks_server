from django.test import SimpleTestCase
from django.urls import reverse


class PublicLegalPagesTests(SimpleTestCase):
    def test_rules_page_is_public_and_links_to_privacy(self) -> None:
        response = self.client.get(reverse("rules"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Правила использования")
        self.assertContains(response, reverse("privacy_policy"))
        self.assertContains(response, "Yandex Mobile Ads")
        self.assertContains(response, "рекламный идентификатор")

    def test_privacy_policy_is_public_and_identifies_app(self) -> None:
        response = self.client.get(reverse("privacy_policy"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Политика конфиденциальности")
        self.assertContains(response, "Калейдоскоп книг")
        self.assertContains(response, "Кузнецов Сергей Валентинович")
        self.assertContains(response, reverse("account_deletion"))
        self.assertContains(response, "Собирается")
        self.assertContains(response, "Yandex Mobile Ads")
        self.assertContains(response, "HTTPS/TLS")

    def test_account_deletion_resource_is_public_and_actionable(self) -> None:
        response = self.client.get(reverse("account_deletion"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Удаление аккаунта")
        self.assertContains(response, "info@kalejdoskopknig.ru")
        self.assertContains(response, "/accounts/account/delete/")
        self.assertContains(response, "не временной блокировкой")
