from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0010_genre_ascii_slugs"),
        ("collaborations", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="authoroffer",
            name="book",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="author_offers",
                to="books.book",
                verbose_name="Книга на сайте",
                help_text="При желании привяжите предложение к книге, которая уже добавлена на сайт.",
            ),
        ),
    ]