from django import forms

from shelves.models import Shelf
from shelves.services import get_home_library_shelf

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

        # self.fields["shelf"].widget.attrs.setdefault("class", "form-select")