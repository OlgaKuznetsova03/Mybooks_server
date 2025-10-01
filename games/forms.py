from django import forms

from django.core.exceptions import ValidationError

from books.models import Book
from shelves.models import Shelf, ShelfItem
from shelves.services import get_home_library_shelf

from .models import BookJourneyAssignment
from .services.book_journey import BookJourneyMap
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
        book_ids = (
            ShelfItem.objects.filter(shelf__user=user)
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
        if not ShelfItem.objects.filter(shelf__user=user, book=book).exists():
            raise ValidationError(
                "Добавьте книгу на любую свою полку, прежде чем прикреплять к заданию."
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