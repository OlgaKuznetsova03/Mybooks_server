from __future__ import annotations

from typing import Iterable

from django import forms
from django.utils.translation import gettext_lazy as _
from django.forms.models import ModelChoiceIteratorValue

from books.models import Book
from .models import MarathonEntry, MarathonTheme, ReadingMarathon


class BookSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):  # type: ignore[override]
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)

        book = None
        if isinstance(value, ModelChoiceIteratorValue):
            book = value.instance
        elif isinstance(value, Book):
            book = value

        if book is not None:
            authors = ", ".join(book.authors.values_list("name", flat=True))
            search_value = f"{book.title} {authors}".strip()
            option.setdefault("attrs", {})["data-search"] = search_value

        return option


class ReadingMarathonForm(forms.ModelForm):
    topic_titles = forms.CharField(
        label=_("Темы марафона"),
        widget=forms.Textarea(attrs={"rows": 5}),
        help_text=_("Перечислите до 30 тем, по одной на строку."),
    )

    class Meta:
        model = ReadingMarathon
        fields = [
            "title",
            "description",
            "cover",
            "start_date",
            "end_date",
            "join_policy",
            "book_submission_policy",
            "completion_policy",
            "topic_titles",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css_class = "form-control"
            if isinstance(field.widget, forms.Select):
                css_class = "form-select"
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {css_class}".strip()

    def clean_topic_titles(self) -> list[str]:
        raw_value = self.cleaned_data.get("topic_titles", "")
        lines: Iterable[str] = (line.strip() for line in raw_value.splitlines())
        topics = [line for line in lines if line]
        if not topics:
            raise forms.ValidationError(_("Добавьте хотя бы одну тему."))
        if len(topics) > 30:
            raise forms.ValidationError(_("Можно указать не более 30 тем."))
        return topics

    def save(self, commit: bool = True):  # type: ignore[override]
        topics = self.cleaned_data.pop("topic_titles", [])
        marathon: ReadingMarathon = super().save(commit=commit)
        if commit:
            marathon.themes.all().delete()
            for order, title in enumerate(topics, start=1):
                MarathonTheme.objects.create(
                    marathon=marathon,
                    title=title,
                    order=order,
                )
        else:
            self._pending_topics = topics  # pragma: no cover - safety for partial saves
        return marathon


class MarathonEntryForm(forms.ModelForm):
    book = forms.ModelChoiceField(queryset=Book.objects.none(), widget=BookSelect())

    class Meta:
        model = MarathonEntry
        fields = [
            "theme",
            "book",
            "status",
            "progress",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop("user", None)
        marathon = kwargs.pop("marathon")
        super().__init__(*args, **kwargs)
        self.fields["theme"].queryset = marathon.themes.all()
        self.fields["book"].queryset = Book.objects.prefetch_related("authors").order_by("title")
        if marathon.book_submission_policy == ReadingMarathon.BookSubmissionPolicy.APPROVAL:
            self.fields["status"].help_text = _(
                "Книга появится в полке после подтверждения создателя марафона."
            )
        for name, field in self.fields.items():
            css_class = "form-control"
            if isinstance(field.widget, forms.Select):
                css_class = "form-select"
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {css_class}".strip()
            if name in {"progress"}:
                field.widget.attrs.setdefault("min", 0)
                field.widget.attrs.setdefault("max", 100)

    def clean_progress(self):
        progress = self.cleaned_data.get("progress") or 0
        if not 0 <= progress <= 100:
            raise forms.ValidationError(_("Прогресс должен быть в пределах от 0 до 100."))
        return progress


class MarathonEntryStatusForm(forms.ModelForm):
    class Meta:
        model = MarathonEntry
        fields = ["status", "progress", "notes"]

    def clean_progress(self):
        progress = self.cleaned_data.get("progress") or 0
        if not 0 <= progress <= 100:
            raise forms.ValidationError(_("Прогресс должен быть в пределах от 0 до 100."))
        return progress

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css_class = "form-control"
            if isinstance(field.widget, forms.Select):
                css_class = "form-select"
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {css_class}".strip()
            if name in {"progress"}:
                field.widget.attrs.setdefault("min", 0)
                field.widget.attrs.setdefault("max", 100)