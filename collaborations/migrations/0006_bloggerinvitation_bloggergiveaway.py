from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("collaborations", "0005_bloggerrequest_collaboration_type_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="BloggerInvitation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "platform",
                    models.CharField(
                        choices=[
                            ("telegram", "Telegram"),
                            ("vk", "ВКонтакте"),
                            ("tiktok", "TikTok"),
                            ("youtube", "YouTube"),
                            ("boosty", "Boosty"),
                            ("dzen", "Яндекс Дзен"),
                            ("other", "Другая платформа"),
                        ],
                        default="other",
                        max_length=20,
                        verbose_name="Платформа",
                    ),
                ),
                (
                    "title",
                    models.CharField(
                        help_text="Коротко расскажите, зачем подписываться на ваш канал.",
                        max_length=150,
                        verbose_name="Приглашение",
                    ),
                ),
                (
                    "link",
                    models.URLField(
                        help_text="Добавьте прямую ссылку на канал или сообщество.",
                        verbose_name="Ссылка",
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Расскажите о тематике, расписании публикаций или особенностях.",
                        verbose_name="Подробнее",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "blogger",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="blogger_invitations",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Блогер",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
                "verbose_name": "Приглашение блогера",
                "verbose_name_plural": "Приглашения блогеров",
            },
        ),
        migrations.CreateModel(
            name="BloggerGiveaway",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "title",
                    models.CharField(
                        help_text="Укажите, что можно выиграть или условия участия.",
                        max_length=200,
                        verbose_name="Название розыгрыша",
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Расскажите коротко об условиях и сроках.",
                        verbose_name="Детали",
                    ),
                ),
                (
                    "link",
                    models.URLField(
                        help_text="Добавьте ссылку на пост или страницу с условиями.",
                        verbose_name="Ссылка",
                    ),
                ),
                (
                    "deadline",
                    models.DateField(
                        blank=True,
                        help_text="Если есть конечная дата, укажите её.",
                        null=True,
                        verbose_name="Окончание",
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="Активно")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "blogger",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="blogger_giveaways",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Блогер",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
                "verbose_name": "Розыгрыш блогера",
                "verbose_name_plural": "Розыгрыши блогеров",
            },
        ),
    ]