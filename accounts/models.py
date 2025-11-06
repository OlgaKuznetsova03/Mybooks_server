from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import F
from django.utils import timezone


WELCOME_BONUS_COINS = 100
DAILY_LOGIN_REWARD_COINS = 10
YANDEX_AD_REWARD_COINS = 20


@dataclass(frozen=True)
class PremiumPlan:
    code: str
    label: str
    duration: timedelta
    price: Decimal


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    bio = models.TextField(blank=True)
    website = models.URLField(blank=True)
    coins = models.PositiveIntegerField(default=0)
    last_daily_reward_at = models.DateField(blank=True, null=True)
    premium_auto_renew = models.BooleanField(default=True)

    def __str__(self):
        return f"Profile({self.user.username})"

    link1 = models.URLField(blank=True, null=True)
    link2 = models.URLField(blank=True, null=True)
    link3 = models.URLField(blank=True, null=True)
    link4 = models.URLField(blank=True, null=True)

    @property
    def is_reader(self):
        return self.user.groups.filter(name="reader").exists()

    @property
    def is_author(self):
        return self.user.groups.filter(name="author").exists()

    @property
    def is_blogger(self):
        return self.user.groups.filter(name="blogger").exists()

    @property
    def active_premium(self) -> "PremiumSubscription | None":
        now = timezone.now()
        return (
            self.user.premium_subscriptions
            .filter(end_at__gte=now)
            .order_by("-end_at")
            .select_related("payment")
            .first()
        )

    @property
    def has_active_premium(self) -> bool:
        return self.active_premium is not None

    @property
    def premium_expires_at(self):
        subscription = self.active_premium
        return subscription.end_at if subscription else None

    @property
    def has_unlimited_coins(self) -> bool:
        return self.has_active_premium

    @property
    def coin_balance(self) -> int | None:
        return None if self.has_unlimited_coins else self.coins

    @property
    def available_coins(self) -> float:
        return float("inf") if self.has_unlimited_coins else self.coins

    def credit_coins(
        self,
        amount: int,
        *,
        transaction_type: "CoinTransaction.Type",
        description: str = "",
    ) -> "CoinTransaction":
        if amount <= 0:
            raise ValueError("Coin credit amount must be positive")

        with transaction.atomic():
            Profile.objects.filter(pk=self.pk).update(coins=F("coins") + amount)
            self.refresh_from_db(fields=["coins"])
            return CoinTransaction.objects.create(
                profile=self,
                change=amount,
                transaction_type=transaction_type,
                balance_after=self.coins,
                description=description,
            )

    def reward_ad_view(self, amount: int, description: str = "") -> "CoinTransaction":
        return self.credit_coins(
            amount,
            transaction_type=CoinTransaction.Type.AD_REWARD,
            description=description or "Награда за просмотр рекламы",
        )

    def grant_daily_login_reward(
        self,
        amount: int = DAILY_LOGIN_REWARD_COINS,
        description: str = "",
    ) -> "CoinTransaction | None":
        today = timezone.localdate()
        with transaction.atomic():
            profile = Profile.objects.select_for_update().get(pk=self.pk)
            if profile.last_daily_reward_at == today:
                return None
            profile.last_daily_reward_at = today
            profile.save(update_fields=["last_daily_reward_at"])
            tx = profile.credit_coins(
                amount,
                transaction_type=CoinTransaction.Type.DAILY_LOGIN,
                description=description or "Ежедневный бонус за вход",
            )

        self.refresh_from_db(fields=["coins", "last_daily_reward_at"])
        return tx

    def spend_coins(
        self,
        amount: int,
        *,
        transaction_type: "CoinTransaction.Type",
        description: str = "",
    ) -> "CoinTransaction":
        if amount <= 0:
            raise ValueError("Coin spending amount must be positive")

        if self.has_unlimited_coins:
            return CoinTransaction.objects.create(
                profile=self,
                change=-amount,
                transaction_type=transaction_type,
                balance_after=None,
                description=description or "Трата монет при активной подписке",
                unlimited=True,
            )

        with transaction.atomic():
            updated = (
                Profile.objects.filter(pk=self.pk, coins__gte=amount)
                .update(coins=F("coins") - amount)
            )
            if not updated:
                raise ValueError("Недостаточно монет")
            self.refresh_from_db(fields=["coins"])
            return CoinTransaction.objects.create(
                profile=self,
                change=-amount,
                transaction_type=transaction_type,
                balance_after=self.coins,
                description=description,
            )


