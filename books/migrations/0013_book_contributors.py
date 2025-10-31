from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0012_book_created_at"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="book",
            name="contributors",
            field=models.ManyToManyField(
                blank=True,
                help_text="Пользователи сайта, которые указаны авторами этой книги.",
                related_name="contributed_books",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]