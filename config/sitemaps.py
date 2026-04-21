from __future__ import annotations

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from books.models import Author, Book, Genre
from reading_clubs.models import ReadingClub
from reading_marathons.models import ReadingMarathon


class StaticViewSitemap(Sitemap):
    priority = 0.7
    changefreq = "weekly"

    def items(self):
        return [
            "home",
            "book_list",
            "games:index",
            "reading_communities_overview",
            "reading_clubs:list",
            "reading_marathons:list",
            "collaborations:blogger_community",
            "collaborations:offer_list",
        ]

    def location(self, item):
        return reverse(item)


class BookSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return Book.objects.order_by("-created_at")

    def lastmod(self, obj: Book):
        return obj.created_at


class AuthorSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Author.objects.order_by("name")


class GenreSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Genre.objects.order_by("name")


class ReadingClubSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.7

    def items(self):
        return ReadingClub.objects.order_by("-updated_at")

    def lastmod(self, obj: ReadingClub):
        return obj.updated_at


class ReadingMarathonSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.7

    def items(self):
        return ReadingMarathon.objects.order_by("-updated_at")

    def lastmod(self, obj: ReadingMarathon):
        return obj.updated_at