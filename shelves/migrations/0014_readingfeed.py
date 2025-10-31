from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("shelves", "0013_bookprogressmedium_and_log_update"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("books", "0010_genre_ascii_slugs"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReadingFeedEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "medium",
                    models.CharField(
                        choices=[
                            ("paper", "Бумажная книга"),
                            ("ebook", "Электронная книга"),
                            ("audiobook", "Аудиокнига"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "current_page",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Текущая страница или эквивалент страниц в момент обновления.",
                        max_digits=7,
                        null=True,
                    ),
                ),
                ("percent", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ("reaction", models.TextField(blank=True)),
                ("is_public", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "book",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reading_feed_entries",
                        to="books.book",
                    ),
                ),
                (
                    "progress",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="feed_entries",
                        to="shelves.bookprogress",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reading_feed_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ReadingFeedComment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "entry",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comments",
                        to="shelves.readingfeedentry",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reading_feed_comments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
    ]