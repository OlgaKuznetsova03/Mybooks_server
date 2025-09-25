from django import forms
from .models import Shelf, ShelfItem, Event, EventParticipant, BookProgress

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
        fields = ["character_notes", "reading_notes"]
        labels = {
            "character_notes": "Герои и заметки о них",
            "reading_notes": "Цитаты, впечатления, реакции",
        }
        widgets = {
            "character_notes": forms.Textarea(attrs={
                "rows": 4,
                "class": "form-control",
                "placeholder": "Добавьте список персонажей и краткие описания, кто есть кто...",
            }),
            "reading_notes": forms.Textarea(attrs={
                "rows": 5,
                "class": "form-control",
                "placeholder": "Фиксируйте цитаты, мысли и эмоции по ходу чтения...",
            }),
        }