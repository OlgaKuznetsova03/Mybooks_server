from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shelves", "0012_remove_homelibraryentry_acquired_from_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="bookprogress",
            name="audio_position",
            field=models.DurationField(
                blank=True,
                help_text="Текущее время прослушивания аудиокниги",
                null=True,
            ),
        ),
        migrations.CreateModel(
            name="BookProgressMedium",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("medium", models.CharField(choices=[("paper", "Бумажная книга"), ("ebook", "Электронная книга"), ("audiobook", "Аудиокнига")], max_length=20)),
                ("current_page", models.PositiveIntegerField(blank=True, null=True)),
                ("total_pages_override", models.PositiveIntegerField(blank=True, null=True)),
                ("audio_position", models.DurationField(blank=True, null=True)),
                ("audio_length", models.DurationField(blank=True, null=True)),
                ("playback_speed", models.DecimalField(blank=True, decimal_places=1, max_digits=3, null=True)),
                ("progress", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="media", to="shelves.bookprogress")),
            ],
            options={
                "unique_together": {("progress", "medium")},
            },
        ),
        migrations.RenameField(
            model_name="readinglog",
            old_name="pages_read",
            new_name="pages_equivalent",
        ),
        migrations.AlterField(
            model_name="readinglog",
            name="pages_equivalent",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=9),
        ),
        migrations.AddField(
            model_name="readinglog",
            name="audio_seconds",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="readinglog",
            name="medium",
            field=models.CharField(choices=[("paper", "Бумажная книга"), ("ebook", "Электронная книга"), ("audiobook", "Аудиокнига")], default="paper", max_length=20),
        ),
        migrations.AlterUniqueTogether(
            name="readinglog",
            unique_together={("progress", "log_date", "medium")},
        ),
    ]