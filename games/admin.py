from django.contrib import admin

from .models import Game, GameShelfBook, GameShelfPurchase, GameShelfState


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