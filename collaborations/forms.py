from __future__ import annotations

from datetime import date

from typing import List, Sequence, Tuple

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
    CollaborationMessage,
    CollaborationStatusUpdate,
)
from .validators import validate_epub_attachment


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
        current_book = None
        if getattr(self.instance, "pk", None) and self.instance.book_id:
            current_book = Book.objects.filter(pk=self.instance.book_id)
        if current_book is not None:
            queryset = queryset | current_book
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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[
            "blogger_collaboration_platform_other"
        ].widget.attrs.setdefault("placeholder", _("Например: TikTok"))
        self.fields[
            "blogger_collaboration_goal_other"
        ].widget.attrs.setdefault(
            "placeholder", _("Опишите формат совместной активности")
        )

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
            "target_audience",
            "blogger_collaboration_platform",
            "blogger_collaboration_platform_other",
            "blogger_collaboration_goal",
            "blogger_collaboration_goal_other",
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
            "target_audience": forms.Select(attrs={"class": "form-select"}),
            "blogger_collaboration_platform": forms.Select(
                attrs={"class": "form-select"}
            ),
            "blogger_collaboration_goal": forms.Select(attrs={"class": "form-select"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        target_audience = cleaned_data.get("target_audience")
        platform = cleaned_data.get("blogger_collaboration_platform")
        platform_other = cleaned_data.get("blogger_collaboration_platform_other", "").strip()
        goal = cleaned_data.get("blogger_collaboration_goal", "")
        goal_other = cleaned_data.get("blogger_collaboration_goal_other", "").strip()

        if target_audience == BloggerRequest.TargetAudience.BLOGGERS:
            if platform is None and not platform_other:
                self.add_error(
                    "blogger_collaboration_platform",
                    _("Выберите платформу или укажите свою."),
                )
                if not platform_other:
                    self.add_error(
                        "blogger_collaboration_platform_other",
                        _("Укажите площадку, если её нет в списке."),
                    )

            if not goal:
                self.add_error(
                    "blogger_collaboration_goal",
                    _("Выберите цель сотрудничества."),
                )
            elif goal == BloggerRequest.BloggerCollaborationGoal.OTHER and not goal_other:
                self.add_error(
                    "blogger_collaboration_goal_other",
                    _("Опишите формат сотрудничества."),
                )
            cleaned_data["blogger_collaboration_platform_other"] = platform_other
            cleaned_data["blogger_collaboration_goal_other"] = goal_other
        else:
            cleaned_data["blogger_collaboration_platform"] = None
            cleaned_data["blogger_collaboration_platform_other"] = ""
            cleaned_data["blogger_collaboration_goal"] = ""
            cleaned_data["blogger_collaboration_goal_other"] = ""

        return cleaned_data

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
    platform_link = forms.URLField(
        required=False,
        label=_("Ссылка на площадку"),
        help_text=_("Добавьте ссылку на блог или профиль."),
        widget=forms.URLInput(
            attrs={
                "placeholder": "https://t.me/username",
            }
        ),
    )
    message = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": _("Расскажите о себе и предложите формат сотрудничества."),
            }
        ),
        label=_("Сообщение"),
    )
    book = forms.ModelChoiceField(
        queryset=Book.objects.none(),
        required=False,
        label=_("Книга"),
        help_text=_("Выберите книгу, которую готовы предложить."),
        widget=forms.Select(attrs={"data-enhanced-single": "1"}),
    )

    def __init__(self, *args, **kwargs):
        self.responder = kwargs.pop("responder", None)
        self.request_obj: BloggerRequest | None = kwargs.pop("request_obj", None)
        super().__init__(*args, **kwargs)
        
        queryset = Book.objects.none()
        if self.responder is not None:
            queryset = Book.objects.filter(contributors=self.responder)
        if self.instance and self.instance.book_id:
            queryset = queryset | Book.objects.filter(pk=self.instance.book_id)
        self.fields["book"].queryset = queryset.distinct().order_by("title")

        self.show_book_field = False
        self.show_platform_link_field = False
        if self.request_obj is not None:
            if self.request_obj.is_for_authors:
                self.show_book_field = True
                self.fields["book"].required = True
                self.fields["platform_link"].required = False
                self.fields["platform_link"].widget = forms.HiddenInput()
            elif self.request_obj.is_for_bloggers:
                self.show_platform_link_field = True
                self.fields["platform_link"].required = True
                self.fields["book"].required = False
                self.fields["book"].widget = forms.HiddenInput()

    class Meta:
        model = BloggerRequestResponse
        fields = ["message", "book", "platform_link"]

    def clean_message(self):
        message = self.cleaned_data.get("message", "")
        if message:
            return message.strip()
        return ""

    def clean_book(self):
        book = self.cleaned_data.get("book")
        if self.request_obj and self.request_obj.is_for_authors:
            if book is None:
                raise forms.ValidationError(_("Укажите книгу, чтобы блогер мог ознакомиться с ней."))
            if self.responder is not None:
                if not book.contributors.filter(pk=self.responder.pk).exists():
                    raise forms.ValidationError(
                        _("Вы можете предложить только книгу, где указаны как автор."),
                    )
        return book

    def clean_platform_link(self):
        link = self.cleaned_data.get("platform_link", "")
        if self.request_obj and self.request_obj.is_for_bloggers:
            if not link:
                raise forms.ValidationError(_("Добавьте ссылку на ваш блог или профиль."))
        return link.strip()

    def expected_responder_type(self) -> str:
        if self.request_obj and self.request_obj.is_for_bloggers:
            return BloggerRequestResponse.ResponderType.BLOGGER
        return BloggerRequestResponse.ResponderType.AUTHOR


