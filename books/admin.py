from django.contrib import admin
from django.utils import timezone
from .models import (
    AudioBook,
    Author,
    Book,
    BookEditRequest,
    Genre,
    ISBNModel,
    Publisher,
    Rating,
    clear_book_list_discovery_cache,
)

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "visibility", "is_hidden_by_admin", "owner", "get_avg")
    search_fields = ("title", "authors__name")
    list_filter = ("visibility", "is_hidden_by_admin", "genres")
    filter_horizontal = ("authors", "genres", "isbn", "publisher")
    readonly_fields = ("hidden_at",)
    actions = ("publish_after_moderation", "hide_from_public", "restore_to_public")

    def get_avg(self, obj):
        return obj.get_average_rating()
    get_avg.short_description = "★"

    def save_model(self, request, obj, form, change):
        cover_changed = "cover" in getattr(form, "changed_data", [])
        visibility_changed = any(
            field in getattr(form, "changed_data", [])
            for field in ("visibility", "is_hidden_by_admin")
        )
        if obj.is_hidden_by_admin and not obj.hidden_at:
            obj.hidden_at = timezone.now()
        elif not obj.is_hidden_by_admin:
            obj.hidden_at = None
        super().save_model(request, obj, form, change)
        if cover_changed:
            if obj.cover:
                obj.ensure_cover_thumbnail(force=True, save=True)
            else:
                try:
                    obj.cover_thumbnail.delete(save=False)
                except (OSError, ValueError):
                    pass
                obj.cover_thumbnail = None
                type(obj).objects.filter(pk=obj.pk).update(cover_thumbnail="")
                clear_book_list_discovery_cache()
        if visibility_changed:
            clear_book_list_discovery_cache()

    @admin.action(description="Скрыть из публичного каталога")
    def hide_from_public(self, request, queryset):
        queryset.update(is_hidden_by_admin=True, hidden_at=timezone.now())
        clear_book_list_discovery_cache()

    @admin.action(description="Опубликовать после модерации")
    def publish_after_moderation(self, request, queryset):
        queryset.update(
            visibility=Book.Visibility.PUBLIC,
            is_hidden_by_admin=False,
            hidden_reason="",
            hidden_at=None,
        )
        clear_book_list_discovery_cache()

    @admin.action(description="Вернуть в публичный каталог")
    def restore_to_public(self, request, queryset):
        queryset.update(
            visibility=Book.Visibility.PUBLIC,
            is_hidden_by_admin=False,
            hidden_at=None,
        )
        clear_book_list_discovery_cache()


@admin.register(ISBNModel)
class ISBNAdmin(admin.ModelAdmin):
    list_display = ("title", "isbn", "isbn13", "publisher", "language")
    search_fields = ("title", "isbn", "isbn13", "publisher")
    list_filter = ("language",)


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


admin.site.register([Publisher, AudioBook, Rating])


@admin.register(BookEditRequest)
class BookEditRequestAdmin(admin.ModelAdmin):
    list_display = ("book", "user", "created_at", "is_resolved")
    list_filter = ("is_resolved", "created_at")
    search_fields = ("book__title", "user__username", "comment")
