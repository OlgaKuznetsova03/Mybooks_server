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
            name="ReadingMarathon",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255, verbose_name="Название")),
                ("description", models.TextField(blank=True, verbose_name="Описание")),
                (
                    "cover",
                    models.ImageField(blank=True, null=True, upload_to="marathons/covers/", verbose_name="Обложка"),
                ),
                ("start_date", models.DateField(verbose_name="Дата начала")),
                ("end_date", models.DateField(blank=True, null=True, verbose_name="Дата окончания")),
                (
                    "join_policy",
                    models.CharField(
                        choices=[("open", "Свободное участие"), ("request", "По запросу")],
                        default="open",
                        max_length=20,
                        verbose_name="Вступление",
                    ),
                ),
                (
                    "book_submission_policy",
                    models.CharField(
                        choices=[
                            ("auto", "Участники добавляют книги без подтверждения"),
                            ("approval", "Требуется подтверждение создателя"),
                        ],
                        default="auto",
                        max_length=20,
                        verbose_name="Добавление книг",
                    ),
                ),
                (
                    "completion_policy",
                    models.CharField(
                        choices=[
                            ("auto", "Этап засчитывается автоматически"),
                            ("approval", "Создатель подтверждает выполнение этапа"),
                        ],
                        default="auto",
                        max_length=20,
                        verbose_name="Зачёт этапа",
                    ),
                ),
                ("slug", models.SlugField(max_length=255, unique=True, verbose_name="URL")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
                (
                    "creator",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="created_reading_marathons",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Создатель",
                    ),
                ),
            ],
            options={
                "verbose_name": "Книжный марафон",
                "verbose_name_plural": "Книжные марафоны",
                "ordering": ("-start_date", "-created_at"),
            },
        ),
        migrations.CreateModel(
            name="MarathonParticipant",
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
                    "marathon",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="participants",
                        to="reading_marathons.readingmarathon",
                        verbose_name="Марафон",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="marathon_participations",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Пользователь",
                    ),
                ),
            ],
            options={
                "verbose_name": "Участник марафона",
                "verbose_name_plural": "Участники марафона",
                "unique_together": {("marathon", "user")},
            },
        ),
        migrations.CreateModel(
            name="MarathonTheme",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255, verbose_name="Название темы")),
                ("description", models.TextField(blank=True, verbose_name="Описание")),
                ("order", models.PositiveIntegerField(default=1, verbose_name="Порядок")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
                (
                    "marathon",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="themes",
                        to="reading_marathons.readingmarathon",
                        verbose_name="Марафон",
                    ),
                ),
            ],
            options={
                "verbose_name": "Тема марафона",
                "verbose_name_plural": "Темы марафона",
                "ordering": ("order", "id"),
            },
        ),
        migrations.CreateModel(
            name="MarathonEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("planned", "Запланирована"),
                            ("reading", "Читаю"),
                            ("completed", "Прочитано"),
                        ],
                        default="planned",
                        max_length=20,
                        verbose_name="Статус чтения",
                    ),
                ),
                ("progress", models.PositiveIntegerField(default=0, verbose_name="Прогресс")),
                ("book_approved", models.BooleanField(default=True, verbose_name="Книга подтверждена")),
                (
                    "completion_status",
                    models.CharField(
                        choices=[
                            ("in_progress", "В процессе"),
                            ("awaiting_review", "Ожидает проверки"),
                            ("confirmed", "Подтверждено"),
                        ],
                        default="in_progress",
                        max_length=20,
                        verbose_name="Завершение",
                    ),
                ),
                ("notes", models.TextField(blank=True, verbose_name="Заметки участника")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Добавлено")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
                (
                    "book",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="marathon_entries",
                        to="books.book",
                        verbose_name="Книга",
                    ),
                ),
                (
                    "participant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="entries",
                        to="reading_marathons.marathonparticipant",
                        verbose_name="Участник",
                    ),
                ),
                (
                    "theme",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="entries",
                        to="reading_marathons.marathontheme",
                        verbose_name="Тема",
                    ),
                ),
            ],
            options={
                "verbose_name": "Книга в марафоне",
                "verbose_name_plural": "Книги в марафоне",
                "ordering": ("theme", "-created_at"),
                "unique_together": {("participant", "theme", "book")},
            },
        ),
    ]