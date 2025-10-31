from django.contrib import admin

from .models import (
    BookExchangeAcceptedBook,
    BookExchangeChallenge,
    BookExchangeOffer,
    Game,
    GameShelfBook,
    GameShelfPurchase,
    GameShelfState,
)


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "is_active")
    list_filter = ("is_active",)
    search_fields = ("title", "slug")


@admin.register(GameShelfState)
class GameShelfStateAdmin(admin.ModelAdmin):
    list_display = (
        "game",
        "shelf",
        "user",
        "points_balance",
        "books_reviewed",
        "books_purchased",
    )
    search_fields = ("shelf__name", "user__username", "game__title")
    list_filter = ("game",)


@admin.register(GameShelfBook)
class GameShelfBookAdmin(admin.ModelAdmin):
    list_display = ("state", "book", "pages_logged", "bonus_awarded", "reviewed_at")
    list_filter = ("bonus_awarded", "state__game")
    search_fields = ("book__title", "state__shelf__name")


@admin.register(GameShelfPurchase)
class GameShelfPurchaseAdmin(admin.ModelAdmin):
    list_display = ("state", "book", "points_spent", "created_at")
    list_filter = ("state__game",)
    search_fields = ("book__title", "state__shelf__name")


@admin.register(BookExchangeChallenge)
class BookExchangeChallengeAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "round_number",
        "target_books",
        "status",
        "started_at",
        "completed_at",
    )
    list_filter = ("status", "started_at")
    search_fields = ("user__username",)
    autocomplete_fields = ("user", "shelf", "genres")


@admin.register(BookExchangeOffer)
class BookExchangeOfferAdmin(admin.ModelAdmin):
    list_display = (
        "challenge",
        "book",
        "offered_by",
        "status",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("book__title", "offered_by__username", "challenge__user__username")
    autocomplete_fields = ("challenge", "book", "offered_by")


@admin.register(BookExchangeAcceptedBook)
class BookExchangeAcceptedBookAdmin(admin.ModelAdmin):
    list_display = (
        "challenge",
        "book",
        "accepted_at",
        "completed_at",
    )
    search_fields = ("book__title", "challenge__user__username")
    autocomplete_fields = ("challenge", "offer", "book")