from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("collaborations", "0012_merge_20251028_2010"),
    ]

    operations = [
        migrations.AddField(
            model_name="bloggerrequest",
            name="blogger_collaboration_goal",
            field=models.CharField(
                blank=True,
                choices=[
                    ("giveaway", "Совместный розыгрыш"),
                    ("cross_promo", "Взаимореклама"),
                    ("other", "Другое"),
                ],
                default="",
                help_text="Уточните формат сотрудничества с другим блогером.",
                max_length=20,
                verbose_name="Цель поиска блогера",
            ),
        ),
        migrations.AddField(
            model_name="bloggerrequest",
            name="blogger_collaboration_goal_other",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Если выбрали 'Другое', опишите формат сотрудничества.",
                max_length=255,
                verbose_name="Другая цель",
            ),
        ),
        migrations.AddField(
            model_name="bloggerrequest",
            name="blogger_collaboration_platform",
            field=models.ForeignKey(
                blank=True,
                help_text="Выберите площадку, где хотите провести совместный проект.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="blogger_collaboration_requests",
                to="collaborations.reviewplatform",
                verbose_name="Платформа для сотрудничества",
            ),
        ),
        migrations.AddField(
            model_name="bloggerrequest",
            name="blogger_collaboration_platform_other",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Если нужной площадки нет в списке, укажите её вручную.",
                max_length=150,
                verbose_name="Другая платформа",
            ),
        ),
    ]