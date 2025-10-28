from django.db import migrations, models


def mark_game_shelves(apps, schema_editor):
    Shelf = apps.get_model("shelves", "Shelf")
    Challenge = apps.get_model("games", "BookExchangeChallenge")
    shelf_ids = list(Challenge.objects.values_list("shelf_id", flat=True).distinct())
    if not shelf_ids:
        return
    Shelf.objects.filter(id__in=shelf_ids).update(is_managed=True, is_public=False)


def unmark_game_shelves(apps, schema_editor):
    Shelf = apps.get_model("shelves", "Shelf")
    Challenge = apps.get_model("games", "BookExchangeChallenge")
    shelf_ids = list(Challenge.objects.values_list("shelf_id", flat=True).distinct())
    if not shelf_ids:
        return
    Shelf.objects.filter(id__in=shelf_ids).update(is_managed=False)


class Migration(migrations.Migration):

    dependencies = [
        ("shelves", "0016_homelibraryentry_read_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="shelf",
            name="is_managed",
            field=models.BooleanField(
                default=False,
                help_text="Полка создаётся и поддерживается системой и скрыта из пользовательских списков.",
            ),
        ),
        migrations.RunPython(mark_game_shelves, unmark_game_shelves),
    ]