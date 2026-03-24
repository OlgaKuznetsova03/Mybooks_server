from django.conf import settings
from django.db import models

class VKAccount(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vk_account",
    )
    vk_user_id = models.BigIntegerField(unique=True, db_index=True)
    first_name = models.CharField(max_length=255, blank=True)
    last_name = models.CharField(max_length=255, blank=True)
    photo_100 = models.URLField(blank=True)
    screen_name = models.CharField(max_length=255, blank=True)
    linked_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        display_name = f"{self.first_name} {self.last_name}".strip()
        return display_name or f"VK {self.vk_user_id}"
