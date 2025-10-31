from django.conf import settings
from django.core.validators import MaxLengthValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0010_genre_ascii_slugs"),
        ("collaborations", "0004_authorofferresponsecomment"),
    ]

    operations = [
        migrations.AddField(
            model_name="bloggerrequest",
            name="collaboration_terms",
            field=models.TextField(
                blank=True,
                help_text="Опишите дедлайны, требования к бартеру или плате.",
                verbose_name="Условия сотрудничества",
            ),
        ),
        migrations.AddField(
            model_name="bloggerrequest",
            name="collaboration_type",
            field=models.CharField(
                choices=[
                    ("barter", "Бартер"),
                    ("paid_only", "Только платно"),
                    ("mixed", "Бартер или оплата"),
                ],
                default="barter",
                help_text="Выберите, в каком формате готовы работать с автором.",
                max_length=20,
                verbose_name="Тип сотрудничества",
            ),
        ),
        migrations.AddField(
            model_name="bloggerrequest",
            name="review_platform_links",
            field=models.TextField(
                blank=True,
                help_text="Укажите ссылки на социальные сети и каналы построчно.",
                verbose_name="Ссылки на площадки",
            ),
        ),
        migrations.RemoveField(
            model_name="bloggerrequest",
            name="open_for_paid_collaboration",
        ),
        migrations.AddField(
            model_name="bloggerrequestresponse",
            name="book",
            field=models.ForeignKey(
                blank=True,
                help_text="Выберите книгу, которую предлагаете блогеру.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="blogger_request_responses",
                to="books.book",
                verbose_name="Книга",
            ),
        ),
        migrations.CreateModel(
            name="BloggerRequestResponseComment",
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
                        validators=[MaxLengthValidator(1000)],
                        verbose_name="Комментарий",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "author",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="blogger_request_response_comments",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Автор комментария",
                    ),
                ),
                (
                    "response",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comments",
                        to="collaborations.bloggerrequestresponse",
                        verbose_name="Отклик",
                    ),
                ),
            ],
            options={
                "ordering": ("created_at",),
                "verbose_name": "Комментарий к отклику блогеру",
                "verbose_name_plural": "Комментарии к откликам блогера",
            },
        ),
    ]