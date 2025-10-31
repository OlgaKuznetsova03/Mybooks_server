from django.db import migrations, models
from django.utils.text import slugify


def generate_genre_slugs(apps, schema_editor):
    Genre = apps.get_model("books", "Genre")

    for genre in Genre.objects.all():
        if genre.slug:
            continue

        base_slug = slugify(genre.name or "", allow_unicode=True) or "genre"
        slug_candidate = base_slug
        counter = 2

        while (
            Genre.objects.filter(slug=slug_candidate)
            .exclude(pk=genre.pk)
            .exists()
        ):
            slug_candidate = f"{base_slug}-{counter}"
            counter += 1

        genre.slug = slug_candidate
        genre.save(update_fields=["slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0008_book_edition_group_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="genre",
            name="slug",
            field=models.SlugField(
                allow_unicode=True,
                blank=True,
                max_length=150,
                null=True,
                unique=True,
            ),
        ),
        migrations.RunPython(generate_genre_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="genre",
            name="slug",
            field=models.SlugField(
                allow_unicode=True,
                blank=True,
                max_length=150,
                unique=True,
            ),
        ),
    ]