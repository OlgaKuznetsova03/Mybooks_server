# Generated manually
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0010_game_year'),
    ]

    operations = [
        # Сначала убираем старый unique_together
        migrations.AlterUniqueTogether(
            name='yasnayapolyananominationbook',
            unique_together=set(),
        ),
        
        # Добавляем поле game с default=5 (Ясная Поляна 2026)
        migrations.AddField(
            model_name='yasnayapolyananominationbook',
            name='game',
            field=models.ForeignKey(
                default=5,
                on_delete=django.db.models.deletion.CASCADE,
                to='games.Game',
                db_constraint=False,  # Временно отключаем внешний ключ
            ),
            preserve_default=False,
        ),
        
        # Устанавливаем новый unique_together
        migrations.AlterUniqueTogether(
            name='yasnayapolyananominationbook',
            unique_together={('game', 'book')},
        ),
    ]
