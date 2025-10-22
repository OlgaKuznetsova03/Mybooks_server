from __future__ import annotations

from datetime import date

from django import forms
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from books.models import Book

from .models import (
    AuthorOffer,
    AuthorOfferResponse,
    AuthorOfferResponseComment,
    BloggerGiveaway,
    BloggerInvitation,
    CommunityBookClub,
    BloggerPlatformPresence,
    BloggerRequest,
    BloggerRequestResponse,
    BloggerRequestResponseComment,
    Collaboration,
)


class BootstrapModelForm(forms.ModelForm):
    """Простая примесь для добавления bootstrap-классов."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
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
            if self.is_bound and name in self.errors:
                widget.attrs["class"] = f"{widget.attrs.get('class', '').strip()} is-invalid".strip()


class AuthorOfferForm(BootstrapModelForm):
    def __init__(self, *args, **kwargs):
        author = kwargs.pop("author", None)
        super().__init__(*args, **kwargs)
        book_field = self.fields.get("book")
        if book_field is None:
            return

        queryset = Book.objects.none()
        if author is not None and getattr(author, "is_authenticated", False):
            queryset = Book.objects.filter(contributors=author)
        book_field.queryset = queryset.order_by("title").distinct()
        
    class Meta:
        model = AuthorOffer
        fields = [
            "title",
            "book",
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
            "book": forms.Select(attrs={"class": "form-select", "data-enhanced-single": "1"}),
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
            "review_platform_links",
            "additional_info",
            "collaboration_type",
            "collaboration_terms",
            "is_active",
        ]
        widgets = {
            "preferred_genres": forms.SelectMultiple(attrs={"data-enhanced-multi": "1"}),
            "review_formats": forms.SelectMultiple(attrs={"data-enhanced-multi": "1"}),
            "additional_info": forms.Textarea(attrs={"rows": 4}),
            "collaboration_terms": forms.Textarea(attrs={"rows": 3}),
            "review_platform_links": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": _("https://t.me/username"),
                }
            ),
            "collaboration_type": forms.Select(attrs={"class": "form-select"}),
        }

    def clean_review_platform_links(self):
        raw = self.cleaned_data.get("review_platform_links", "")
        if not raw:
            return ""
        links = [link.strip() for link in raw.splitlines() if link.strip()]
        return "\n".join(links)
    

class AuthorOfferResponseForm(BootstrapModelForm):
    platform_links = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": _("Например: https://instagram.com/username"),
            }
        ),
        label=_("Где опубликуете отзыв"),
        help_text=_("Укажите ссылки на площадки построчно."),
    )
    message = forms.CharField(
        required=False,
        max_length=4000,
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "placeholder": _("Расскажите автору о себе и формате сотрудничества."),
                "maxlength": 4000,
            }
        ),
        label=_("Сообщение"),
        help_text=_("Можно добавить детали сотрудничества или вопросы."),
    )

    class Meta:
        model = AuthorOfferResponse
        fields = ["platform_links", "message"]

    def _label_with_class(self, field_name: str, css_class: str = "form-label"):
        """Возвращает label_tag с указанным CSS-классом."""

        bound_field = self[field_name]
        return bound_field.label_tag(attrs={"class": css_class})

    @property
    def platform_links_label_tag(self):
        return self._label_with_class("platform_links")

    @property
    def message_label_tag(self):
        return self._label_with_class("message")
    
    def clean_platform_links(self):
        raw_links = self.cleaned_data.get("platform_links", "")
        if not raw_links:
            return ""
        links = [link.strip() for link in raw_links.splitlines() if link.strip()]
        return "\n".join(links)


class AuthorOfferResponseCommentForm(BootstrapModelForm):
    class Meta:
        model = AuthorOfferResponseComment
        fields = ["text"]
        widgets = {
            "text": forms.Textarea(
                attrs={
                    "rows": 3,
                    "maxlength": 1000,
                    "placeholder": _(
                        "Задайте уточняющий вопрос или уточните детали сотрудничества."
                    ),
                }
            )
        }
        labels = {"text": _("Комментарий")}


class BloggerRequestResponseForm(BootstrapModelForm):
    book = forms.ModelChoiceField(
        required=False,
        queryset=Book.objects.none(),
        label=_("Книга"),
        help_text=_("Прикрепите книгу, чтобы блогер мог быстро её изучить."),
        widget=forms.Select(attrs={"data-enhanced-single": "1"}),
    )

    def __init__(self, *args, **kwargs):
        self.author = kwargs.pop("author", None)
        super().__init__(*args, **kwargs)
        queryset = Book.objects.all()
        if self.author is not None:
            user_books = getattr(self.author, "books", None)
            if hasattr(user_books, "all"):
                queryset = user_books.all()
        self.fields["book"].queryset = queryset.order_by("title")

    class Meta:
        model = BloggerRequestResponse
        fields = ["message", "book"]
        widgets = {"message": forms.Textarea(attrs={"rows": 4})}


class BloggerInvitationForm(BootstrapModelForm):
    class Meta:
        model = BloggerInvitation
        fields = ["platform", "title", "link", "description"]
        widgets = {
            "platform": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(
                attrs={
                    "placeholder": _("Например: Подпишитесь на обзоры новинок каждую неделю"),
                }
            ),
            "link": forms.URLInput(
                attrs={
                    "placeholder": "https://t.me/username",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": _("Поделитесь уникальностью вашего канала."),
                }
            ),
        }


class BloggerGiveawayForm(BootstrapModelForm):
    class Meta:
        model = BloggerGiveaway
        fields = ["title", "link", "description", "deadline", "is_active"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "placeholder": _("Например: Розыгрыш набора фэнтези-новинок"),
                }
            ),
            "link": forms.URLInput(
                attrs={"placeholder": "https://vk.com/wall..."}),
            "description": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": _("Опишите условия участия и сроки."),
                }
            ),
            "deadline": forms.DateInput(attrs={"type": "date"}),
        }


class CommunityBookClubForm(BootstrapModelForm):
    class Meta:
        model = CommunityBookClub
        fields = [
            "title",
            "city",
            "meeting_format",
            "meeting_schedule",
            "link",
            "description",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "placeholder": _("Например: Литературный вечер по средам"),
                }
            ),
            "city": forms.TextInput(
                attrs={
                    "placeholder": _("Москва, Минск, Онлайн"),
                }
            ),
            "meeting_schedule": forms.TextInput(
                attrs={
                    "placeholder": _("Каждый второй четверг"),
                }
            ),
            "link": forms.URLInput(
                attrs={
                    "placeholder": "https://t.me/club_link",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": _("Расскажите о формате, книгах и участниках."),
                }
            ),
        }


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


class BloggerRequestResponseCommentForm(BootstrapModelForm):
    class Meta:
        model = BloggerRequestResponseComment
        fields = ["text"]
        widgets = {
            "text": forms.Textarea(
                attrs={
                    "rows": 3,
                    "maxlength": 1000,
                    "placeholder": _("Уточните детали сотрудничества."),
                }
            )
        }
        labels = {"text": _("Комментарий")}


class BloggerRequestResponseAcceptForm(forms.Form):
    deadline = forms.DateField(
        label=_("Предоставить ссылки до"),
        help_text=_("Выберите дату, к которой автор должен выслать ссылки."),
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    def clean_deadline(self):
        deadline = self.cleaned_data["deadline"]
        if deadline < date.today():
            raise forms.ValidationError(_("Дата не может быть в прошлом."))
        return deadline

BloggerPlatformPresenceFormSet = inlineformset_factory(
    BloggerRequest,
    BloggerPlatformPresence,
    form=BloggerPlatformPresenceForm,
    extra=1,
    can_delete=True,
)


class AuthorOfferResponseAcceptForm(forms.Form):
    deadline = forms.DateField(
        label=_("Сдать отзыв до"),
        help_text=_("Выберите дату, к которой партнёр должен прислать ссылки на отзывы."),
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    def clean_deadline(self):
        deadline = self.cleaned_data["deadline"]
        if deadline < date.today():
            raise forms.ValidationError(_("Дата не может быть в прошлом."))
        return deadline