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