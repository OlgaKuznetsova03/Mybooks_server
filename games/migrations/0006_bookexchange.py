from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("books", "0014_alter_ratingcomment_id"),
        ("shelves", "0016_homelibraryentry_read_at"),
        ("games", "0005_forgottenbookentry"),
    ]

    operations = [
        migrations.CreateModel(
            name="BookExchangeChallenge",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("round_number", models.PositiveIntegerField()),
                ("target_books", models.PositiveIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Активный"), ("completed", "Завершён")],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("deadline_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "game",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="book_exchange_challenges",
                        to="games.game",
                    ),
                ),
                (
                    "shelf",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="book_exchange_challenges",
                        to="shelves.shelf",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="book_exchange_challenges",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-started_at"],
                "unique_together": {("user", "round_number")},
            },
        ),
        migrations.CreateModel(
            name="BookExchangeOffer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Ожидает решения"),
                            ("accepted", "Принято"),
                            ("declined", "Отклонено"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("note", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("responded_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "book",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="book_exchange_offers",
                        to="books.book",
                    ),
                ),
                (
                    "challenge",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="offers",
                        to="games.bookexchangechallenge",
                    ),
                ),
                (
                    "offered_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="book_exchange_offers",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"], "unique_together": {("challenge", "book", "offered_by")}},
        ),
        migrations.CreateModel(
            name="BookExchangeAcceptedBook",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("accepted_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("review_submitted_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "book",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="book_exchange_acceptances",
                        to="books.book",
                    ),
                ),
                (
                    "challenge",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="accepted_books",
                        to="games.bookexchangechallenge",
                    ),
                ),
                (
                    "offer",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="accepted_entry",
                        to="games.bookexchangeoffer",
                    ),
                ),
            ],
            options={"ordering": ["accepted_at"], "unique_together": {("challenge", "book")}},
        ),
        migrations.AddField(
            model_name="bookexchangechallenge",
            name="genres",
            field=models.ManyToManyField(
                blank=True,
                related_name="book_exchange_challenges",
                to="books.genre",
            ),
        ),
    ]