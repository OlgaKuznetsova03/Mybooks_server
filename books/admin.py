from django.contrib import admin
from .models import Book, BookEditRequest, ISBNModel, Author, Genre, Publisher, AudioBook, Rating

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "get_avg",)
    search_fields = ("title", "authors__name")
    list_filter = ("genres",)
    filter_horizontal = ("authors", "genres", "isbn", "publisher")

    def get_avg(self, obj):
        return obj.get_average_rating()
    get_avg.short_description = "★"

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