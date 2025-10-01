"""Data and helpers for the 30-step literary journey map."""

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
    """Static specification for the forest & mountain reading journey."""

    TITLE = "Литературное путешествие"
    SUBTITLE = (
        "30 этапов, на каждом из которых нужно выбрать подходящую книгу, "
        "прочитать её, завершить чтение на сайте и написать отзыв, чтобы двигаться дальше."
    )
    CHECKLIST: Tuple[str, ...] = (
        "Добавьте книгу на текущую точку карты.",
        "Прочитайте выбранную книгу и отмечайте прогресс.",
        "Завершите чтение на сайте, когда книга дочитана.",
        "Напишите отзыв — только после этого открывается следующий этап.",
    )
    TERRAIN: Dict[str, Dict[str, str]] = {
        "forest": {
            "label": "Лес",
            "hint": "Задания, связанные с природой, новыми авторами и лёгким стартом.",
        },
        "river": {
            "label": "Река",
            "hint": "Истории о путешествиях, воде и преодолении пути.",
        },
        "mountain": {
            "label": "Горы",
            "hint": "Самые сложные испытания — крупные тома, классика и награды.",
        },
        "camp": {
            "label": "Стоянка",
            "hint": "Передышка и знакомство с рекомендациями друзей или сообщества.",
        },
        "village": {
            "label": "Поселение",
            "hint": "Тёплые истории про людей и сообщества.",
        },
        "ridge": {
            "label": "Хребет",
            "hint": "Книги с сильными героями и многослойными сюжетами.",
        },
    }

    STAGES: Tuple[JourneyStage, ...] = (
        JourneyStage(
            number=1,
            title="Лесная поляна",
            requirement="Книга объёмом до 200 страниц, чтобы мягко начать путешествие.",
            description=(
                "Выберите лёгкое чтение, добавьте его в точку старта и после завершения "
                "обязательно отметьте прочитанное и отзыв."
            ),
            terrain="forest",
            top=78,
            left=6,
        ),
        JourneyStage(
            number=2,
            title="Сосновый мост",
            requirement="Книга автора из вашей страны или родного города.",
            description=(
                "Поддержите локального автора и поделитесь в отзыве, чем вас зацепил знакомый голос."
            ),
            terrain="forest",
            top=72,
            left=14,
        ),
        JourneyStage(
            number=3,
            title="Таёжная тропа",
            requirement="Новинка последних двух лет.",
            description=(
                "Добавьте свежую историю и расскажите в отзыве, чего ждёте от новых авторов."),
            terrain="forest",
            top=80,
            left=22,
        ),
        JourneyStage(
            number=4,
            title="Дом лесничего",
            requirement="Книга, действие которой проходит в лесу или дикой природе.",
            description="Погрузитесь в атмосферу природы и отметьте самые яркие описания в отзыве.",
            terrain="forest",
            top=68,
            left=30,
        ),
        JourneyStage(
            number=5,
            title="Развилка у ручья",
            requirement="Нон-фикшн о природе, климате или экологичном образе жизни.",
            description="Расскажите, какой совет из книги попробуете воплотить первым.",
            terrain="river",
            top=76,
            left=38,
        ),
        JourneyStage(
            number=6,
            title="Сторожевая башня",
            requirement="Книга, написанная женщиной-автором.",
            description="Отметьте в отзыве, что нового авторка привнесла в знакомую тему.",
            terrain="forest",
            top=66,
            left=46,
        ),
        JourneyStage(
            number=7,
            title="Лагерь следопытов",
            requirement="Первая книга в серии, цикла или трилогии.",
            description="Опишите, захотелось ли продолжить серию после завершения чтения.",
            terrain="camp",
            top=74,
            left=54,
        ),
        JourneyStage(
            number=8,
            title="Водопад идей",
            requirement="Перевод с японского или корейского языка.",
            description="Поделитесь, какие культурные особенности открылись вам при чтении.",
            terrain="river",
            top=62,
            left=60,
        ),
        JourneyStage(
            number=9,
            title="Лунная поляна",
            requirement="История, где важную роль играет ночь или лунный свет.",
            description="Расскажите, как автор использует атмосферу ночи, чтобы усилить сюжет.",
            terrain="forest",
            top=70,
            left=68,
        ),
        JourneyStage(
            number=10,
            title="Горная гряда",
            requirement="Путевые заметки или мемуары о походе, горном или пешем путешествии.",
            description="Отметьте в отзыве, чему вас научил опыт героя-исследователя.",
            terrain="river",
            top=60,
            left=76,
        ),
        JourneyStage(
            number=11,
            title="Небесный перевал",
            requirement="Классическая книга, изданная до 1970 года.",
            description="Расскажите, почему классика всё ещё откликается современному читателю.",
            terrain="mountain",
            top=68,
            left=84,
        ),
        JourneyStage(
            number=12,
            title="Облачное плато",
            requirement="Книга объёмом более 500 страниц.",
            description="Поделитесь, как вам удалось удержать фокус на таком объёмном произведении.",
            terrain="mountain",
            top=56,
            left=90,
        ),
        JourneyStage(
            number=13,
            title="Высокогорное озеро",
            requirement="История, связанная с водой, морем или озёрами.",
            description="В отзыве отметьте, какую роль вода играет в развитии героев.",
            terrain="river",
            top=48,
            left=86,
        ),
        JourneyStage(
            number=14,
            title="Альпийская деревня",
            requirement="Роман о маленьком сообществе или семейной саге.",
            description="Расскажите о персонаже, за которого болели больше всего.",
            terrain="village",
            top=52,
            left=76,
        ),
        JourneyStage(
            number=15,
            title="Пещера эха",
            requirement="Книга в новом для вас жанре.",
            description="Опишите, какие открытия сделали, пробуя непривычное направление.",
            terrain="ridge",
            top=44,
            left=68,
        ),
        JourneyStage(
            number=16,
            title="Горный приют",
            requirement="Книга по рекомендации друга или участника сообщества ReadTogether.",
            description="Отметьте в отзыве, кто подсказал книгу и оправдались ли ожидания.",
            terrain="camp",
            top=48,
            left=58,
        ),
        JourneyStage(
            number=17,
            title="Обсерватория",
            requirement="Популярная наука или научно-популярная литература.",
            description="Расскажите, какой факт или идея поразили вас больше всего.",
            terrain="ridge",
            top=40,
            left=50,
        ),
        JourneyStage(
            number=18,
            title="Метеорный хребет",
            requirement="Книга, где действие связано с космосом или небесными телами.",
            description="Опишите, как автор сочетает научную фантазию и эмоции героев.",
            terrain="mountain",
            top=46,
            left=40,
        ),
        JourneyStage(
            number=19,
            title="Древние руины",
            requirement="Исторический роман о событиях до 1900 года.",
            description="Расскажите, чему вас научила эпоха, описанная в книге.",
            terrain="ridge",
            top=38,
            left=32,
        ),
        JourneyStage(
            number=20,
            title="Высотный лагерь",
            requirement="Книга, отмеченная престижной литературной премией.",
            description="Поделитесь, оправдывает ли книга полученную награду.",
            terrain="mountain",
            top=42,
            left=22,
        ),
        JourneyStage(
            number=21,
            title="Ледяной мост",
            requirement="Перевод со скандинавского языка.",
            description="В отзыве расскажите о настроении северной истории.",
            terrain="river",
            top=34,
            left=14,
        ),
        JourneyStage(
            number=22,
            title="Хрустальная поляна",
            requirement="Сборник поэзии или поэтический роман.",
            description="Поделитесь любимой строкой и почему она вас задела.",
            terrain="forest",
            top=28,
            left=20,
        ),
        JourneyStage(
            number=23,
            title="Ветряной перевал",
            requirement="Книга с сильной женской главной героиней.",
            description="Опишите, как персонаж справляется с испытаниями.",
            terrain="ridge",
            top=32,
            left=30,
        ),
        JourneyStage(
            number=24,
            title="Дом пастуха",
            requirement="Подростковая или middle grade история.",
            description="Вспомните, что бы вы сказали юной версии себя после прочтения.",
            terrain="village",
            top=24,
            left=38,
        ),
        JourneyStage(
            number=25,
            title="Утёс звёздопада",
            requirement="Книга автора из Латинской Америки, Африки или Азии.",
            description="Поделитесь, что нового о культуре вы узнали из повествования.",
            terrain="mountain",
            top=30,
            left=48,
        ),
        JourneyStage(
            number=26,
            title="Ледниковая арка",
            requirement="Роман с нелинейным или двухвременным повествованием.",
            description="Расскажите, как автор удерживает интригу между разными линиями.",
            terrain="mountain",
            top=22,
            left=58,
        ),
        JourneyStage(
            number=27,
            title="Сторожевая скала",
            requirement="Детектив, триллер или загадочная история.",
            description="Опишите, удалось ли вам разгадать тайну раньше финала.",
            terrain="ridge",
            top=28,
            left=68,
        ),
        JourneyStage(
            number=28,
            title="Солнечный склон",
            requirement="Мемуары или автобиография о личных переменах.",
            description="Расскажите, какой совет автора забираете с собой.",
            terrain="camp",
            top=18,
            left=76,
        ),
        JourneyStage(
            number=29,
            title="Гребень рассвета",
            requirement="Сборник рассказов или антология.",
            description="Отметьте любимый рассказ и чему он вас научил.",
            terrain="mountain",
            top=24,
            left=86,
        ),
        JourneyStage(
            number=30,
            title="Огненный лагерь",
            requirement="Повторное чтение любимой книги, чтобы завершить круг.",
            description="Поделитесь, как изменилось впечатление от книги при перечитывании.",
            terrain="camp",
            top=12,
            left=94,
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


__all__ = ["BookJourneyMap", "JourneyStage"]
