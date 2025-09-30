from django import forms

from shelves.models import Shelf

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
        enrolled_ids = ReadBeforeBuyGame.iter_participating_shelves(user).values_list(
            "shelf_id", flat=True
        )
        self.fields["shelf"].queryset = (
            Shelf.objects.filter(user=user)
            .exclude(id__in=enrolled_ids)
            .order_by("-is_default", "name")
        )
        self.fields["shelf"].widget.attrs.setdefault("class", "form-select")