from django.core.management.base import BaseCommand

from books.models import Book


class Command(BaseCommand):
    help = (
        "Generate 160x240 WebP thumbnails for existing uploaded book covers. "
        "Use this once after deploy to backfill covers already stored on S3."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Regenerate thumbnails even when cover_thumbnail is already filled.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=200,
            help="Number of books to stream from the database at once.",
        )

    def handle(self, *args, **options):
        force = options["force"]
        batch_size = options["batch_size"]
        queryset = Book.objects.exclude(cover="").exclude(cover__isnull=True).order_by("pk")

        total = queryset.count()
        created = 0
        skipped = 0
        failed = 0

        self.stdout.write(f"Found {total} books with uploaded covers.")

        for book in queryset.iterator(chunk_size=batch_size):
            if book.cover_thumbnail and not force:
                skipped += 1
                continue

            if book.ensure_cover_thumbnail(force=force, save=True):
                created += 1
                self.stdout.write(f"Created thumbnail for book #{book.pk}: {book.cover_thumbnail.name}")
            else:
                failed += 1
                self.stderr.write(f"Could not create thumbnail for book #{book.pk}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. created={created}, skipped={skipped}, failed={failed}, total={total}"
            )
        )