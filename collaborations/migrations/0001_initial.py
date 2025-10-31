from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("books", "0010_genre_ascii_slugs"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReviewPlatform",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150, unique=True, verbose_name="Название")),
                (
                    "url",
                    models.URLField(
                        blank=True,
                        help_text="При наличии — ссылка на платформу или профиль.",
                        verbose_name="Ссылка",
                    ),
                ),
            ],
            options={
                "verbose_name": "Платформа для отзывов",
                "verbose_name_plural": "Платформы для отзывов",
                "ordering": ("name",),
            },
        ),
        migrations.CreateModel(
            name="AuthorOffer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(help_text="Название книги, цикла или проекта, который предлагается.", max_length=255, verbose_name="Книга или проект")),
                (
                    "offered_format",
                    models.CharField(
                        choices=[
                            ("electronic", "Электронная"),
                            ("paper", "Бумажная"),
                            ("audio", "Аудио"),
                        ],
                        default="electronic",
                        max_length=20,
                        verbose_name="Предлагаемый формат",
                    ),
                ),
                (
                    "synopsis",
                    models.TextField(blank=True, help_text="Краткое описание, чтобы блогеры могли понять тематику.", verbose_name="Кратко о книге"),
                ),
                (
                    "review_requirements",
                    models.TextField(help_text="Опишите ожидания по содержанию, срокам и оформлению.", verbose_name="Требования к отзыву"),
                ),
                (
                    "text_review_length",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Количество слов или знаков. Укажите 0, если нет ограничений.",
                        verbose_name="Желаемый объем текста",
                    ),
                ),
                (
                    "video_review_type",
                    models.CharField(
                        choices=[
                            ("none", "Не требуются"),
                            ("single", "Одно видео"),
                            ("series", "Серия видео"),
                        ],
                        default="none",
                        max_length=20,
                        verbose_name="Формат видеоотзыва",
                    ),
                ),
                ("video_requires_unboxing", models.BooleanField(default=False, verbose_name="Нужна распаковка")),
                ("video_requires_aesthetics", models.BooleanField(default=False, verbose_name="Нужна эстетика/атмосфера")),
                ("video_requires_review", models.BooleanField(default=True, verbose_name="Нужен полноценный отзыв")),
                ("considers_paid_collaboration", models.BooleanField(default=False, verbose_name="Рассматриваю платное сотрудничество")),
                (
                    "allow_regular_users",
                    models.BooleanField(
                        default=False,
                        help_text="Если включено, отзыв могут оставить не только блогеры.",
                        verbose_name="Открыт для обычных читателей",
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="Активно")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "author",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="author_offers",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Автор",
                    ),
                ),
            ],
            options={
                "verbose_name": "Предложение автора",
                "verbose_name_plural": "Предложения авторов",
                "ordering": ("-created_at",),
            },
        ),
        migrations.CreateModel(
            name="BloggerRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(help_text="Например: 'Ищу фэнтези-новинки'", max_length=255, verbose_name="Название заявки")),
                ("accepts_paper", models.BooleanField(default=True, verbose_name="Беру бумажные издания")),
                ("accepts_electronic", models.BooleanField(default=True, verbose_name="Беру электронные издания")),
                ("accepts_audio", models.BooleanField(default=False, verbose_name="Беру аудиокниги")),
                (
                    "additional_info",
                    models.TextField(
                        blank=True,
                        help_text="Расскажите о предпочитаемом формате контента и условиях.",
                        verbose_name="Дополнительные детали",
                    ),
                ),
                (
                    "open_for_paid_collaboration",
                    models.BooleanField(default=False, verbose_name="Готов к платному сотрудничеству"),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="Активна")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "blogger",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="blogger_requests",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Блогер",
                    ),
                ),
                (
                    "preferred_genres",
                    models.ManyToManyField(blank=True, related_name="blogger_requests", to="books.genre", verbose_name="Предпочитаемые жанры"),
                ),
            ],
            options={
                "verbose_name": "Заявка блогера",
                "verbose_name_plural": "Заявки блогеров",
                "ordering": ("-created_at",),
            },
        ),
        migrations.CreateModel(
            name="BloggerRating",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("score", models.IntegerField(default=100)),
                ("successful_collaborations", models.PositiveIntegerField(default=0)),
                ("failed_collaborations", models.PositiveIntegerField(default=0)),
                ("total_collaborations", models.PositiveIntegerField(default=0)),
                (
                    "blogger",
                    models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="blogger_rating", to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={
                "verbose_name": "Рейтинг блогера",
                "verbose_name_plural": "Рейтинги блогеров",
            },
        ),
        migrations.CreateModel(
            name="Collaboration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("negotiation", "Переговоры"),
                            ("active", "В работе"),
                            ("completed", "Завершено"),
                            ("failed", "Просрочено"),
                            ("cancelled", "Отменено"),
                        ],
                        default="negotiation",
                        max_length=20,
                    ),
                ),
                ("deadline", models.DateField(verbose_name="Дедлайн публикации")),
                (
                    "review_links",
                    models.TextField(blank=True, help_text="Укажите ссылки построчно после выполнения условий.", verbose_name="Ссылки на опубликованные отзывы"),
                ),
                ("author_confirmed", models.BooleanField(default=False, verbose_name="Автор подтвердил")),
                ("partner_confirmed", models.BooleanField(default=False, verbose_name="Блогер подтвердил")),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "author",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="collaborations_as_author",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "offer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="collaborations",
                        to="collaborations.authoroffer",
                    ),
                ),
                (
                    "partner",
                    models.ForeignKey(
                        help_text="Блогер или пользователь, который выполняет условия.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="collaborations_as_partner",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "request",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="collaborations",
                        to="collaborations.bloggerrequest",
                    ),
                ),
            ],
            options={
                "verbose_name": "Сотрудничество",
                "verbose_name_plural": "Сотрудничества",
                "ordering": ("-created_at",),
            },
        ),
        migrations.CreateModel(
            name="BloggerPlatformPresence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "custom_platform_name",
                    models.CharField(blank=True, help_text="Если площадки нет в общем списке, укажите её здесь.", max_length=150, verbose_name="Название платформы"),
                ),
                ("followers_count", models.PositiveIntegerField(default=0, verbose_name="Количество подписчиков")),
                (
                    "platform",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="platform_presences",
                        to="collaborations.reviewplatform",
                    ),
                ),
                (
                    "request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="platforms",
                        to="collaborations.bloggerrequest",
                    ),
                ),
            ],
            options={
                "verbose_name": "Площадка блогера",
                "verbose_name_plural": "Площадки блогеров",
            },
        ),
        migrations.AddField(
            model_name="bloggerrequest",
            name="review_formats",
            field=models.ManyToManyField(blank=True, related_name="blogger_requests", to="collaborations.reviewplatform", verbose_name="Где публикую отзывы"),
        ),
        migrations.AddField(
            model_name="authoroffer",
            name="expected_platforms",
            field=models.ManyToManyField(blank=True, related_name="offers", to="collaborations.reviewplatform", verbose_name="Целевые площадки"),
        ),
        migrations.CreateModel(
            name="BloggerRequestResponse",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("message", models.TextField(blank=True, verbose_name="Сообщение")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "На рассмотрении"),
                            ("accepted", "Принято"),
                            ("declined", "Отклонено"),
                            ("withdrawn", "Отозвано"),
                        ],
                        default="pending",
                        max_length=20,
                        verbose_name="Статус",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "author",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="blogger_request_responses",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="responses",
                        to="collaborations.bloggerrequest",
                    ),
                ),
            ],
            options={
                "verbose_name": "Отклик автора на заявку блогера",
                "verbose_name_plural": "Отклики авторов на заявки блогеров",
                "ordering": ("-created_at",),
            },
        ),
        migrations.CreateModel(
            name="AuthorOfferResponse",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("message", models.TextField(blank=True, verbose_name="Сообщение")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "На рассмотрении"),
                            ("accepted", "Принято"),
                            ("declined", "Отклонено"),
                            ("withdrawn", "Отозвано"),
                        ],
                        default="pending",
                        max_length=20,
                        verbose_name="Статус",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "offer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="responses",
                        to="collaborations.authoroffer",
                    ),
                ),
                (
                    "respondent",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="offer_responses",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Отклик на предложение автора",
                "verbose_name_plural": "Отклики на предложения авторов",
                "ordering": ("-created_at",),
            },
        ),
        migrations.AlterUniqueTogether(
            name="bloggerrequestresponse",
            unique_together={("request", "author")},
        ),
        migrations.AlterUniqueTogether(
            name="authorofferresponse",
            unique_together={("offer", "respondent")},
        ),
    ]