class CollaborationMessageForm(BootstrapModelForm):
    can_upload_epub: bool = False
    epub_file = forms.FileField(
        label=_("EPUB-файл"),
        required=False,
        help_text=_("Прикрепите электронную версию книги в формате .epub."),
        widget=forms.ClearableFileInput(attrs={"accept": ".epub"}),
    )

    def __init__(self, *args, **kwargs):
        self.collaboration = kwargs.pop("collaboration", None)
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        field = self.fields.get("epub_file")
        if field is not None:
            field.required = False
            field.widget.attrs.setdefault("class", "form-control")
        self.can_upload_epub = self._epub_allowed()

    def _epub_allowed(self) -> bool:
        """Return True when the author can attach an EPUB to the chat."""

        if not self.collaboration or not self.user:
            return False

        is_author = getattr(self.user, "id", None) == getattr(
            self.collaboration, "author_id", None
        )
        is_confirmed = (
            self.collaboration.author_approved and self.collaboration.partner_approved
        )

        return is_author and is_confirmed and self.collaboration.allows_discussion()
        
    class Meta:
        model = CollaborationMessage
        fields = ["text", "epub_file"]
        widgets = {
            "text": forms.Textarea(
                attrs={
                    "rows": 3,
                    "maxlength": 2000,
                    "placeholder": _(
                        "Обсудите рабочие моменты, уточните детали доставки или контента."
                    ),
                }
            )
        }
        labels = {"text": _("Сообщение")}

    def clean_epub_file(self):
        upload = self.cleaned_data.get("epub_file")
        if not upload:
            return None
        if not getattr(self, "can_upload_epub", False):
            raise forms.ValidationError(
                _("Прикреплять файлы может только автор после подтверждения сотрудничества."),
            )
        validate_epub_attachment(upload)
        return upload


