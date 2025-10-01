"""Data and helpers for the literary journey map."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple


@dataclass(frozen=True)
class JourneyStage:
    """Description of a single map stage."""

    number: int
    title: str
    requirement: str
    description: str
    terrain: str
    top: float
    left: float


class BookJourneyMap:
    """Static specification for the updated literary journey."""

    TITLE = "Книжное путешествие"
    SUBTITLE = (
        "15 заданий на карте классиков: выбирайте книгу, завершайте чтение и делитесь впечатлениями, "
        "чтобы исследовать все острова."
    )
    CHECKLIST: Tuple[str, ...] = (
        "Выберите задание на карте и прикрепите к нему книгу из своей библиотеки.",
        "Можно выполнять этапы в любом порядке, но одновременно активен только один.",
        "Когда дочитаете книгу, отметьте прогресс в трекере чтения.",
        "Напишите отзыв — после этого задание автоматически считается выполненным.",
    )
    TERRAIN: Dict[str, Dict[str, str]] = {
        "harbor": {
            "label": "Гавань",
            "hint": "Дружелюбные стартовые задачи для лёгкого входа в игру.",
        },
        "heritage": {
            "label": "Наследие",
            "hint": "Знакомство с классикой и обязательными произведениями.",
        },
        "inspiration": {
            "label": "Вдохновение",
            "hint": "Истории о творчестве, путешествиях и поиске идей.",
        },
        "mystery": {
            "label": "Тайна",
            "hint": "Необычные жанры, мистика и экспериментальные сюжеты.",
        },
        "city": {
            "label": "Город",
            "hint": "Книги о людях, сообществах и личных историях.",
        },
    }

    STAGES: Tuple[JourneyStage, ...] = (
        JourneyStage(
            number=1,
            title="Гавань Гюго",
            requirement="Тонкая книга до 200 страниц, чтобы начать плавание легко.",
            description=(
                "Выберите небольшое произведение и расскажите в отзыве, какой момент стал точкой входа в приключение."
            ),
            terrain="harbor",
            top=24,
            left=18,
        ),
        JourneyStage(
            number=2,
            title="Фонарь драматурга",
            requirement="Пьеса или сценарий — всё, что написано для сцены.",
            description="Поделитесь, какого героя вам хотелось бы увидеть на подмостках.",
            terrain="inspiration",
            top=36,
            left=24,
        ),
        JourneyStage(
            number=3,
            title="Мыс романтиков",
            requirement="Французский или европейский роман XIX века.",
            description="Опишите, какую эмоцию автор передаёт сильнее всего.",
            terrain="heritage",
            top=48,
            left=20,
        ),
        JourneyStage(
            number=4,
            title="Чеховская пристань",
            requirement="Сборник рассказов русскоязычного автора.",
            description="Расскажите о сюжете, который зацепил вас больше остальных.",
            terrain="city",
            top=66,
            left=30,
        ),
        JourneyStage(
            number=5,
            title="Дача на острове",
            requirement="Семейная сага или камерная повесть о взаимоотношениях.",
            description="Опишите героя, чьи решения заставили задуматься о своих ценностях.",
            terrain="city",
            top=78,
            left=22,
        ),
        JourneyStage(
            number=6,
            title="Станция письма",
            requirement="Эпистолярный роман или книга в формате дневника.",
            description="Поделитесь цитатой, которую хочется переписать в свой дневник.",
            terrain="inspiration",
            top=70,
            left=40,
        ),
        JourneyStage(
            number=7,
            title="Башня Шекспира",
            requirement="Классическая трагедия или комедия о сильных характерах.",
            description="Расскажите, чему вас научили решения главных героев.",
            terrain="heritage",
            top=22,
            left=58,
        ),
        JourneyStage(
            number=8,
            title="Водопад сонетов",
            requirement="Сборник поэзии или верлибра о любви и поиске вдохновения.",
            description="Поделитесь строкой, которая звучит у вас в голове после чтения.",
            terrain="inspiration",
            top=34,
            left=64,
        ),
        JourneyStage(
            number=9,
            title="Переход интриг",
            requirement="Исторический роман с политическими тайнами.",
            description="Расскажите, какой поворот сюжета оказался самым неожиданным.",
            terrain="mystery",
            top=40,
            left=72,
        ),
        JourneyStage(
            number=10,
            title="Площадь Достоевского",
            requirement="Психологический роман, исследующий внутренний мир героя.",
            description="Опишите конфликт, в котором вы узнаёте себя или современность.",
            terrain="city",
            top=48,
        ),
        JourneyStage(
            number=11,
            title="Подземная галерея",
            requirement="Современный роман о городе или его жителях.",
            description="Расскажите, как автор показывает город как живого персонажа.",
            terrain="city",
            top=56,
            left=68,
        ),
        JourneyStage(
            number=12,
            title="Перекрёсток расследований",
            requirement="Детектив или нуар, где разгадка связана с моральным выбором.",
            description="Поделитесь, удалось ли вам догадаться до развязки раньше героев.",
            terrain="mystery",
            top=62,
            left=76,
        ),
        JourneyStage(
            number=13,
            title="Лабиринт Кафки",
            requirement="Произведение с элементами абсурда или магического реализма.",
            description="Расскажите, какая метафора или образ остались с вами после чтения.",
            terrain="mystery",
            top=70,
            left=84,
        ),
        JourneyStage(
            number=14,
            title="Мастерская превращений",
            requirement="Книга о трансформации героя — личной, профессиональной или мистической.",
            description="Опишите, что помогло персонажу справиться с переменами.",
            terrain="inspiration",
            top=78,
            left=70,
        ),
        JourneyStage(
            number=15,
            title="Порт возвращения",
            requirement="Любимая книга для перечитывания и написания итогового отзыва.",
            description="Расскажите, что заметили в книге теперь и чего не видели раньше.",
            terrain="harbor",
            top=84,
            left=58,
        ),
    )

    @classmethod
    def get_stages(cls) -> Tuple[JourneyStage, ...]:
        """Return the immutable collection of stages."""

        return cls.STAGES

    @classmethod
    def get_stage_count(cls) -> int:
        """Number of stages on the map."""

        return len(cls.STAGES)

    @classmethod
    def get_terrain_legend(cls) -> Iterable[Tuple[str, Dict[str, str]]]:
        """Legend entries sorted by key for stable templates."""

        return tuple((key, cls.TERRAIN[key]) for key in sorted(cls.TERRAIN.keys()))
    
     @classmethod
    def get_stage_by_number(cls, number: int) -> JourneyStage | None:
        """Return a stage definition by its sequential number."""

        for stage in cls.STAGES:
            if stage.number == number:
                return stage
        return None


__all__ = ["BookJourneyMap", "JourneyStage"]
