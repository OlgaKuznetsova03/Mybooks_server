from django.contrib import admin

from .models import DiscussionPost, ReadingClub, ReadingNorm, ReadingParticipant


@admin.register(ReadingClub)
class ReadingClubAdmin(admin.ModelAdmin):
    list_display = ("title", "book", "start_date", "end_date", "join_policy", "creator")
    list_filter = ("join_policy", "start_date", "end_date")
    search_fields = ("title", "book__title", "creator__username")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(ReadingNorm)
class ReadingNormAdmin(admin.ModelAdmin):
    list_display = ("title", "reading", "order", "discussion_opens_at")
    list_filter = ("discussion_opens_at",)
    search_fields = ("title", "reading__title")


@admin.register(DiscussionPost)
class DiscussionPostAdmin(admin.ModelAdmin):
    list_display = ("topic", "author", "created_at")
    list_filter = ("created_at",)
    search_fields = ("topic__title", "author__username", "content")


@admin.register(ReadingParticipant)
class ReadingParticipantAdmin(admin.ModelAdmin):
    list_display = ("reading", "user", "status", "joined_at")
    list_filter = ("status",)
    search_fields = ("reading__title", "user__username")