class CollaborationStatusForm(BootstrapModelForm):
    """Форма для ручного переключения рабочего статуса автором."""

    _manual_statuses = {
        Collaboration.Status.NEGOTIATION,
        Collaboration.Status.ACTIVE,
    }

    class Meta:
        model = Collaboration
        fields = ["status"]
        labels = {"status": _("Статус")}
        widgets = {
            "status": forms.Select(attrs={"class": "form-select form-select-sm"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields.get("status")
        self._allowed_statuses = self._resolve_allowed_statuses()
        if field is not None:
            field.choices = [
                (value, label)
                for value, label in Collaboration.Status.choices
                if value in self._allowed_statuses
            ]

    def _resolve_allowed_statuses(self) -> set[str]:
        allowed = set(self._manual_statuses)
        current = getattr(self.instance, "status", None)
        if current:
            allowed.add(current)
        return allowed

    def clean_status(self):
        status = self.cleaned_data.get("status")
        if status not in self._allowed_statuses:
            raise forms.ValidationError(_("Этот статус нельзя выбрать вручную."))
        return status


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


class CollaborationApprovalForm(forms.Form):
    deadline = forms.DateField(
        label=_("Подтвердить дедлайн"),
        help_text=_("Если нужно, скорректируйте дату сдачи материалов."),
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    def clean_deadline(self):
        deadline = self.cleaned_data["deadline"]
        if deadline < date.today():
            raise forms.ValidationError(_("Дата не может быть в прошлом."))
        return deadline


class CollaborationStatusForm(forms.ModelForm):
    """Форма для смены статуса сотрудничества участниками."""

    status = forms.ChoiceField(
        label=_("Новый статус"),
        required=True,
        choices=(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.allowed_statuses: List[Tuple[str, str]] = self._resolve_allowed_statuses()
        field = self.fields["status"]
        field.choices = self.allowed_statuses
        if self.instance.pk:
            field.initial = self.instance.status
        self.current_status = self.instance.status if self.instance.pk else None
        self.current_status_label = (
            dict(Collaboration.Status.choices).get(self.current_status)
            if self.current_status
            else None
        )

    class Meta:
        model = Collaboration
        fields = ["status"]

    @staticmethod
    def _available_for_author() -> Sequence[str]:
        return (
            Collaboration.Status.NEGOTIATION,
            Collaboration.Status.ACTIVE,
            Collaboration.Status.COMPLETED,
            Collaboration.Status.FAILED,
            Collaboration.Status.CANCELLED,
        )

    @staticmethod
    def _available_for_partner() -> Sequence[str]:
        return (
            Collaboration.Status.NEGOTIATION,
            Collaboration.Status.ACTIVE,
            Collaboration.Status.CANCELLED,
        )

    def _resolve_allowed_statuses(self) -> List[Tuple[str, str]]:
        instance = self.instance
        choices_map = dict(Collaboration.Status.choices)
        if not instance.pk or self.user is None:
            return []
        if not instance.is_participant(self.user):
            return []

        if self.user.id == instance.author_id:
            codes: Sequence[str] = self._available_for_author()
        else:
            codes = self._available_for_partner()

        codes = list(codes)
        if instance.status not in codes:
            codes.insert(0, instance.status)

        if not instance.get_review_links():
            codes = [code for code in codes if code != Collaboration.Status.COMPLETED]

        seen = set()
        allowed: List[Tuple[str, str]] = []
        for code in codes:
            if code in seen:
                continue
            label = choices_map.get(code)
            if label is None:
                continue
            seen.add(code)
            allowed.append((code, label))
        return allowed

    @property
    def has_available_options(self) -> bool:
        return any(code != self.instance.status for code, _ in self.allowed_statuses)

    def clean(self):
        cleaned_data = super().clean()
        if not self.allowed_statuses:
            raise forms.ValidationError(
                _("Вы не можете изменять статус этого сотрудничества."),
            )
        return cleaned_data

    def clean_status(self):
        status = self.cleaned_data["status"]
        if status == Collaboration.Status.COMPLETED and not self.instance.get_review_links():
            raise forms.ValidationError(
                _("Добавьте ссылки на отзывы, прежде чем завершать сотрудничество."),
            )
        return status

    def apply(self) -> CollaborationStatusUpdate | None:
        """Изменяет статус экземпляра и возвращает информацию об обновлении."""

        collaboration = self.instance
        new_status = self.cleaned_data["status"]
        if new_status == Collaboration.Status.COMPLETED:
            return CollaborationStatusUpdate.confirm_completion(
                collaboration, collaboration.get_review_links()
            )
        if new_status == Collaboration.Status.FAILED:
            return CollaborationStatusUpdate.mark_failed(collaboration)

        collaboration.status = new_status
        if new_status != Collaboration.Status.COMPLETED and collaboration.completed_at:
            collaboration.completed_at = None
        collaboration.save(update_fields=["status", "updated_at", "completed_at"])
        return None