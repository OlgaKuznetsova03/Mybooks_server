from typing import Optional
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django import forms
from django.core.exceptions import ValidationError

from books.models import Book, Genre
from .models import (
    Shelf,
    ShelfItem,
    Event,
    EventParticipant,
    BookProgress,
    BookProgressMedium,
    CharacterNote,
    ProgressAnnotation,
    HomeLibraryEntry,
    ReadingFeedComment,
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


class ProgressAnnotationForm(forms.ModelForm):
    base_body_placeholder = ""
    base_comment_placeholder = ""

    class Meta:
        model = ProgressAnnotation
        fields = ["body", "location", "comment"]
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": "form-control",
                }
            ),
            "location": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),
            "comment": forms.Textarea(
                attrs={
                    "rows": 2,
                    "class": "form-control",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.base_body_placeholder:
            self.fields["body"].widget.attrs.setdefault(
                "placeholder", self.base_body_placeholder
            )
        if self.base_comment_placeholder:
            self.fields["comment"].widget.attrs.setdefault(
                "placeholder", self.base_comment_placeholder
            )


class ProgressQuoteForm(ProgressAnnotationForm):
    base_body_placeholder = "Запишите точный текст цитаты..."
    base_comment_placeholder = "Что вас зацепило в этой цитате? (необязательно)"

    class Meta(ProgressAnnotationForm.Meta):
        labels = {
            "body": "Текст цитаты",
            "location": "Страница или отметка",
            "comment": "Комментарий",
        }


class ProgressNoteEntryForm(ProgressAnnotationForm):
    base_body_placeholder = "Кратко опишите идею, мысль или момент из книги..."
    base_comment_placeholder = "Дополнительные детали (необязательно)"

    class Meta(ProgressAnnotationForm.Meta):
        labels = {
            "body": "Текст заметки",
            "location": "Глава или сцена",
            "comment": "Комментарий",
        }


class ReadingFeedCommentForm(forms.ModelForm):
    class Meta:
        model = ReadingFeedComment
        fields = ["body"]
        labels = {"body": "Комментарий"}
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 2,
                    "class": "form-control",
                    "placeholder": "Поддержите читателя или задайте вопрос...",
                }
            )
        }


