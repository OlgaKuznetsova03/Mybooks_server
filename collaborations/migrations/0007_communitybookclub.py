from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("collaborations", "0006_bloggerinvitation_bloggergiveaway"),
    ]

    operations = [
        migrations.CreateModel(
            name="CommunityBookClub",
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
                        help_text="Укажите название или тему клуба.",
                        max_length=200,
                        verbose_name="Название клуба",
                    ),
                ),
                (
                    "city",
                    models.CharField(
                        blank=True,
                        help_text="Если встречи проходят офлайн, напишите город.",
                        max_length=120,
                        verbose_name="Город",
                    ),
                ),
                (
                    "meeting_format",
                    models.CharField(
                        choices=[
                            ("offline", "Офлайн"),
                            ("online", "Онлайн"),
                            ("hybrid", "Гибридно"),
                        ],
                        default="offline",
                        max_length=20,
                        verbose_name="Формат",
                    ),
                ),
                (
                    "meeting_schedule",
                    models.CharField(
                        blank=True,
                        help_text="Например: каждое воскресенье или раз в месяц.",
                        max_length=150,
                        verbose_name="Расписание",
                    ),
                ),
                (
                    "link",
                    models.URLField(
                        blank=True,
                        help_text="Добавьте ссылку на чат или страницу клуба.",
                        verbose_name="Ссылка",
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Коротко расскажите о формате и темах обсуждений.",
                        verbose_name="Описание",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "submitted_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="community_book_clubs",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Автор записи",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
                "verbose_name": "Книжный клуб сообщества",
                "verbose_name_plural": "Книжные клубы сообщества",
            },
        ),
    ]