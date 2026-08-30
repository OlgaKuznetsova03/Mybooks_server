from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone

from .models import (
    CoinTransaction,
    PremiumPayment,
    PremiumSubscription,
    Profile,
    RewardAdTicket,
    YANDEX_AD_REWARD_COINS,
)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "is_private",
        "is_reader",
        "is_author",
        "is_blogger",
        "has_active_premium",
        "coin_balance_display",
    )
    list_filter = ("is_private",)
    search_fields = ("user__username", "user__email")
    list_select_related = ("user",)

    @admin.display(description="Монеты")
    def coin_balance_display(self, obj):
        if obj.has_unlimited_coins:
            return "∞"
        return obj.coins


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
    readonly_fields = (
        "created_at",
        "updated_at",
        "paid_at",
        "reference",
        "provider_payment_id",
        "idempotence_key",
        "confirmation_url",
        "provider_payload",
    )
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


@admin.register(CoinTransaction)
class CoinTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "profile",
        "transaction_type",
        "change",
        "balance_after_display",
        "current_balance_display",
        "unlimited",
        "created_at",
    )
    list_filter = ("transaction_type", "unlimited", "created_at")
    search_fields = (
        "profile__user__username",
        "profile__user__email",
        "description",
    )
    autocomplete_fields = ("profile",)
    readonly_fields = ("created_at",)
    list_select_related = ("profile", "profile__user")
    date_hierarchy = "created_at"
    ordering = ("-created_at", "-id")

    @admin.display(description="Баланс после операции", ordering="balance_after")
    def balance_after_display(self, obj):
        return obj.balance_after

    @admin.display(description="Текущий общий баланс")
    def current_balance_display(self, obj):
        return obj.profile.coins


@admin.register(RewardAdTicket)
class RewardAdTicketAdmin(admin.ModelAdmin):
    list_display = (
        "profile",
        "provider",
        "issued_at",
        "claimed_at",
        "transaction",
        "current_balance_display",
        "expires_at",
    )
    list_filter = ("provider", "claimed_at")
    search_fields = ("profile__user__username", "profile__user__email", "token")
    autocomplete_fields = ("profile",)
    readonly_fields = (
        "token",
        "issued_at",
        "not_before",
        "expires_at",
        "claimed_at",
        "transaction",
    )
    list_select_related = ("profile", "profile__user", "transaction")
    ordering = ("-issued_at", "-id")
    actions = ("credit_selected_unclaimed_tickets",)

    @admin.display(description="Текущий общий баланс")
    def current_balance_display(self, obj):
        return obj.profile.coins

    @admin.action(
        description=f"Начислить {YANDEX_AD_REWARD_COINS} монет по выбранным незакрытым билетам"
    )
    def credit_selected_unclaimed_tickets(self, request, queryset):
        credited = 0
        skipped = 0

        for ticket_id in queryset.values_list("pk", flat=True):
            with transaction.atomic():
                ticket = (
                    RewardAdTicket.objects.select_for_update()
                    .select_related("profile")
                    .get(pk=ticket_id)
                )
                if ticket.claimed_at or ticket.transaction_id:
                    skipped += 1
                    continue

                profile = Profile.objects.select_for_update().get(pk=ticket.profile_id)
                coin_transaction = profile.reward_ad_view(
                    YANDEX_AD_REWARD_COINS,
                    description=(
                        "Награда за просмотр рекламы, восстановленная администратором "
                        f"({ticket.get_provider_display()})"
                    ),
                )
                ticket.claimed_at = timezone.now()
                ticket.transaction = coin_transaction
                ticket.save(update_fields=("claimed_at", "transaction"))
                credited += 1

        if credited:
            self.message_user(
                request,
                f"Начислено наград: {credited}. Каждая награда — {YANDEX_AD_REWARD_COINS} монет.",
                level=messages.SUCCESS,
            )
        if skipped:
            self.message_user(
                request,
                f"Пропущено уже обработанных билетов: {skipped}.",
                level=messages.WARNING,
            )
