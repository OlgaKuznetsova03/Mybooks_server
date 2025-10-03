from __future__ import annotations

from django import forms
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from .models import (
    AuthorOffer,
    AuthorOfferResponse,
    BloggerPlatformPresence,
    BloggerRequest,
    BloggerRequestResponse,
    Collaboration,
)


class BootstrapModelForm(forms.ModelForm):
    """Простая примесь для добавления bootstrap-классов."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", "form-control")
            elif isinstance(widget, forms.SelectMultiple):
                widget.attrs.setdefault("class", "form-select")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")


class AuthorOfferForm(BootstrapModelForm):
    class Meta:
        model = AuthorOffer
        fields = [
            "title",
            "offered_format",
            "synopsis",
            "review_requirements",
            "text_review_length",
            "expected_platforms",
            "video_review_type",
            "video_requires_unboxing",
            "video_requires_aesthetics",
            "video_requires_review",
            "considers_paid_collaboration",
            "allow_regular_users",
            "is_active",
        ]
        widgets = {
            "review_requirements": forms.Textarea(attrs={"rows": 4}),
            "synopsis": forms.Textarea(attrs={"rows": 3}),
            "expected_platforms": forms.SelectMultiple(attrs={"data-enhanced-multi": "1"}),
        }


class BloggerRequestForm(BootstrapModelForm):
    class Meta:
        model = BloggerRequest
        fields = [
            "title",
            "preferred_genres",
            "accepts_paper",
            "accepts_electronic",
            "accepts_audio",
            "review_formats",
            "additional_info",
            "open_for_paid_collaboration",
            "is_active",
        ]
        widgets = {
            "preferred_genres": forms.SelectMultiple(attrs={"data-enhanced-multi": "1"}),
            "review_formats": forms.SelectMultiple(attrs={"data-enhanced-multi": "1"}),
            "additional_info": forms.Textarea(attrs={"rows": 4}),
        }


class AuthorOfferResponseForm(BootstrapModelForm):
    class Meta:
        model = AuthorOfferResponse
        fields = ["message"]
        widgets = {"message": forms.Textarea(attrs={"rows": 4})}


class BloggerRequestResponseForm(BootstrapModelForm):
    class Meta:
        model = BloggerRequestResponse
        fields = ["message"]
        widgets = {"message": forms.Textarea(attrs={"rows": 4})}


class CollaborationReviewForm(BootstrapModelForm):
    review_links = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        required=True,
        help_text=_("Вставьте каждую ссылку на новой строке."),
        label=_("Ссылки на отзывы"),
    )

    class Meta:
        model = Collaboration
        fields = ["review_links"]

    def clean_review_links(self):
        raw = self.cleaned_data["review_links"]
        links = [link.strip() for link in raw.splitlines() if link.strip()]
        if not links:
            raise forms.ValidationError(_("Добавьте хотя бы одну ссылку."))
        return "\n".join(links)


class BloggerPlatformPresenceForm(BootstrapModelForm):
    class Meta:
        model = BloggerPlatformPresence
        fields = ("platform", "custom_platform_name", "followers_count")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["custom_platform_name"].widget.attrs.setdefault(
            "placeholder", _("Например: TikTok")
        )
        self.fields["followers_count"].widget.attrs.setdefault("min", "0")


BloggerPlatformPresenceFormSet = inlineformset_factory(
    BloggerRequest,
    BloggerPlatformPresence,
    form=BloggerPlatformPresenceForm,
    extra=1,
    can_delete=True,
)