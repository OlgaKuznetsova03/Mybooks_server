from django.contrib import admin

from .models import MarathonEntry, MarathonParticipant, MarathonTheme, ReadingMarathon


class MarathonThemeInline(admin.TabularInline):
    model = MarathonTheme
    extra = 0


@admin.register(ReadingMarathon)
class ReadingMarathonAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "creator",
        "start_date",
        "end_date",
        "join_policy",
        "book_submission_policy",
        "completion_policy",
    )
    search_fields = ("title", "description")
    list_filter = ("join_policy", "book_submission_policy", "completion_policy")
    inlines = [MarathonThemeInline]


@admin.register(MarathonParticipant)
class MarathonParticipantAdmin(admin.ModelAdmin):
    list_display = ("marathon", "user", "status", "joined_at")
    list_filter = ("status",)
    search_fields = ("marathon__title", "user__username")


@admin.register(MarathonEntry)
class MarathonEntryAdmin(admin.ModelAdmin):
    list_display = (
        "participant",
        "theme",
        "book",
        "status",
        "book_approved",
        "completion_status",
    )
    list_filter = ("status", "book_approved", "completion_status")
    search_fields = ("book__title", "participant__user__username", "theme__title")
