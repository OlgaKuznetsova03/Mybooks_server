from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reading_clubs", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="discussionpost",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.CASCADE,
                related_name="replies",
                to="reading_clubs.discussionpost",
                verbose_name="Ответ на",
            ),
        ),
    ]