from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0010_genre_ascii_slugs"),
        ("shelves", "0010_homelibraryentry"),
    ]

    operations = [
        migrations.AddField(
            model_name="homelibraryentry",
            name="disposition_note",
            field=models.TextField(
                blank=True,
                help_text="Комментарий, почему книга выбыла",
            ),
        ),
        migrations.AddField(
            model_name="homelibraryentry",
            name="is_classic",
            field=models.BooleanField(
                default=False,
                help_text="Отметьте, если книга относится к классике",
            ),
        ),
        migrations.AddField(
            model_name="homelibraryentry",
            name="is_disposed",
            field=models.BooleanField(
                default=False,
                help_text="Пометка, что книга продана или отдана",
            ),
        ),
        migrations.AddField(
            model_name="homelibraryentry",
            name="series_name",
            field=models.CharField(
                blank=True,
                help_text="Серия, к которой относится экземпляр",
                max_length=150,
            ),
        ),
        migrations.AddField(
            model_name="homelibraryentry",
            name="custom_genres",
            field=models.ManyToManyField(
                blank=True,
                help_text="Жанры именно этого экземпляра",
                related_name="home_library_entries",
                to="books.genre",
            ),
        ),
    ]