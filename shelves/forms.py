from typing import Optional
from datetime import timedelta
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from books.models import Book, Genre
from .models import (
    Shelf,
    ShelfItem,
    Event,
    EventParticipant,
    BookProgress,
    CharacterNote,
    HomeLibraryEntry,
)
class ShelfCreateForm(forms.ModelForm):
    class Meta:
        model = Shelf
        fields = ["name", "is_public"]
        labels = {"name": "Название полки", "is_public": "Публичная"}

class AddToShelfForm(forms.Form):
    shelf = forms.ModelChoiceField(
        queryset=Shelf.objects.none(),
        label="Выберите полку",
        empty_label=None
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # показываем только полки текущего пользователя
        self.fields["shelf"].queryset = Shelf.objects.filter(user=user).order_by("-is_default", "name")

class AddToEventForm(forms.Form):
    event = forms.ModelChoiceField(
        queryset=Event.objects.none(),
        label="Выберите марафон/событие",
        empty_label=None
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            ev_ids = EventParticipant.objects.filter(user=user).values_list("event_id", flat=True)
            self.fields["event"].queryset = Event.objects.filter(id__in=ev_ids).order_by("-start_at")


class HomeLibraryQuickAddForm(forms.Form):
    purchase_date = forms.DateField(
        required=False,
        label="Дата покупки",
        help_text="Необязательно: когда книга появилась у вас дома",
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": "form-control form-control-sm",
            }
        ),
    )
class BookProgressNotesForm(forms.ModelForm):
    class Meta:
        model = BookProgress
        fields = ["reading_notes"]
        labels = {
            "reading_notes": "Цитаты, впечатления, реакции",
        }
        widgets = {
            "reading_notes": forms.Textarea(
                attrs={
                    "rows": 5,
                    "class": "form-control",
                    "placeholder": "Фиксируйте цитаты, мысли и эмоции по ходу чтения...",
                }
            ),
        }

class CharacterNoteForm(forms.ModelForm):
    class Meta:
        model = CharacterNote
        fields = ["name", "description"]
        labels = {
            "name": "Имя героя",
            "description": "Описание",
        }
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Как зовут персонажа?",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": "form-control",
                    "placeholder": "Кем является герой, как связан с сюжетом...",
                }
            ),
        }


