"""Configuration for Yasnaya Polyana 2026 foreign literature nomination game."""

from ..models import Game


class YasnayaPolyanaForeign2026Game:
    SLUG = "yasnaya-polyana-foreign-2026"
    TITLE = "Номинация «Иностранная литература» — Ясная Поляна 2026"
    DESCRIPTION = (
        "Отмечайте книги из длинного списка номинации, следите за прочитанным и "
        "переходом в короткий список."
    )

    @classmethod
    def get_game(cls) -> Game:
        game, _ = Game.objects.get_or_create(
            slug=cls.SLUG,
            defaults={"title": cls.TITLE, "description": cls.DESCRIPTION, "year": 2026},
        )
        update_fields = []
        if game.year != 2026:
            game.year = 2026
            update_fields.append("year")
        if not game.title:
            game.title = cls.TITLE
            update_fields.append("title")
        if not game.description:
            game.description = cls.DESCRIPTION
            update_fields.append("description")
        if update_fields:
            game.save(update_fields=update_fields)
        return game
