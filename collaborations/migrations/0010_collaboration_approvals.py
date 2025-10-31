from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("collaborations", "0009_add_default_review_platforms"),
    ]

    operations = [
        migrations.AddField(
            model_name="collaboration",
            name="author_approved",
            field=models.BooleanField(
                default=False,
                verbose_name="Автор подтвердил сотрудничество",
            ),
        ),
        migrations.AddField(
            model_name="collaboration",
            name="partner_approved",
            field=models.BooleanField(
                default=False,
                verbose_name="Партнёр подтвердил сотрудничество",
            ),
        ),
    ]