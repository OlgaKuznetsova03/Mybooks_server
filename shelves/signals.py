from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Shelf

DEFAULT_SHELVES = ["Хочу прочитать", "Читаю", "Прочитал"]

@receiver(post_save, sender=User)
def create_default_shelves(sender, instance, created, **kwargs):
    if created:
        Shelf.objects.bulk_create([
            Shelf(user=instance, name=name, is_default=True) for name in DEFAULT_SHELVES
        ])
