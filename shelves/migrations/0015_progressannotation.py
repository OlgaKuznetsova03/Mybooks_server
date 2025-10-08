from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("shelves", "0014_readingfeed"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProgressAnnotation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("quote", "Цитата"), ("note", "Заметка")], max_length=20)),
                ("body", models.TextField()),
                (
                    "location",
                    models.CharField(
                        blank=True,
                        help_text="Страница, глава или отметка, где сделана заметка.",
                        max_length=120,
                    ),
                ),
                ("comment", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "progress",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="annotations",
                        to="shelves.bookprogress",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at", "id"],
            },
        ),
    ]