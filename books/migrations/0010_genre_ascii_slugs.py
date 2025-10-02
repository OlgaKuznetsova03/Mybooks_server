from django.db import migrations, models
from django.utils.text import slugify


CYRILLIC_TO_LATIN = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "yo",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def _transliterate_for_slug(value: str) -> str:
    if not value:
        return ""
    return "".join(CYRILLIC_TO_LATIN.get(ch, ch) for ch in value.lower())


def _build_slug(name: str) -> str:
    return slugify(_transliterate_for_slug(name), allow_unicode=False) or "genre"


def make_genre_slugs_ascii(apps, schema_editor):
    Genre = apps.get_model("books", "Genre")

    for genre in Genre.objects.all().order_by("pk"):
        base_slug = _build_slug(genre.name or "")
        slug_candidate = base_slug
        counter = 2

        while (
            Genre.objects.filter(slug=slug_candidate)
            .exclude(pk=genre.pk)
            .exists()
        ):
            slug_candidate = f"{base_slug}-{counter}"
            counter += 1

        if genre.slug != slug_candidate:
            genre.slug = slug_candidate
            genre.save(update_fields=["slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0009_genre_slug"),
    ]

    operations = [
        migrations.AlterField(
            model_name="genre",
            name="slug",
            field=models.SlugField(blank=True, max_length=150, unique=True),
        ),
        migrations.RunPython(make_genre_slugs_ascii, migrations.RunPython.noop),
    ]
