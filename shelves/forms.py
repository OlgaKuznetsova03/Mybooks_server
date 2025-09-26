from django import forms
from .models import (
    Shelf,
    ShelfItem,
    Event,
    EventParticipant,
    BookProgress,
    CharacterNote,
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