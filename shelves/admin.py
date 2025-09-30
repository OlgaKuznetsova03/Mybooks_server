from django.contrib import admin

from .models import (
    Shelf,
    ShelfItem,
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