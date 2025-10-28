from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("collaborations", "0006_bloggerinvitation_bloggergiveaway"),
    ]

    operations = [
        migrations.AddField(
            model_name="bloggerrequest",
            name="target_audience",
            field=models.CharField(
                choices=[("authors", "Авторов"), ("bloggers", "Блогеров")],
                default="authors",
                help_text="Выберите, кого хотите найти — авторов или блогеров.",
                max_length=20,
                verbose_name="Кого ищу",
            ),
        ),
        migrations.RenameField(
            model_name="bloggerrequestresponse",
            old_name="author",
            new_name="responder",
        ),
        migrations.AddField(
            model_name="bloggerrequestresponse",
            name="blogger_last_read_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bloggerrequestresponse",
            name="last_activity_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bloggerrequestresponse",
            name="last_activity_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="blogger_request_response_updates",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="bloggerrequestresponse",
            name="platform_link",
            field=models.URLField(
                blank=True,
                help_text="Добавьте ссылку на блог или социальную сеть.",
                verbose_name="Ссылка на площадку",
            ),
        ),
        migrations.AddField(
            model_name="bloggerrequestresponse",
            name="responder_last_read_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bloggerrequestresponse",
            name="responder_type",
            field=models.CharField(
                choices=[("author", "Автор"), ("blogger", "Блогер")],
                default="author",
                max_length=20,
                verbose_name="Кто откликнулся",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="bloggerrequestresponse",
            unique_together={("request", "responder")},
        ),
    ]