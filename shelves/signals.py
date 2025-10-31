from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User

from .models import Shelf, ShelfItem, HomeLibraryEntry
from .services import (
    DEFAULT_HOME_LIBRARY_SHELF,
    DEFAULT_READ_SHELF,
    DEFAULT_READING_SHELF,
    DEFAULT_WANT_SHELF,
)

DEFAULT_SHELVES = [
    (DEFAULT_WANT_SHELF, True),
    (DEFAULT_READING_SHELF, True),
    (DEFAULT_READ_SHELF, True),
    (DEFAULT_HOME_LIBRARY_SHELF, False),
]

@receiver(post_save, sender=User)
def create_default_shelves(sender, instance, created, **kwargs):
    if created:
        Shelf.objects.bulk_create([
            Shelf(user=instance, name=name, is_default=True, is_public=is_public)
            for name, is_public in DEFAULT_SHELVES
        ])


@receiver(post_save, sender=ShelfItem)
def ensure_home_library_entry(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.shelf.name != DEFAULT_HOME_LIBRARY_SHELF:
        return
    HomeLibraryEntry.objects.get_or_create(shelf_item=instance)