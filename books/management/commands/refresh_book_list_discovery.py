from django.core.cache import cache
from django.core.management.base import BaseCommand

from books.views import (
    BOOK_LIST_POPULAR_DISCOVERY_CACHE_KEY,
    BOOK_LIST_POPULAR_DISCOVERY_CACHE_TIMEOUT,
    BOOK_LIST_RECENT_DISCOVERY_CACHE_KEY,
    BOOK_LIST_RECENT_DISCOVERY_CACHE_TIMEOUT,
    build_book_list_discovery_payload,
    save_book_list_popular_discovery_snapshot,
)


class Command(BaseCommand):
    help = "Refresh cached discovery shelves for /books/book_list."

    def handle(self, *args, **options):
        recent_payload = build_book_list_discovery_payload(include_popular=False)
        cache.set(
            BOOK_LIST_RECENT_DISCOVERY_CACHE_KEY,
            recent_payload,
            timeout=BOOK_LIST_RECENT_DISCOVERY_CACHE_TIMEOUT,
        )

        popular_payload = build_book_list_discovery_payload(include_recent=False)
        cache.set(
            BOOK_LIST_POPULAR_DISCOVERY_CACHE_KEY,
            popular_payload,
            timeout=BOOK_LIST_POPULAR_DISCOVERY_CACHE_TIMEOUT,
        )
        popular_json_path = save_book_list_popular_discovery_snapshot(popular_payload)

        recent_shelves_count = len(recent_payload.get("shelves", []))
        popular_shelves_count = len(popular_payload.get("shelves", []))
        total_books = int(recent_payload.get("total_books", 0) or 0)
        self.stdout.write(
            self.style.SUCCESS(
                f"Refreshed {recent_shelves_count} recent shelves for "
                f"{BOOK_LIST_RECENT_DISCOVERY_CACHE_TIMEOUT} seconds and "
                f"{popular_shelves_count} popular shelves for "
                f"{BOOK_LIST_POPULAR_DISCOVERY_CACHE_TIMEOUT} seconds "
                f"for {total_books} books. Popular shelves JSON: {popular_json_path}."
            )
        )
