from django.conf import settings
from django.core.validators import MaxLengthValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("collaborations", "0007_communitybookclub"),
    ]

    operations = [
        migrations.CreateModel(
            name="CollaborationMessage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "text",
                    models.TextField(
                        validators=[MaxLengthValidator(2000)],
                        verbose_name="Сообщение",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "author",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="collaboration_messages",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Автор сообщения",
                    ),
                ),
                (
                    "collaboration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages",
                        to="collaborations.collaboration",
                        verbose_name="Сотрудничество",
                    ),
                ),
            ],
            options={
                "ordering": ("created_at",),
                "verbose_name": "Сообщение сотрудничества",
                "verbose_name_plural": "Сообщения сотрудничества",
            },
        ),
    ]