class CoinTransaction(models.Model):
    class Type(models.TextChoices):
        AD_REWARD = ("ad_reward", "Награда за просмотр рекламы")
        DAILY_LOGIN = ("daily_login", "Бонус за ежедневный вход")
        SIGNUP_BONUS = ("signup_bonus", "Приветственный бонус")
        ADMIN_ADJUSTMENT = ("admin_adjustment", "Корректировка администратором")
        FEATURE_PURCHASE = ("feature_purchase", "Трата на функцию")

    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="coin_transactions",
    )
    change = models.IntegerField()
    transaction_type = models.CharField(max_length=40, choices=Type.choices)
    description = models.CharField(max_length=255, blank=True)
    balance_after = models.PositiveIntegerField(null=True, blank=True)
    unlimited = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return (
            f"CoinTransaction({self.profile.user.username}, {self.transaction_type}, {self.change})"
        )


class PremiumPayment(models.Model):
    class PaymentMethod(models.TextChoices):
        YOOMONEY = ("yoomoney", "ЮMoney кошелёк")

    class Status(models.TextChoices):
        PENDING = ("pending", "Ожидает оплаты")
        PAID = ("paid", "Оплачен")
        CANCELLED = ("cancelled", "Отменён")

    class Plan(models.TextChoices):
        MONTH = ("month", "1 месяц")

    PLAN_CONFIGURATION: dict[str, PremiumPlan] = {
        Plan.MONTH: PremiumPlan(
            code=Plan.MONTH,
            label="1 месяц",
            duration=timedelta(days=30),
            price=Decimal("300.00"),
        ),
    }

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="premium_payments",
    )
    plan = models.CharField(max_length=20, choices=Plan.choices)
    method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    amount = models.DecimalField(
        max_digits=9,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    currency = models.CharField(max_length=3, default="RUB")
    reference = models.CharField(max_length=40, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"PremiumPayment({self.user.username}, {self.plan}, {self.status})"

    @classmethod
    def get_plan(cls, code: str) -> PremiumPlan:
        plan = cls.PLAN_CONFIGURATION.get(code)
        if not plan:
            raise ValueError(f"Unknown premium plan: {code}")
        return plan

    @classmethod
    def get_plan_choices_with_price(cls):
        for plan in cls.PLAN_CONFIGURATION.values():
            yield (plan.code, f"{plan.label} — {plan.price} ₽")

    def get_plan_duration(self) -> timedelta:
        return self.get_plan(self.plan).duration

    def get_plan_price(self) -> Decimal:
        return self.get_plan(self.plan).price

    def mark_paid(self):
        self.status = self.Status.PAID
        self.save(update_fields=["status"])

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        previous_status = None
        if not is_new:
            previous_status = (
                PremiumPayment.objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
        if not self.reference:
            self.reference = uuid.uuid4().hex[:12].upper()
        if not self.amount:
            self.amount = self.get_plan(self.plan).price
        if not self.currency:
            self.currency = "RUB"
        super().save(*args, **kwargs)

        status_changed_to_paid = (
            self.status == self.Status.PAID
            and (is_new or previous_status != self.status)
        )
        if status_changed_to_paid:
            if not self.paid_at:
                self.paid_at = timezone.now()
                super().save(update_fields=["paid_at"])
            self._ensure_subscription()

    def _ensure_subscription(self):
        if hasattr(self, "subscription") and self.subscription:
            return
        start = self.paid_at or timezone.now()
        end = start + self.get_plan_duration()
        PremiumSubscription.objects.create(
            user=self.user,
            start_at=start,
            end_at=end,
            source=PremiumSubscription.Source.PURCHASE,
            payment=self,
        )


class PremiumSubscription(models.Model):
    class Source(models.TextChoices):
        PURCHASE = ("purchase", "Покупка")
        ADMIN = ("admin", "Выдано администратором")
        COMPENSATION = ("compensation", "Компенсация")

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="premium_subscriptions",
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.PURCHASE,
    )
    granted_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        related_name="granted_premium_subscriptions",
        on_delete=models.SET_NULL,
    )
    payment = models.OneToOneField(
        "PremiumPayment",
        null=True,
        blank=True,
        related_name="subscription",
        on_delete=models.SET_NULL,
    )

    class Meta:
        ordering = ("-end_at",)
        indexes = [
            models.Index(fields=["user", "end_at"]),
        ]

    def __str__(self) -> str:
        return f"PremiumSubscription({self.user.username}, до {self.end_at:%Y-%m-%d})"

    @property
    def is_active(self) -> bool:
        return self.end_at >= timezone.now()

    def remaining_timedelta(self):
        return max(self.end_at - timezone.now(), timedelta())