class BookProgressFormatForm(forms.ModelForm):
    audio_length_input = forms.CharField(
        required=False,
        label="Длительность аудиокниги",
        help_text="Формат ЧЧ:ММ:СС",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Например, 12:45:00",
            }
        ),
    )

    audio_playback_speed = forms.DecimalField(
        required=False,
        min_value=Decimal("0.5"),
        max_value=Decimal("3.0"),
        decimal_places=1,
        label="Скорость прослушивания",
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "0.1",
                "min": "0.5",
                "max": "3.0",
            }
        ),
    )

    class Meta:
        model = BookProgress
        fields = ["format", "custom_total_pages", "audio_playback_speed"]
        labels = {
            "format": "Формат чтения",
            "custom_total_pages": "Количество страниц",
        }
        widgets = {
            "format": forms.Select(attrs={"class": "form-select"}),
            "custom_total_pages": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "1",
                }
            ),
        }

    def __init__(self, *args, book: Optional[Book] = None, **kwargs):
        instance = kwargs.get("instance")
        self.book = book or (instance.book if instance is not None else None)  # type: ignore[assignment]
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.audio_length:
            total_seconds = int(self.instance.audio_length.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.initial["audio_length_input"] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        if not self.instance.custom_total_pages and self.book:
            total = self.book.get_total_pages()
            if total:
                self.fields["custom_total_pages"].widget.attrs.setdefault("placeholder", str(total))

    def clean_audio_length_input(self):
        raw = self.cleaned_data.get("audio_length_input")
        if not raw:
            return None
        parts = raw.split(":")
        if len(parts) != 3:
            raise ValidationError("Используйте формат ЧЧ:ММ:СС")
        try:
            hours, minutes, seconds = (int(part) for part in parts)
        except ValueError:
            raise ValidationError("Часы, минуты и секунды должны быть числами") from None
        if minutes < 0 or minutes >= 60 or seconds < 0 or seconds >= 60 or hours < 0:
            raise ValidationError("Неверное значение времени")
        return timedelta(hours=hours, minutes=minutes, seconds=seconds)

    def clean(self):
        cleaned = super().clean()
        fmt = cleaned.get("format") or BookProgress.FORMAT_PAPER
        custom_pages = cleaned.get("custom_total_pages")
        audio_length = self.cleaned_data.get("audio_length_input")
        speed = cleaned.get("audio_playback_speed")

        if fmt == BookProgress.FORMAT_AUDIO:
            if not audio_length:
                raise ValidationError("Укажите длительность аудиокниги")
            if speed is None:
                cleaned["audio_playback_speed"] = Decimal("1.0")
        else:
            cleaned["audio_playback_speed"] = None
            if not custom_pages:
                total = self.book.get_total_pages() if self.book else None
                if not total:
                    raise ValidationError("Введите количество страниц для этой книги")
                cleaned["custom_total_pages"] = None
            self.cleaned_data["audio_length_input"] = None
        return cleaned

    def save(self, commit=True):
        progress = super().save(commit=False)
        audio_length = self.cleaned_data.get("audio_length_input")
        if progress.format == BookProgress.FORMAT_AUDIO:
            progress.audio_length = audio_length
            if progress.audio_playback_speed is None:
                progress.audio_playback_speed = Decimal("1.0")
            progress.custom_total_pages = None
        else:
            progress.audio_length = None
        if commit:
            progress.save()
        return progress


class HomeLibraryEntryForm(forms.ModelForm):
    class Meta:
        model = HomeLibraryEntry
        fields = [
            "edition",
            "language",
            "format",
            "status",
            "location",
            "shelf_section",
            "acquired_at",
            "is_classic",
            "series_name",
            "custom_genres",
            "is_disposed",
            "disposition_note",
            "notes",
        ]
        labels = {
            "edition": "Издание",
            "language": "Язык экземпляра",
            "format": "Формат",
            "status": "Статус",
            "location": "Где хранится",
            "shelf_section": "Секция/полка",
            "acquired_at": "Дата приобретения",
            "is_classic": "Классика",
            "series_name": "Серия книг",
            "custom_genres": "Жанры",
            "is_disposed": "Продана / отдана",
            "disposition_note": "Комментарий к передаче",
            "notes": "Заметки",
        }
        widgets = {
            "edition": forms.TextInput(attrs={"class": "form-control"}),
            "language": forms.TextInput(attrs={"class": "form-control"}),
            "format": forms.Select(attrs={"class": "form-select"}),
            "status": forms.TextInput(attrs={"class": "form-control"}),
            "location": forms.TextInput(attrs={"class": "form-control"}),
            "shelf_section": forms.TextInput(attrs={"class": "form-control"}),
            "acquired_at": forms.DateInput(
                attrs={"type": "date", "class": "form-control"},
                format="%Y-%m-%d",
            ),
            "is_classic": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "series_name": forms.TextInput(attrs={"class": "form-control"}),
            "custom_genres": forms.SelectMultiple(
                attrs={"class": "form-select", "size": "6"}
            ),
            "is_disposed": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "disposition_note": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}
            ),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        acquired_field = self.fields["acquired_at"]
        existing_formats = list(acquired_field.input_formats or [])
        if "%Y-%m-%d" not in existing_formats:
            existing_formats.insert(0, "%Y-%m-%d")
        acquired_field.input_formats = existing_formats
        acquired_field.widget.format = "%Y-%m-%d"
        if self.instance and self.instance.pk and self.instance.acquired_at:
            self.initial.setdefault("acquired_at", self.instance.acquired_at)

    def clean(self):
        cleaned_data = super().clean()
        is_disposed = cleaned_data.get("is_disposed")
        note = cleaned_data.get("disposition_note", "").strip()
        if is_disposed and not note:
            self.add_error("disposition_note", "Укажите, почему книга выбыла из коллекции.")
        return cleaned_data


class HomeLibraryFilterForm(forms.Form):
    is_classic = forms.ChoiceField(
        required=False,
        label="Классика",
        choices=(
            ("", "Все"),
            ("true", "Только классика"),
            ("false", "Только современная"),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    series = forms.ChoiceField(
        required=False,
        label="Серия",
        choices=[("", "Все серии")],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    genres = forms.ModelMultipleChoiceField(
        required=False,
        label="Жанры",
        queryset=Genre.objects.none(),
        widget=forms.SelectMultiple(
            attrs={"class": "form-select", "size": "6"}
        ),
    )

    def __init__(self, *args, series_choices=None, genre_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        base_choices = [("", "Все серии")]
        if series_choices:
            unique_series = sorted({value for value in series_choices if value})
            base_choices.extend((value, value) for value in unique_series)
        self.fields["series"].choices = base_choices
        if genre_queryset is not None:
            self.fields["genres"].queryset = genre_queryset