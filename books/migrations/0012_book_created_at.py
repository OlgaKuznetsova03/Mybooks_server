from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0011_ratingcomment"),
    ]

    operations = [
        migrations.AddField(
            model_name="book",
            name="created_at",
            field=models.DateTimeField(default=django.utils.timezone.now, auto_now_add=True),
            preserve_default=False,
        ),
    ]