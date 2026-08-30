from django.core.management.base import BaseCommand

from books.models import Book, clear_book_list_discovery_cache


class Command(BaseCommand):
    help = "Regenerate cached cover thumbnails used by book list pages."

    def add_arguments(self, parser):
        parser.add_argument(
            "--book-id",
            action="append",
            dest="book_ids",
            type=int,
            help="Regenerate thumbnails only for the selected book id. Can be used more than once.",
        )

    def handle(self, *args, **options):
        book_ids = options.get("book_ids") or []
        queryset = Book.objects.exclude(cover="")
        if book_ids:
            queryset = queryset.filter(pk__in=book_ids)

        updated = 0
        skipped = 0

        for book in queryset.iterator():
            if not book.cover:
                skipped += 1
                continue

            if book.ensure_cover_thumbnail(force=True, save=True):
                updated += 1
            else:
                skipped += 1

        clear_book_list_discovery_cache()

        self.stdout.write(
            self.style.SUCCESS(
                f"Regenerated {updated} cover thumbnails. Skipped {skipped} books."
            )
        )
