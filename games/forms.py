from django import forms

from django.core.exceptions import ValidationError

from books.models import Book, Genre
from shelves.models import Shelf, ShelfItem
from shelves.services import (
    DEFAULT_HOME_LIBRARY_SHELF,
    DEFAULT_READING_SHELF,
    DEFAULT_WANT_SHELF,
    ALL_DEFAULT_READ_SHELF_NAMES,
    get_home_library_shelf,
)

from .models import (
    BookJourneyAssignment,
    BookExchangeOffer,
    ForgottenBookEntry,
)
from .services.book_exchange import BookExchangeGame
from .services.book_journey import BookJourneyMap
from .services.forgotten_books import ForgottenBooksGame
from .services.read_before_buy import ReadBeforeBuyGame


class ReadBeforeBuyEnrollForm(forms.Form):
    shelf = forms.ModelChoiceField(
        queryset=Shelf.objects.none(),
        label="Выберите полку",
        empty_label=None,
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not user:
            self.fields["shelf"].queryset = Shelf.objects.none()
            return
        home_shelf = get_home_library_shelf(user)
        state_exists = ReadBeforeBuyGame.get_state_for_shelf(user, home_shelf)
        if state_exists:
            queryset = Shelf.objects.none()
        else:
            queryset = Shelf.objects.filter(pk=home_shelf.pk)
        self.fields["shelf"].queryset = queryset
        self.fields["shelf"].widget.attrs.setdefault("class", "form-select")
        if not state_exists:
            self.fields["shelf"].label = f"Полка «{home_shelf.name}»"


ALLOWED_SHELF_NAMES = [
    DEFAULT_HOME_LIBRARY_SHELF,
    DEFAULT_WANT_SHELF,
    DEFAULT_READING_SHELF,
]


class BookJourneyAssignForm(forms.Form):
    stage_number = forms.ChoiceField(widget=forms.HiddenInput)
    book = forms.ModelChoiceField(
        queryset=Book.objects.none(),
        label="Книга для задания",
        empty_label="Выберите книгу",
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        stages = BookJourneyMap.get_stages()
        self.fields["stage_number"].choices = [
            (stage.number, f"#{stage.number} — {stage.title}") for stage in stages
        ]
        book_field = self.fields["book"]
        book_field.widget.attrs.setdefault("class", "form-select")
        if not user:
            book_field.queryset = Book.objects.none()
            return
        allowed_items = ShelfItem.objects.filter(
            shelf__user=user, shelf__name__in=ALLOWED_SHELF_NAMES
        )
        read_book_ids = ShelfItem.objects.filter(
            shelf__user=user, shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES
        ).values_list("book_id", flat=True)
        book_ids = (
            allowed_items.exclude(book_id__in=read_book_ids)
            .values_list("book_id", flat=True)
            .distinct()
        )
        queryset = Book.objects.filter(id__in=book_ids).order_by("title")
        book_field.queryset = queryset

    def clean(self):
        cleaned_data = super().clean()
        user = self.user
        if not user:
            raise ValidationError("Требуется авторизация для прикрепления книги.")
        stage_number = cleaned_data.get("stage_number")
        if stage_number is None:
            raise ValidationError("Не удалось определить задание.")
        try:
            stage_number = int(stage_number)
        except (TypeError, ValueError):
            raise ValidationError("Некорректный номер задания.")
        stage = BookJourneyMap.get_stage_by_number(stage_number)
        if not stage:
            raise ValidationError("Такого задания на карте нет.")
        book = cleaned_data.get("book")
        if not book:
            return cleaned_data
        if ShelfItem.objects.filter(
            shelf__user=user,
            shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
            book=book,
        ).exists():
            raise ValidationError("Прочитанные книги нельзя прикреплять к заданию.")
        if not ShelfItem.objects.filter(
            shelf__user=user, shelf__name__in=ALLOWED_SHELF_NAMES, book=book
        ).exists():
            raise ValidationError(
                "Добавьте книгу в домашнюю библиотеку или на полку «Хочу прочитать»/«Читаю», прежде чем прикреплять к заданию."
            )
        existing = BookJourneyAssignment.objects.filter(
            user=user, stage_number=stage_number
        ).first()
        if existing and existing.is_completed:
            raise ValidationError("Завершённое задание нельзя переиграть повторно.")
        cleaned_data["stage_number"] = stage_number
        return cleaned_data


class BookJourneyReleaseForm(forms.Form):
    stage_number = forms.IntegerField(widget=forms.HiddenInput)

    def clean_stage_number(self):
        number = self.cleaned_data["stage_number"]
        stage = BookJourneyMap.get_stage_by_number(number)
        if not stage:
            raise ValidationError("Этап на карте не найден.")
        return number


class ForgottenBooksAddForm(forms.Form):
    book = forms.ModelChoiceField(
        queryset=Book.objects.none(),
        label="Выберите книгу",
        empty_label="Книга из домашней библиотеки",
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        field = self.fields["book"]
        field.widget.attrs.setdefault("class", "form-select")
        if not user:
            field.queryset = Book.objects.none()
            return
        home_shelf = get_home_library_shelf(user)
        queryset = Book.objects.filter(
            shelf_items__shelf=home_shelf,
        ).exclude(
            shelf_items__shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
            shelf_items__shelf__user=user,
        )
        queryset = queryset.exclude(
            forgotten_book_entries__user=user
        ).distinct().order_by("title")
        field.queryset = queryset

    def clean(self):
        cleaned = super().clean()
        user = self.user
        if not user:
            raise ValidationError("Авторизуйтесь, чтобы управлять списком книг.")
        book = cleaned.get("book")
        if not book:
            return cleaned
        if not ForgottenBooksGame.can_add_more(user):
            raise ValidationError("Вы уже добавили 12 книг в челлендж.")
        return cleaned


class ForgottenBooksRemoveForm(forms.Form):
    entry_id = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_entry_id(self):
        entry_id = self.cleaned_data["entry_id"]
        try:
            entry = ForgottenBookEntry.objects.get(pk=entry_id, user=self.user)
        except ForgottenBookEntry.DoesNotExist as exc:  # pragma: no cover - validation
            raise ValidationError("Книга не найдена в вашем списке.") from exc
        if entry.is_selected:
            raise ValidationError("Нельзя удалить выбранную книгу.")
        self.cleaned_data["entry"] = entry
        return entry_id


class BookExchangeStartForm(forms.Form):
    target_books = forms.IntegerField(
        min_value=1,
        max_value=50,
        label="Сколько книг готовы принять",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    genres = forms.ModelMultipleChoiceField(
        queryset=Genre.objects.none(),
        label="Предпочтительные жанры",
        widget=forms.SelectMultiple(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["genres"].queryset = Genre.objects.all().order_by("name")

    def clean(self):
        cleaned = super().clean()
        user = self.user
        if not user:
            raise ValidationError("Авторизуйтесь, чтобы начать игру.")
        if BookExchangeGame.has_active_challenge(user):
            raise ValidationError("Сначала завершите текущий раунд.")
        genres = cleaned.get("genres")
        if not genres:
            raise ValidationError("Выберите хотя бы один жанр.")
        return cleaned


class BookExchangeOfferForm(forms.Form):
    book = forms.ModelChoiceField(
        queryset=Book.objects.none(),
        label="Книга из вашей полки «Прочитал»",
        empty_label="Выберите книгу",
    )

    def __init__(self, *args, user=None, challenge=None, **kwargs):
        self.user = user
        self.challenge = challenge
        super().__init__(*args, **kwargs)
        field = self.fields["book"]
        field.widget.attrs.setdefault("class", "form-select")
        if not user or not challenge:
            field.queryset = Book.objects.none()
            return
        read_items = ShelfItem.objects.filter(
            shelf__user=user,
            shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
        )
        genre_ids = list(challenge.genres.values_list("id", flat=True))
        if genre_ids:
            read_items = read_items.filter(book__genres__id__in=genre_ids)
        book_ids = read_items.values_list("book_id", flat=True).distinct()
        field.queryset = Book.objects.filter(id__in=book_ids).order_by("title")

    def clean(self):
        cleaned = super().clean()
        user = self.user
        challenge = self.challenge
        if not user or not challenge:
            raise ValidationError("Не удалось определить игру для предложения.")
        book = cleaned.get("book")
        if not book:
            return cleaned
        if user == challenge.user:
            raise ValidationError("Нельзя предлагать книги самому себе.")
        if not ShelfItem.objects.filter(
            shelf__user=user,
            shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
            book=book,
        ).exists():
            raise ValidationError("Добавьте книгу в полку «Прочитал», прежде чем предлагать.")
        if BookExchangeOffer.objects.filter(
            challenge=challenge,
            offered_by=user,
            book=book,
        ).exists():
            raise ValidationError("Вы уже предлагали эту книгу.")
        genre_ids = list(challenge.genres.values_list("id", flat=True))
        if genre_ids and not book.genres.filter(id__in=genre_ids).exists():
            raise ValidationError("Книга не подходит по жанрам игрока.")
        return cleaned


class BookExchangeRespondForm(forms.Form):
    DECISIONS = (
        ("accept", "Принять"),
        ("decline", "Отклонить"),
    )

    offer_id = forms.IntegerField(widget=forms.HiddenInput)
    decision = forms.ChoiceField(choices=DECISIONS, widget=forms.HiddenInput)

    def __init__(self, *args, user=None, challenge=None, **kwargs):
        self.user = user
        self.challenge = challenge
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        user = self.user
        challenge = self.challenge
        if not user or not challenge:
            raise ValidationError("Не удалось определить раунд игры.")
        if user != challenge.user:
            raise ValidationError("Только владелец раунда может управлять предложениями.")
        offer_id = cleaned.get("offer_id")
        decision = cleaned.get("decision")
        try:
            offer = BookExchangeOffer.objects.select_related("challenge", "book", "offered_by").get(
                pk=offer_id,
                challenge=challenge,
            )
        except BookExchangeOffer.DoesNotExist as exc:
            raise ValidationError("Предложение не найдено.") from exc
        if offer.status != BookExchangeOffer.Status.PENDING:
            raise ValidationError("Это предложение уже обработано.")
        if decision == "decline" and not BookExchangeGame.can_decline_offer(
            challenge, additional_decline=1
        ):
            raise ValidationError("Нельзя отклонить более половины предложенных книг.")
        cleaned["offer"] = offer
        cleaned["decision"] = decision
        return cleaned