class BookProgressFormatForm(forms.ModelForm):
    formats = forms.MultipleChoiceField(
        choices=BookProgress.FORMAT_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label="Форматы",
        required=True,
    )

    paper_current_page = forms.IntegerField(
        required=False,
        min_value=0,
        label="Текущая страница (бумажный формат)",
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
    )

    aper_total_pages = forms.IntegerField(
        required=False,
        min_value=1,
        label="Страниц в бумажном издании",
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "min": "1",
            }
        ),
        help_text="Используем для синхронизации прогресса между форматами.",
    )

    ebook_current_page = forms.IntegerField(
        required=False,
        min_value=0,
        label="Текущая страница (электронный формат)",
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
    )

    ebook_total_pages = forms.IntegerField(
        required=False,
        min_value=1,
        label="Страниц в электронном издании",
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "min": "1",
            }
        ),
        help_text="Помогает правильно пересчитывать страницы из e-book в бумажный формат.",
    )

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

    audio_position_input = forms.CharField(
        required=False,
        label="Прогресс аудио",
        help_text="Прослушано, формат ЧЧ:ММ:СС",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Например, 02:30:00",
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
        fields = ["custom_total_pages", "audio_playback_speed"]
        labels = {
            "custom_total_pages": "Количество страниц",
        }
        widgets = {
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
        media_map = {}
        if self.instance and self.instance.pk:
            media_map = {
                medium.medium: medium
                for medium in self.instance.media.all()
            }
        selected_formats = list(media_map.keys()) or ([self.instance.format] if self.instance and self.instance.format else [])
        if selected_formats:
            self.initial.setdefault("formats", selected_formats)
        paper_medium = media_map.get(BookProgress.FORMAT_PAPER)
        if paper_medium and paper_medium.current_page is not None:
            self.initial.setdefault("paper_current_page", paper_medium.current_page)
        elif self.instance and self.instance.format == BookProgress.FORMAT_PAPER and self.instance.current_page is not None:
            self.initial.setdefault("paper_current_page", self.instance.current_page)

        if paper_medium and paper_medium.total_pages_override:
            self.initial.setdefault("paper_total_pages", paper_medium.total_pages_override)
        elif self.instance and self.instance.custom_total_pages:
            self.initial.setdefault("paper_total_pages", self.instance.custom_total_pages)

        ebook_medium = media_map.get(BookProgress.FORMAT_EBOOK)
        if ebook_medium and ebook_medium.current_page is not None:
            self.initial.setdefault("ebook_current_page", ebook_medium.current_page)
        elif self.instance and self.instance.format == BookProgress.FORMAT_EBOOK and self.instance.current_page is not None:
            self.initial.setdefault("ebook_current_page", self.instance.current_page)

        if ebook_medium and ebook_medium.total_pages_override:
            self.initial.setdefault("ebook_total_pages", ebook_medium.total_pages_override)

        audio_medium = media_map.get(BookProgress.FORMAT_AUDIO)
        audio_length = None
        audio_position = None
        playback_speed = None
        if audio_medium:
            audio_length = audio_medium.audio_length or self.instance.audio_length
            audio_position = audio_medium.audio_position or self.instance.audio_position
            playback_speed = audio_medium.playback_speed or self.instance.audio_playback_speed
        elif self.instance and self.instance.format == BookProgress.FORMAT_AUDIO:
            audio_length = self.instance.audio_length
            audio_position = self.instance.audio_position
            playback_speed = self.instance.audio_playback_speed

        if audio_length:
            total_seconds = int(audio_length.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.initial["audio_length_input"] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        if audio_position:
            total_seconds = int(audio_position.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.initial["audio_position_input"] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        if playback_speed:
            self.initial.setdefault("audio_playback_speed", playback_speed)
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

    def clean_audio_position_input(self):
        raw = self.cleaned_data.get("audio_position_input")
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
        formats = cleaned.get("formats") or []
        if not formats:
            raise ValidationError("Выберите хотя бы один формат")

        custom_pages = cleaned.get("custom_total_pages")
        paper_total = cleaned.get("paper_total_pages")
        ebook_total = cleaned.get("ebook_total_pages")
        base_total = custom_pages or paper_total or (self.book.get_total_pages() if self.book else None) or ebook_total
        requires_pages = any(fmt in {BookProgress.FORMAT_PAPER, BookProgress.FORMAT_EBOOK} for fmt in formats)
        if requires_pages and not base_total:
            raise ValidationError("Введите количество страниц для этой книги")

        if not custom_pages and not (self.book and self.book.get_total_pages()):
            if paper_total:
                cleaned["custom_total_pages"] = paper_total
            elif ebook_total:
                cleaned["custom_total_pages"] = ebook_total

        for fmt, field in (
            (BookProgress.FORMAT_PAPER, "paper_current_page"),
            (BookProgress.FORMAT_EBOOK, "ebook_current_page"),
        ):
            if fmt in formats:
                value = cleaned.get(field)
                if value is not None and value < 0:
                    self.add_error(field, "Значение не может быть отрицательным")
                if value is not None and base_total and value > base_total:
                    self.add_error(field, "Текущее значение не может превышать количество страниц")

        for fmt, field in (
            (BookProgress.FORMAT_PAPER, "paper_total_pages"),
            (BookProgress.FORMAT_EBOOK, "ebook_total_pages"),
        ):
            if cleaned.get(field) is not None and fmt not in formats:
                self.cleaned_data[field] = None
                cleaned[field] = None

        audio_length = self.cleaned_data.get("audio_length_input")
        audio_position = self.cleaned_data.get("audio_position_input")
        speed = cleaned.get("audio_playback_speed")
        if BookProgress.FORMAT_AUDIO in formats:
            if not audio_length:
                raise ValidationError("Укажите длительность аудиокниги")
            if audio_position and audio_length and audio_position > audio_length:
                self.add_error("audio_position_input", "Прогресс не может превышать длительность")
            if speed is None:
                cleaned["audio_playback_speed"] = Decimal("1.0")
        else:
            cleaned["audio_playback_speed"] = None
            self.cleaned_data["audio_length_input"] = None
            self.cleaned_data["audio_position_input"] = None
        return cleaned

    def save(self, commit=True):
        formats = self.cleaned_data.get("formats", [])
        progress = super().save(commit=False)
        if formats:
            progress.format = formats[0]
        if BookProgress.FORMAT_AUDIO in formats:
            progress.audio_length = self.cleaned_data.get("audio_length_input")
            progress.audio_position = self.cleaned_data.get("audio_position_input")
            progress.audio_playback_speed = self.cleaned_data.get("audio_playback_speed") or Decimal("1.0")
        else:
            progress.audio_length = None
            progress.audio_position = None
            progress.audio_playback_speed = None
        if commit:
            progress.save()
            self._sync_media(progress, formats)
        else:
            self._pending_formats = formats
        return progress

    def save_m2m(self):  # type: ignore[override]
        progress = self.instance
        formats = getattr(self, "_pending_formats", self.cleaned_data.get("formats", []))
        self._sync_media(progress, formats)

    def _sync_media(self, progress: BookProgress, formats):
        existing = {medium.medium: medium for medium in progress.media.all()}
        to_keep = set(formats)
        for medium_code, medium_obj in list(existing.items()):
            if medium_code not in to_keep:
                medium_obj.delete()
                existing.pop(medium_code, None)

        page_fields = {
            BookProgress.FORMAT_PAPER: "paper_current_page",
            BookProgress.FORMAT_EBOOK: "ebook_current_page",
        }
        override_fields = {
            BookProgress.FORMAT_PAPER: "paper_total_pages",
            BookProgress.FORMAT_EBOOK: "ebook_total_pages",
        }
        for medium_code in formats:
            medium_obj = existing.get(medium_code)
            if not medium_obj:
                medium_obj = BookProgressMedium(progress=progress, medium=medium_code)
            if medium_code in page_fields:
                value = self.cleaned_data.get(page_fields[medium_code])
                medium_obj.current_page = value if value is not None else None
                override_value = self.cleaned_data.get(override_fields.get(medium_code))
                if override_value:
                    medium_obj.total_pages_override = override_value
                else:
                    medium_obj.total_pages_override = progress.custom_total_pages
                medium_obj.audio_position = None
                medium_obj.audio_length = None
                medium_obj.playback_speed = None
            elif medium_code == BookProgress.FORMAT_AUDIO:
                medium_obj.current_page = None
                medium_obj.total_pages_override = None
                medium_obj.audio_length = self.cleaned_data.get("audio_length_input")
                medium_obj.audio_position = self.cleaned_data.get("audio_position_input")
                medium_obj.playback_speed = self.cleaned_data.get("audio_playback_speed") or Decimal("1.0")
            medium_obj.save()

        combined = progress.get_combined_current_pages()
        progress.current_page = (
            int(combined.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if combined is not None
            else None
        )
        progress.save(update_fields=["current_page"])
        progress.recalc_percent()

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