from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('shelves', '0004_readingsession'),
    ]

    operations = [
        migrations.DeleteModel(
            name='ReadingSession',
        ),
    ]
