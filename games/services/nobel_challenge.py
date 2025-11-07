"""Static data and helpers for the Nobel laureates reading challenge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple

from ..models import Game


@dataclass(frozen=True)
class NobelStage:
    """Description of a single Nobel laureate stage."""

    number: int
    year: int
    laureate: str

    @property
    def title(self) -> str:
        return f"{self.year} — {self.laureate}"

    @property
    def requirement(self) -> str:
        return (
            "Прочитайте любое произведение лауреата и добавьте свою книгу к этапу."
        )

    @property
    def description(self) -> str:
        return (
            "Когда книга окажется на полке «Прочитал» и вы оставите отзыв, этап будет"
            " засчитан автоматически."
        )


class NobelLaureatesChallenge:
    """Specification of the long-term Nobel laureates challenge."""

    SLUG = "nobel-laureates"
    TITLE = "Прочитай всех нобелевских лауреатов"
    DESCRIPTION = (
        "Последовательно отмечайте книги лауреатов Нобелевской премии по литературе"
        " — от первых наград до современных победителей. Выбирайте любого лауреата,"
        " прикрепляйте книгу с полки «Хочу прочитать» или «Прочитал» и делитесь"
        " впечатлениями, чтобы завершить этап."
    )
    CHECKLIST: Tuple[str, ...] = (
        "Выберите этап и прикрепите книгу лауреата из своих полок «Хочу прочитать»"
        " или «Прочитал/Прочитано».",
        "Этапы можно проходить в любом порядке — выбирайте интересных авторов без"
        " ограничений.",
        "Когда отметите книгу как прочитанную и оставите отзыв, этап завершится"
        " автоматически.",
    )

    STAGES: Tuple[NobelStage, ...] = (
        NobelStage(number=1, year=1901, laureate='СЮЛЛИ-ПРЮДОМ Рене Арман'),
        NobelStage(number=2, year=1902, laureate='МОММЗЕН Теодор'),
        NobelStage(number=3, year=1903, laureate='БЬЁРНСОН Бьёрнстьерне Мартиниус'),
        NobelStage(number=4, year=1904, laureate='МИСТРАЛЬ Фредерик'),
        NobelStage(number=5, year=1904, laureate='ЭЧЕГАРАЙ-И-ЭЙСАГИРРЕ Хосе'),
        NobelStage(number=6, year=1905, laureate='СЕНКЕВИЧ Генрик'),
        NobelStage(number=7, year=1906, laureate='КАРДУЧЧИ Джозуэ'),
        NobelStage(number=8, year=1907, laureate='КИПЛИНГ Джозеф Редьярд'),
        NobelStage(number=9, year=1908, laureate='ЭЙКЕН Рудольф Кристоф'),
        NobelStage(number=10, year=1909, laureate='ЛАГЕРЛЁФ Сельма'),
        NobelStage(number=11, year=1910, laureate='ХЕЙЗЕ Пауль'),
        NobelStage(number=12, year=1911, laureate='МЕТЕРЛИНК Морис'),
        NobelStage(number=13, year=1912, laureate='ГАУПТМАН Герхарт'),
        NobelStage(number=14, year=1913, laureate='ТАГОР Рабиндранат'),
        NobelStage(number=15, year=1915, laureate='РОЛЛАН Ромен'),
        NobelStage(number=16, year=1916, laureate='ХЕЙДЕНСТАМ Карл Густав Вернер фон'),
        NobelStage(number=17, year=1917, laureate='ГЬЕЛЛЕРУП Карл Адольф'),
        NobelStage(number=18, year=1917, laureate='ПОНТОППИДАН Хенрик'),
        NobelStage(number=19, year=1919, laureate='ШПИТТЕЛЕР Карл'),
        NobelStage(number=20, year=1920, laureate='ГАМСУН Кнут'),
        NobelStage(number=21, year=1921, laureate='ФРАНС Анатоль'),
        NobelStage(number=22, year=1922, laureate='БЕНАВЕНТЕ-И-МАРТИНЕС Хасинто'),
        NobelStage(number=23, year=1923, laureate='ЙИТС [ЙЕТС] Уильям Батлер'),
        NobelStage(number=24, year=1924, laureate='РЕЙМОНТ Владислав'),
        NobelStage(number=25, year=1925, laureate='ШОУ Джордж Бернард'),
        NobelStage(number=26, year=1926, laureate='ДЕЛЕДДА Грация'),
        NobelStage(number=27, year=1927, laureate='БЕРГСОН Анри'),
        NobelStage(number=28, year=1928, laureate='УНСЕТ Сигрид'),
        NobelStage(number=29, year=1929, laureate='МАНН Томас'),
        NobelStage(number=30, year=1930, laureate='ЛЬЮИС Синклер'),
        NobelStage(number=31, year=1931, laureate='КАРЛФЕЛЬДТ Эрик Аксель'),
        NobelStage(number=32, year=1932, laureate='ГОЛСУОРСИ Джон'),
        NobelStage(number=33, year=1933, laureate='БУНИН Иван Алексеевич'),
        NobelStage(number=34, year=1934, laureate='ПИРАНДЕЛЛО Луиджи'),
        NobelStage(number=35, year=1936, laureate='О’НИЛ Юджин'),
        NobelStage(number=36, year=1937, laureate='МАРТЕН ДЮ ГАР Роже'),
        NobelStage(number=37, year=1938, laureate='БАК Перл'),
        NobelStage(number=38, year=1939, laureate='СИЛЛАНПЯЯ Франс Эмиль'),
        NobelStage(number=39, year=1944, laureate='ЙЕНСЕН Йоханнес Вильхельм'),
        NobelStage(number=40, year=1945, laureate='МИСТРАЛЬ Габриэла'),
        NobelStage(number=41, year=1946, laureate='ГЕССЕ [ХЕССЕ] Герман'),
        NobelStage(number=42, year=1947, laureate='ЖИД Андре'),
        NobelStage(number=43, year=1948, laureate='ЭЛИОТ Томас Стернз'),
        NobelStage(number=44, year=1949, laureate='ФОЛКНЕР Уильям'),
        NobelStage(number=45, year=1950, laureate='РАССЕЛ Бертран'),
        NobelStage(number=46, year=1951, laureate='ЛАГЕРКВИСТ Пер Фабиан'),
        NobelStage(number=47, year=1952, laureate='МОРИАК Франсуа'),
        NobelStage(number=48, year=1953, laureate='ЧЕРЧИЛЛЬ Уинстон Леонард Спенсер'),
        NobelStage(number=49, year=1954, laureate='ХЭМИНГУЭЙ Эрнест Миллер'),
        NobelStage(number=50, year=1955, laureate='ЛАКСНЕСС Халлдор Кильян'),
        NobelStage(number=51, year=1956, laureate='ХИМЕНЕС Хуан Рамон'),
        NobelStage(number=52, year=1957, laureate='КАМЮ Альбер'),
        NobelStage(number=53, year=1958, laureate='ПАСТЕРНАК Борис Леонидович'),
        NobelStage(number=54, year=1959, laureate='КВАЗИМОДО Сальваторе'),
        NobelStage(number=55, year=1960, laureate='СЕН-ЖОН Перс'),
        NobelStage(number=56, year=1961, laureate='АНДРИЧ Иво'),
        NobelStage(number=57, year=1962, laureate='СТЕЙНБЕК Джон Эрнст'),
        NobelStage(number=58, year=1963, laureate='СЕФЕРИС Йоргос'),
        NobelStage(number=59, year=1964, laureate='САРТР Жан-Поль'),
        NobelStage(number=60, year=1965, laureate='ШОЛОХОВ Михаил Александрович'),
        NobelStage(number=61, year=1966, laureate='АГНОН Шмуэль Йосеф'),
        NobelStage(number=62, year=1966, laureate='ЗАКС Нелли'),
        NobelStage(number=63, year=1967, laureate='АСТУРИАС Мигель Анхель'),
        NobelStage(number=64, year=1968, laureate='КАВАБАТА Ясунари'),
        NobelStage(number=65, year=1969, laureate='БЕККЕТ Сэмюэль'),
        NobelStage(number=66, year=1970, laureate='СОЛЖЕНИЦЫН Александр Исаевич'),
        NobelStage(number=67, year=1971, laureate='НЕРУДА Пабло'),
        NobelStage(number=68, year=1972, laureate='БЁЛЛЬ Генрих Теодор'),
        NobelStage(number=69, year=1973, laureate='УАЙТ Патрик Виктор'),
        NobelStage(number=70, year=1974, laureate='МАРТИНСОН Харри Эдмунд'),
        NobelStage(number=71, year=1974, laureate='ЮНСОН Эйвинд'),
        NobelStage(number=72, year=1975, laureate='МОНТАЛЕ Эудженио'),
        NobelStage(number=73, year=1976, laureate='БЕЛЛОУ Сол'),
        NobelStage(number=74, year=1977, laureate='ВИСЕНТЕ Алейксандре'),
        NobelStage(number=75, year=1978, laureate='ЗИНГЕР Исаак Башевис'),
        NobelStage(number=76, year=1979, laureate='ЭЛИТИС Одисеас'),
        NobelStage(number=77, year=1980, laureate='МИЛОШ Чеслав'),
        NobelStage(number=78, year=1981, laureate='КАНЕТТИ Элиас'),
        NobelStage(number=79, year=1982, laureate='ГАРСИЯ МАРКЕС Габриэль'),
        NobelStage(number=80, year=1983, laureate='ГОЛДИНГ Уильям'),
        NobelStage(number=81, year=1984, laureate='СЕЙФЕРТ Ярослав'),
        NobelStage(number=82, year=1985, laureate='СИМОН Клод Эжен Анри'),
        NobelStage(number=83, year=1986, laureate='ШОЙИНКА Воле'),
        NobelStage(number=84, year=1987, laureate='БРОДСКИЙ Иосиф Александрович'),
        NobelStage(number=85, year=1988, laureate='МАХФУЗ Нагиб'),
        NobelStage(number=86, year=1989, laureate='СЕЛА Камило Хосе'),
        NobelStage(number=87, year=1990, laureate='ПАС Октавио'),
        NobelStage(number=88, year=1991, laureate='ГОРДИМЕР Надин'),
        NobelStage(number=89, year=1992, laureate='УОЛКОТТ Дерек'),
        NobelStage(number=90, year=1993, laureate='МОРРИСОН Тони'),
        NobelStage(number=91, year=1994, laureate='ОЭ Кэндзабуро'),
        NobelStage(number=92, year=1995, laureate='ХИНИ Шеймас'),
        NobelStage(number=93, year=1996, laureate='ШИМБОРСКАЯ Вислава'),
        NobelStage(number=94, year=1997, laureate='ФО Дарио'),
        NobelStage(number=95, year=1998, laureate='САРАМАГО Жозе'),
        NobelStage(number=96, year=1999, laureate='ГРАСС Гюнтер'),
        NobelStage(number=97, year=2000, laureate='СИНЦЗЯНЬ Гао'),
        NobelStage(number=98, year=2001, laureate='НАЙПОЛ Видадхар Сураджпрасад'),
        NobelStage(number=99, year=2002, laureate='КЕРТЕС Имре'),
        NobelStage(number=100, year=2003, laureate='КУТЗЕЕ Джон Максвелл'),
        NobelStage(number=101, year=2004, laureate='ЕЛИНЕК Эльфрида'),
        NobelStage(number=102, year=2005, laureate='ПИНТЕР Гарольд'),
        NobelStage(number=103, year=2006, laureate='ПАМУК Орхан'),
        NobelStage(number=104, year=2007, laureate='ЛЕССИНГ Дорис'),
        NobelStage(number=105, year=2008, laureate='ЛЕКЛЕЗИО Жан-Мари Гюстав'),
        NobelStage(number=106, year=2009, laureate='МЮЛЛЕР Герта'),
        NobelStage(number=107, year=2010, laureate='ВАРГАС ЛЬОСА Марио'),
        NobelStage(number=108, year=2011, laureate='ТРАНСТРЕМЕР Тумас'),
        NobelStage(number=109, year=2012, laureate='МО Янь'),
        NobelStage(number=110, year=2013, laureate='МАНРО Элис'),
        NobelStage(number=111, year=2014, laureate='МОДИАНО Патрик'),
        NobelStage(number=112, year=2015, laureate='АЛЕКСИЕВИЧ Светлана Александровна'),
        NobelStage(number=113, year=2016, laureate='ДИЛАН Боб (Циммерман Роберт Аллен)'),
        NobelStage(number=114, year=2017, laureate='КУДЗУО Исигуро'),
        NobelStage(number=115, year=2018, laureate='ТОКАРЧУК Ольга'),
        NobelStage(number=116, year=2019, laureate='ХАНДКЕ Петер'),
        NobelStage(number=117, year=2020, laureate='ГЛЮК Луиза'),
        NobelStage(number=118, year=2021, laureate='ГУРНА Абдулразак'),
        NobelStage(number=119, year=2022, laureate='ЭРНО Анни'),
        NobelStage(number=120, year=2023, laureate='ФОССЕ Юн'),
        NobelStage(number=121, year=2024, laureate='ГАН Хан'),
        NobelStage(number=122, year=2025, laureate='КРАСНАХОРКАИ Ласло'),
    )

    @classmethod
    def get_game(cls) -> Game:
        game, _ = Game.objects.get_or_create(
            slug=cls.SLUG,
            defaults={
                "title": cls.TITLE,
                "description": cls.DESCRIPTION,
            },
        )
        return game

    @classmethod
    def get_stages(cls) -> Tuple[NobelStage, ...]:
        return cls.STAGES

    @classmethod
    def get_stage_count(cls) -> int:
        return len(cls.STAGES)

    @classmethod
    def get_stage_by_number(cls, number: int) -> NobelStage | None:
        for stage in cls.STAGES:
            if stage.number == number:
                return stage
        return None

    @classmethod
    def iter_stages(cls) -> Iterable[NobelStage]:
        return iter(cls.STAGES)


__all__ = ["NobelLaureatesChallenge", "NobelStage"]