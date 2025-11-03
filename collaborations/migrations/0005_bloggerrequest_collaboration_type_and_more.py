from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('collaborations', '0004_authorofferresponsecomment'),
    ]

    operations = [
        migrations.AddField(
            model_name='bloggerrequest',
            name='collaboration_type',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='bloggerrequest',
            name='platforms',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
