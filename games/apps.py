from django.apps import AppConfig


class GamesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "games"
    verbose_name = "Игровые механики"

    def ready(self) -> None:  # pragma: no cover - import side effect
        from . import signals  # noqa: F401