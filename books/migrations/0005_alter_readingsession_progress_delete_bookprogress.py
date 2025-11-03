from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('books', '0004_bookprogress_rename_pages_isbnmodel_total_pages_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='readingsession',
            name='progress',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.DeleteModel(
            name='BookProgress',
        ),
    ]
