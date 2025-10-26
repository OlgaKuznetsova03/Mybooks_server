from __future__ import annotations

from django import forms

from .models import DiscussionPost, ReadingClub, ReadingNorm


class ReadingClubForm(forms.ModelForm):
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    class Meta:
        model = ReadingClub
        fields = [
            "title",
            "book",
            "description",
            "start_date",
            "end_date",
            "join_policy",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_form_control_styles()

    def _apply_form_control_styles(self) -> None:
        for name, field in self.fields.items():
            widget = field.widget
            classes = widget.attrs.get("class", "").split()
            if isinstance(widget, forms.Select):
                base_class = "form-select"
            elif isinstance(widget, forms.CheckboxInput):
                base_class = "form-check-input"
            else:
                base_class = "form-control"
            if base_class not in classes:
                classes.append(base_class)
            if "form-control" not in classes and base_class != "form-control" and isinstance(widget, forms.Textarea):
                classes.append("form-control")
            widget.attrs["class"] = " ".join(filter(None, classes))

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "Дата окончания не может быть раньше даты начала.")
        return cleaned_data


class ReadingNormForm(forms.ModelForm):
    discussion_opens_at = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    class Meta:
        model = ReadingNorm
        fields = ["title", "description", "order", "discussion_opens_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            classes = widget.attrs.get("class", "").split()
            if isinstance(widget, forms.Select):
                base_class = "form-select"
            elif isinstance(widget, forms.CheckboxInput):
                base_class = "form-check-input"
            else:
                base_class = "form-control"
            if base_class not in classes:
                classes.append(base_class)
            if "form-control" not in classes and base_class != "form-control" and isinstance(widget, forms.Textarea):
                classes.append("form-control")
            widget.attrs["class"] = " ".join(filter(None, classes))

            
class DiscussionPostForm(forms.ModelForm):
    class Meta:
        model = DiscussionPost
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(attrs={"rows": 5, "placeholder": "Поделитесь мыслями..."}),
        }
        labels = {
            "content": "Сообщение",
        }