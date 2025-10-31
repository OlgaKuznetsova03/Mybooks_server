from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("books", "0010_genre_ascii_slugs"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReadingClub",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255, verbose_name="Название")),
                ("description", models.TextField(blank=True, verbose_name="Описание")),
                ("start_date", models.DateField(verbose_name="Дата начала")),
                ("end_date", models.DateField(blank=True, null=True, verbose_name="Дата окончания")),
                (
                    "join_policy",
                    models.CharField(
                        choices=[("open", "Открыто для всех"), ("request", "По запросу")],
                        default="open",
                        max_length=20,
                        verbose_name="Присоединение",
                    ),
                ),
                ("slug", models.SlugField(unique=True, verbose_name="URL")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
                (
                    "book",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reading_clubs",
                        to="books.book",
                        verbose_name="Книга",
                    ),
                ),
                (
                    "creator",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="created_reading_clubs",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Создатель",
                    ),
                ),
            ],
            options={
                "verbose_name": "Совместное чтение",
                "verbose_name_plural": "Совместные чтения",
                "ordering": ("-start_date", "-created_at"),
            },
        ),
        migrations.CreateModel(
            name="ReadingParticipant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[("approved", "Участник"), ("pending", "Ожидает подтверждения")],
                        default="approved",
                        max_length=20,
                        verbose_name="Статус",
                    ),
                ),
                ("joined_at", models.DateTimeField(auto_now_add=True, verbose_name="Присоединился")),
                (
                    "reading",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="participants",
                        to="reading_clubs.readingclub",
                        verbose_name="Совместное чтение",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reading_participations",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Пользователь",
                    ),
                ),
            ],
            options={
                "verbose_name": "Участник совместного чтения",
                "verbose_name_plural": "Участники совместных чтений",
            },
        ),
        migrations.CreateModel(
            name="ReadingNorm",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255, verbose_name="Название нормы")),
                ("description", models.TextField(blank=True, verbose_name="Описание")),
                ("order", models.PositiveIntegerField(default=1, verbose_name="Порядок")),
                (
                    "discussion_opens_at",
                    models.DateField(verbose_name="Дата открытия обсуждения"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
                (
                    "reading",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="topics",
                        to="reading_clubs.readingclub",
                        verbose_name="Совместное чтение",
                    ),
                ),
            ],
            options={
                "verbose_name": "Норма чтения",
                "verbose_name_plural": "Нормы чтения",
                "ordering": ("order", "discussion_opens_at", "id"),
            },
        ),
        migrations.CreateModel(
            name="DiscussionPost",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("content", models.TextField(verbose_name="Сообщение")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
                (
                    "author",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reading_posts",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Автор",
                    ),
                ),
                (
                    "topic",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="posts",
                        to="reading_clubs.readingnorm",
                        verbose_name="Тема",
                    ),
                ),
            ],
            options={
                "verbose_name": "Сообщение обсуждения",
                "verbose_name_plural": "Сообщения обсуждений",
                "ordering": ("created_at", "id"),
            },
        ),
        migrations.AlterUniqueTogether(
            name="readingparticipant",
            unique_together={("reading", "user")},
        ),
    ]