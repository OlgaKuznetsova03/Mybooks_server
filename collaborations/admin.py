from django.contrib import admin

from .models import (
    AuthorOffer,
    AuthorOfferResponse,
    BloggerPlatformPresence,
    BloggerRating,
    BloggerRequest,
    BloggerRequestResponse,
    Collaboration,
    ReviewPlatform,
)


@admin.register(ReviewPlatform)
class ReviewPlatformAdmin(admin.ModelAdmin):
    list_display = ("name", "url")
    search_fields = ("name",)


class AuthorOfferResponseInline(admin.TabularInline):
    model = AuthorOfferResponse
    extra = 0
    readonly_fields = ("respondent", "status", "created_at", "updated_at")


@admin.register(AuthorOffer)
class AuthorOfferAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "offered_format", "is_active", "created_at")
    list_filter = ("offered_format", "is_active", "considers_paid_collaboration")
    search_fields = ("title", "synopsis")
    inlines = [AuthorOfferResponseInline]
    filter_horizontal = ("expected_platforms",)


class BloggerRequestResponseInline(admin.TabularInline):
    model = BloggerRequestResponse
    extra = 0
    readonly_fields = ("author", "status", "created_at", "updated_at")


class BloggerPlatformPresenceInline(admin.TabularInline):
    model = BloggerPlatformPresence
    extra = 1


@admin.register(BloggerRequest)
class BloggerRequestAdmin(admin.ModelAdmin):
    list_display = ("title", "blogger", "is_active", "created_at")
    list_filter = ("is_active", "open_for_paid_collaboration")
    search_fields = ("title", "additional_info")
    inlines = [BloggerPlatformPresenceInline, BloggerRequestResponseInline]
    filter_horizontal = ("preferred_genres", "review_formats")


@admin.register(Collaboration)
class CollaborationAdmin(admin.ModelAdmin):
    list_display = ("author", "partner", "status", "deadline", "created_at")
    list_filter = ("status",)
    search_fields = ("offer__title", "request__title", "author__username", "partner__username")


@admin.register(BloggerRating)
class BloggerRatingAdmin(admin.ModelAdmin):
    list_display = (
        "blogger",
        "score",
        "successful_collaborations",
        "failed_collaborations",
        "total_collaborations",
    )
    search_fields = ("blogger__username", "blogger__first_name", "blogger__last_name")