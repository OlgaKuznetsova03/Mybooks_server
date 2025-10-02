"""Signal handlers for the games app."""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from books.models import Rating
from shelves.models import BookProgress

from .models import BookJourneyAssignment, ForgottenBookEntry


@receiver(post_save, sender=BookProgress)
def handle_book_progress_update(sender, instance, **kwargs):
    """Update journey assignments when reading progress changes."""

    if instance.user_id and instance.book_id:
        BookJourneyAssignment.sync_for_user_book(instance.user, instance.book)
        ForgottenBookEntry.sync_for_user_book(instance.user, instance.book)


@receiver(post_save, sender=Rating)
def handle_rating_save(sender, instance, **kwargs):
    """Update assignments when a review is saved or edited."""

    if instance.user_id and instance.book_id:
        BookJourneyAssignment.sync_for_user_book(instance.user, instance.book)
        ForgottenBookEntry.sync_for_user_book(instance.user, instance.book)


@receiver(post_delete, sender=Rating)
def handle_rating_delete(sender, instance, **kwargs):
    """Re-check completion when a review is removed."""

    if instance.user_id and instance.book_id:
        BookJourneyAssignment.sync_for_user_book(instance.user, instance.book)
        ForgottenBookEntry.sync_for_user_book(instance.user, instance.book)