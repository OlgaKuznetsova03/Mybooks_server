from django.db import migrations


PLATFORMS = [
    ("ВК", "https://vk.com"),
    ("ТикТок", "https://www.tiktok.com"),
    ("Телеграм", "https://t.me"),
    ("MAX", ""),
    ("LiveLib", "https://www.livelib.ru"),
    ("LitRes", "https://www.litres.ru"),
]


def add_default_review_platforms(apps, schema_editor):
    ReviewPlatform = apps.get_model("collaborations", "ReviewPlatform")
    for name, url in PLATFORMS:
        ReviewPlatform.objects.update_or_create(name=name, defaults={"url": url})


def remove_default_review_platforms(apps, schema_editor):
    ReviewPlatform = apps.get_model("collaborations", "ReviewPlatform")
    ReviewPlatform.objects.filter(name__in=[name for name, _ in PLATFORMS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("collaborations", "0008_collaborationmessage"),
    ]

    operations = [
        migrations.RunPython(add_default_review_platforms, remove_default_review_platforms),
    ]