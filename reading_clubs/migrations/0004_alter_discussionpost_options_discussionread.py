from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def ensure_readingnorm_pk(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE t.relname = 'reading_clubs_readingnorm'
              AND n.nspname = current_schema()
              AND c.contype = 'p'
            LIMIT 1;
            """
        )
        if cursor.fetchone():
            return
        cursor.execute(
            """
            ALTER TABLE reading_clubs_readingnorm
                ADD CONSTRAINT reading_clubs_readingnorm_id_pk PRIMARY KEY (id);
            """
        )


def drop_readingnorm_pk(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            ALTER TABLE reading_clubs_readingnorm
                DROP CONSTRAINT IF EXISTS reading_clubs_readingnorm_id_pk;
            """
        )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('reading_clubs', '0003_alter_readingclub_slug'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='discussionpost',
            options={'ordering': ('created_at', 'id')},
        ),
        migrations.RunPython(
            ensure_readingnorm_pk,
            reverse_code=drop_readingnorm_pk,
        ),
        migrations.CreateModel(
            name='DiscussionRead',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('last_read_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Последний просмотр')),
                ('topic', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='read_statuses', to='reading_clubs.readingnorm', verbose_name='Тема')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reading_discussion_reads', to=settings.AUTH_USER_MODEL, verbose_name='Пользователь')),
            ],
            options={
                'verbose_name': 'Просмотр обсуждения',
                'verbose_name_plural': 'Просмотры обсуждений',
                'unique_together': {('user', 'topic')},
            },
        ),
    ]