from django.contrib import admin

from .models import VKAccount


@admin.register(VKAccount)
class VKAccountAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "vk_user_id", "first_name", "last_name", "linked_at")
    search_fields = ("user__username", "user__email", "vk_user_id", "screen_name")
    readonly_fields = ("linked_at", "updated_at")
