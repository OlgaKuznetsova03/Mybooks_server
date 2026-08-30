from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def ensure_discussionpost_pk(apps, schema_editor):
    """Repair the primary key missing from some legacy production databases."""
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE t.relname = 'reading_clubs_discussionpost'
              AND n.nspname = current_schema()
              AND c.contype = 'p'
            LIMIT 1;
            """
        )
        if cursor.fetchone():
            return

        cursor.execute(
            """
            ALTER TABLE reading_clubs_discussionpost
                ADD CONSTRAINT reading_clubs_discussionpost_id_pk PRIMARY KEY (id);
            """
        )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("reading_clubs", "0004_alter_discussionpost_options_discussionread"),
    ]

    operations = [
        migrations.RunPython(
            ensure_discussionpost_pk,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.CreateModel(
            name="DiscussionPostReport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reason", models.CharField(choices=[("spam", "Спам или реклама"), ("harassment", "Оскорбления или травля"), ("hate", "Язык вражды"), ("dangerous", "Опасный или незаконный контент"), ("sexual", "Контент сексуального характера"), ("personal_data", "Персональные данные"), ("other", "Другое")], max_length=32, verbose_name="Причина")),
                ("details", models.TextField(blank=True, verbose_name="Комментарий")),
                ("content_snapshot", models.TextField(verbose_name="Текст сообщения")),
                ("topic_snapshot", models.CharField(blank=True, max_length=255, verbose_name="Обсуждение")),
                ("status", models.CharField(choices=[("pending", "Ожидает проверки"), ("reviewing", "На проверке"), ("action_taken", "Приняты меры"), ("rejected", "Нарушение не найдено")], default="pending", max_length=24, verbose_name="Статус")),
                ("moderator_note", models.TextField(blank=True, verbose_name="Заметка модератора")),
                ("reviewed_at", models.DateTimeField(blank=True, null=True, verbose_name="Проверено")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
                ("post", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reports", to="reading_clubs.discussionpost", verbose_name="Сообщение")),
                ("reported_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reported_reading_posts", to=settings.AUTH_USER_MODEL, verbose_name="Автор сообщения")),
                ("reporter", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reading_post_reports", to=settings.AUTH_USER_MODEL, verbose_name="Отправитель жалобы")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_reading_post_reports", to=settings.AUTH_USER_MODEL, verbose_name="Проверил")),
            ],
            options={
                "verbose_name": "Жалоба на сообщение",
                "verbose_name_plural": "Жалобы на сообщения",
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddConstraint(
            model_name="discussionpostreport",
            constraint=models.UniqueConstraint(fields=("reporter", "post"), name="unique_reading_post_report_per_user"),
        ),
    ]
