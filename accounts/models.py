from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


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


class PremiumPayment(models.Model):
    class PaymentMethod(models.TextChoices):
        MIR = ("mir", "Банковская карта МИР")
        SBP = ("sbp", "СБП (Система быстрых платежей)")
        YOOMONEY = ("yoomoney", "ЮMoney кошелёк")
        QIWI = ("qiwi", "QIWI Кошелёк")

    class Status(models.TextChoices):
        PENDING = ("pending", "Ожидает оплаты")
        PAID = ("paid", "Оплачен")
        CANCELLED = ("cancelled", "Отменён")

    class Plan(models.TextChoices):
        MONTH = ("month", "1 месяц")
        QUARTER = ("quarter", "3 месяца")
        YEAR = ("year", "12 месяцев")

    PLAN_CONFIGURATION: dict[str, PremiumPlan] = {
        Plan.MONTH: PremiumPlan(
            code=Plan.MONTH,
            label="1 месяц",
            duration=timedelta(days=30),
            price=Decimal("299.00"),
        ),
        Plan.QUARTER: PremiumPlan(
            code=Plan.QUARTER,
            label="3 месяца",
            duration=timedelta(days=90),
            price=Decimal("749.00"),
        ),
        Plan.YEAR: PremiumPlan(
            code=Plan.YEAR,
            label="12 месяцев",
            duration=timedelta(days=365),
            price=Decimal("2490.00"),
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