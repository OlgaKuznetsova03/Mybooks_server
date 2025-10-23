from django.contrib import admin
from django.utils import timezone

from .models import Profile, PremiumPayment, PremiumSubscription


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "is_reader", "is_author", "is_blogger", "has_active_premium")
    search_fields = ("user__username", "user__email")
    list_select_related = ("user",)


@admin.register(PremiumPayment)
class PremiumPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "plan",
        "method",
        "status",
        "amount",
        "reference",
        "created_at",
        "paid_at",
    )
    list_filter = ("status", "method", "plan")
    search_fields = ("user__username", "user__email", "reference")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at", "paid_at", "reference")
    actions = ("mark_selected_as_paid",)

    @admin.action(description="Отметить как оплаченные и активировать премиум")
    def mark_selected_as_paid(self, request, queryset):
        updated = 0
        for payment in queryset:
            if payment.status != PremiumPayment.Status.PAID:
                payment.status = PremiumPayment.Status.PAID
                payment.paid_at = timezone.now()
                payment.save()
                updated += 1
        if updated:
            self.message_user(request, f"Обновлено {updated} платежей.")
        else:
            self.message_user(request, "Выбранные платежи уже отмечены как оплаченные.")


@admin.register(PremiumSubscription)
class PremiumSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "start_at", "end_at", "source", "granted_by", "is_active_display")
    list_filter = ("source", "end_at")
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user", "granted_by", "payment")
    readonly_fields = ("created_at",)

    @admin.display(boolean=True, description="Активна")
    def is_active_display(self, obj):
        return obj.is_active
