from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shelves", "0015_progressannotation"),
    ]

    operations = [
        migrations.AddField(
            model_name="homelibraryentry",
            name="read_at",
            field=models.DateField(
                blank=True,
                help_text="Дата завершения чтения",
                null=True,
            ),
        ),
    ]