from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserPointEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("book_completed", "Прочитана книга"),
                            ("review_written", "Написан отзыв"),
                            ("club_discussion", "Сообщение в совместном чтении"),
                            ("game_stage_completed", "Этап игры завершён"),
                            ("marathon_confirmed", "Этап марафона зачтён"),
                        ],
                        max_length=64,
                    ),
                ),
                ("points", models.PositiveIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("object_id", models.PositiveBigIntegerField(blank=True, null=True)),
                (
                    "content_type",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_rating_events",
                        to="contenttypes.contenttype",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rating_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at", "-id"),
                "verbose_name": "Событие рейтинга пользователя",
                "verbose_name_plural": "События рейтинга пользователей",
            },
        ),
        migrations.AddIndex(
            model_name="userpointevent",
            index=models.Index(fields=["user", "event_type", "created_at"], name="user_events_idx"),
        ),
        migrations.AddIndex(
            model_name="userpointevent",
            index=models.Index(fields=["content_type", "object_id"], name="user_events_object_idx"),
        ),
    ]