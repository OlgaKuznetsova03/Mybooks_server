from django.conf import settings
import secrets
from django.db import models


def generate_mobile_token_key() -> str:
    return secrets.token_hex(32)


class MobileAuthToken(models.Model):
    key = models.CharField(max_length=64, primary_key=True, default=generate_mobile_token_key, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mobile_auth_tokens",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self) -> str:
        return f"Mobile token for {self.user_id}"


class VKAccount(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vk_account",
    )
    vk_user_id = models.BigIntegerField(unique=True, db_index=True)
    first_name = models.CharField(max_length=255, blank=True)
    last_name = models.CharField(max_length=255, blank=True)
    photo_100 = models.CharField(max_length=1000, blank=True)  # Было URLField, изменили на CharField с 1000
    screen_name = models.CharField(max_length=255, blank=True)
    linked_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        display_name = f"{self.first_name} {self.last_name}".strip()
        return display_name or f"VK {self.vk_user_id}"
