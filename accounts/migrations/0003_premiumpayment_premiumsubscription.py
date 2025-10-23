from decimal import Decimal

from django.conf import settings
from django.core import validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_profile_link1_profile_link2_profile_link3_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PremiumPayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("plan", models.CharField(choices=[("month", "1 месяц"), ("quarter", "3 месяца"), ("year", "12 месяцев")], max_length=20)),
                ("method", models.CharField(choices=[("mir", "Банковская карта МИР"), ("sbp", "СБП (Система быстрых платежей)"), ("yoomoney", "ЮMoney кошелёк"), ("qiwi", "QIWI Кошелёк")], max_length=20)),
                ("status", models.CharField(choices=[("pending", "Ожидает оплаты"), ("paid", "Оплачен"), ("cancelled", "Отменён")], default="pending", max_length=20)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=9, validators=[validators.MinValueValidator(Decimal("0.00"))])),
                ("currency", models.CharField(default="RUB", max_length=3)),
                ("reference", models.CharField(editable=False, max_length=40, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="premium_payments", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.CreateModel(
            name="PremiumSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("start_at", models.DateTimeField()),
                ("end_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("source", models.CharField(choices=[("purchase", "Покупка"), ("admin", "Выдано администратором"), ("compensation", "Компенсация")], default="purchase", max_length=20)),
                ("granted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="granted_premium_subscriptions", to=settings.AUTH_USER_MODEL)),
                ("payment", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="subscription", to="accounts.premiumpayment")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="premium_subscriptions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("-end_at",),
            },
        ),
        migrations.AddIndex(
            model_name="premiumsubscription",
            index=models.Index(fields=["user", "end_at"], name="accounts_premium_sub_user_end_idx"),
        ),
    ]