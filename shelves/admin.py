from django.contrib import admin

from .models import (
    Shelf,
    ShelfItem,
    PurchaseList,
    PurchaseListItem,
    Event,
    EventParticipant,
    BookProgress,
)


class ShelfItemInline(admin.TabularInline):
    model = ShelfItem
    extra = 0


@admin.register(Shelf)
class ShelfAdmin(admin.ModelAdmin):
    list_display = ("user", "name", "is_default", "is_public")
    list_filter = ("is_default", "is_public")
    search_fields = ("name", "user__username")
    inlines = [ShelfItemInline]


@admin.register(ShelfItem)
class ShelfItemAdmin(admin.ModelAdmin):
    list_display = ("shelf", "book", "added_at")
    search_fields = ("shelf__name", "book__title", "shelf__user__username")


class PurchaseListItemInline(admin.TabularInline):
    model = PurchaseListItem
    extra = 0
    autocomplete_fields = ("book",)


@admin.register(PurchaseList)
class PurchaseListAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "items_count", "updated_at")
    list_filter = ("created_at", "updated_at")
    search_fields = ("title", "description", "user__username", "user__email")
    inlines = [PurchaseListItemInline]

    def items_count(self, obj):
        return obj.items.count()

    items_count.short_description = "Книг"


@admin.register(PurchaseListItem)
class PurchaseListItemAdmin(admin.ModelAdmin):
    list_display = ("purchase_list", "book", "added_at")
    search_fields = ("purchase_list__title", "purchase_list__user__username", "book__title")
    autocomplete_fields = ("book",)


class EventParticipantInline(admin.TabularInline):
    model = EventParticipant
    extra = 0


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "creator", "start_at", "end_at", "is_public")
    list_filter  = ("kind", "is_public")
    search_fields = ("title", "creator__username")
    inlines = [EventParticipantInline]


@admin.register(BookProgress)
class BookProgressAdmin(admin.ModelAdmin):
    list_display = ("event", "user", "book", "percent", "updated_at")
    list_filter = ("event",)
    search_fields = ("book__title", "user__username")


@admin.register(EventParticipant)
class EventParticipantAdmin(admin.ModelAdmin):
    list_display = ("event", "user", "is_moderator", "joined_at")
    list_filter = ("is_moderator",)
    search_fields = ("event__title", "user__username")
