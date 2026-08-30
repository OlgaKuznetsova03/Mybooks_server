from django.core.management.base import BaseCommand, CommandError

from shelves.models import BookProgress


class Command(BaseCommand):
    help = (
        "Normalize tracker totals after paper page counts were added to books. "
        "E-book totals stay on the e-book medium; book pages become the base."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "book_id",
            nargs="?",
            type=int,
            help="Book id to normalize trackers for.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Normalize trackers for all books.",
        )

    def handle(self, *args, **options):
        book_id = options.get("book_id")
        normalize_all = options.get("all")
        if not book_id and not normalize_all:
            raise CommandError("Pass a book_id or use --all.")

        queryset = (
            BookProgress.objects
            .select_related("book", "user")
            .prefetch_related("media")
            .order_by("id")
        )
        if book_id:
            queryset = queryset.filter(book_id=book_id)

        scanned = 0
        changed = 0
        for progress in queryset.iterator(chunk_size=200):
            scanned += 1
            if progress.normalize_page_totals():
                changed += 1

        scope = f"book_id={book_id}" if book_id else "all books"
        self.stdout.write(
            self.style.SUCCESS(
                f"Normalized tracker pages for {scope}: {changed}/{scanned} changed."
            )
        )
