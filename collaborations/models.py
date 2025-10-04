from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

from django.contrib.auth import get_user_model
from django.core.validators import MaxLengthValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from books.models import Book

User = get_user_model()


class ReviewPlatform(models.Model):
    """Платформа, на которой ожидается отзыв."""

    name = models.CharField(max_length=150, unique=True, verbose_name=_("Название"))
    url = models.URLField(
        blank=True,
        verbose_name=_("Ссылка"),
        help_text=_("При наличии — ссылка на платформу или профиль."),
    )

    class Meta:
        ordering = ("name",)
        verbose_name = _("Платформа для отзывов")
        verbose_name_plural = _("Платформы для отзывов")

    def __str__(self) -> str:
        return self.name


class AuthorOffer(models.Model):
    """Предложение автора (или издательства) о сотрудничестве."""

    class BookFormat(models.TextChoices):
        ELECTRONIC = "electronic", _("Электронная")
        PAPER = "paper", _("Бумажная")
        AUDIO = "audio", _("Аудио")

    class VideoReviewType(models.TextChoices):
        NONE = "none", _("Не требуются")
        SINGLE = "single", _("Одно видео")
        SERIES = "series", _("Серия видео")

    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="author_offers",
        verbose_name=_("Автор"),
    )
    title = models.CharField(
        max_length=255,
        verbose_name=_("Книга или проект"),
        help_text=_("Название книги, цикла или проекта, который предлагается."),
    )
    offered_format = models.CharField(
        max_length=20,
        choices=BookFormat.choices,
        default=BookFormat.ELECTRONIC,
        verbose_name=_("Предлагаемый формат"),
    )
    synopsis = models.TextField(
        blank=True,
        verbose_name=_("Кратко о книге"),
        help_text=_("Краткое описание, чтобы блогеры могли понять тематику."),
    )
    review_requirements = models.TextField(
        verbose_name=_("Требования к отзыву"),
        help_text=_("Опишите ожидания по содержанию, срокам и оформлению."),
    )
    text_review_length = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Желаемый объем текста"),
        help_text=_("Количество слов или знаков. Укажите 0, если нет ограничений."),
    )
    expected_platforms = models.ManyToManyField(
        ReviewPlatform,
        blank=True,
        related_name="offers",
        verbose_name=_("Целевые площадки"),
    )
    video_review_type = models.CharField(
        max_length=20,
        choices=VideoReviewType.choices,
        default=VideoReviewType.NONE,
        verbose_name=_("Формат видеоотзыва"),
    )
    book = models.ForeignKey(
        Book,
        on_delete=models.SET_NULL,
        related_name="author_offers",
        null=True,
        blank=True,
        verbose_name=_("Книга на сайте"),
        help_text=_(
            "При желании привяжите предложение к книге, которая уже добавлена на сайт."
        ),
    )
    video_requires_unboxing = models.BooleanField(
        default=False,
        verbose_name=_("Нужна распаковка"),
    )
    video_requires_aesthetics = models.BooleanField(
        default=False,
        verbose_name=_("Нужна эстетика/атмосфера"),
    )
    video_requires_review = models.BooleanField(
        default=True,
        verbose_name=_("Нужен полноценный отзыв"),
    )
    considers_paid_collaboration = models.BooleanField(
        default=False,
        verbose_name=_("Рассматриваю платное сотрудничество"),
    )
    allow_regular_users = models.BooleanField(
        default=False,
        verbose_name=_("Открыт для обычных читателей"),
        help_text=_("Если включено, отзыв могут оставить не только блогеры."),
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Активно"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Предложение автора")
        verbose_name_plural = _("Предложения авторов")

    def __str__(self) -> str:
        return f"{self.title} — {self.get_offered_format_display()}"

    @property
    def paid_collaboration_disclaimer(self) -> str:
        if not self.considers_paid_collaboration:
            return ""
        return _(
            "Все договорённости по платным интеграциям или сотрудничеству заключаются исключительно между автором и заказчиком. Платформа не является стороной сделки, не осуществляет контроль над условиями и не несёт какой-либо ответственности за последствия договорённостей."
        )

    def get_attached_book_cover_url(self) -> str:
        if self.book is None:
            return ""
        return self.book.get_cover_url()
    

class BloggerRequest(models.Model):
    """Заявка блогера на поиск авторов."""

    blogger = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="blogger_requests",
        verbose_name=_("Блогер"),
    )
    title = models.CharField(
        max_length=255,
        verbose_name=_("Название заявки"),
        help_text=_("Например: 'Ищу фэнтези-новинки'"),
    )
    preferred_genres = models.ManyToManyField(
        "books.Genre",
        blank=True,
        related_name="blogger_requests",
        verbose_name=_("Предпочитаемые жанры"),
    )
    accepts_paper = models.BooleanField(default=True, verbose_name=_("Беру бумажные издания"))
    accepts_electronic = models.BooleanField(default=True, verbose_name=_("Беру электронные издания"))
    accepts_audio = models.BooleanField(default=False, verbose_name=_("Беру аудиокниги"))
    review_formats = models.ManyToManyField(
        ReviewPlatform,
        blank=True,
        related_name="blogger_requests",
        verbose_name=_("Где публикую отзывы"),
    )
    additional_info = models.TextField(
        blank=True,
        verbose_name=_("Дополнительные детали"),
        help_text=_("Расскажите о предпочитаемом формате контента и условиях."),
    )
    open_for_paid_collaboration = models.BooleanField(
        default=False,
        verbose_name=_("Готов к платному сотрудничеству"),
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Активна"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Заявка блогера")
        verbose_name_plural = _("Заявки блогеров")

    def __str__(self) -> str:
        return self.title

    def get_format_display_list(self) -> list[str]:
        formats: list[str] = []
        if self.accepts_paper:
            formats.append(str(AuthorOffer.BookFormat.PAPER.label))
        if self.accepts_electronic:
            formats.append(str(AuthorOffer.BookFormat.ELECTRONIC.label))
        if self.accepts_audio:
            formats.append(str(AuthorOffer.BookFormat.AUDIO.label))
        return formats


class BloggerPlatformPresence(models.Model):
    """Информация о платформе блогера и его аудитории."""

    request = models.ForeignKey(
        BloggerRequest,
        on_delete=models.CASCADE,
        related_name="platforms",
    )
    platform = models.ForeignKey(
        ReviewPlatform,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_presences",
    )
    custom_platform_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name=_("Название платформы"),
        help_text=_("Если площадки нет в общем списке, укажите её здесь."),
    )
    followers_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Количество подписчиков"),
    )

    class Meta:
        verbose_name = _("Площадка блогера")
        verbose_name_plural = _("Площадки блогеров")

    def __str__(self) -> str:
        if self.platform:
            return f"{self.platform.name}: {self.followers_count}"
        return f"{self.custom_platform_name or _('Площадка')}: {self.followers_count}"

    @property
    def display_name(self) -> str:
        if self.platform:
            return self.platform.name
        return self.custom_platform_name


class AuthorOfferResponse(models.Model):
    """Отклик блогера или читателя на предложение автора."""

    class Status(models.TextChoices):
        PENDING = "pending", _("На рассмотрении")
        ACCEPTED = "accepted", _("Принято")
        DECLINED = "declined", _("Отклонено")
        WITHDRAWN = "withdrawn", _("Отозвано")

    offer = models.ForeignKey(
        AuthorOffer,
        on_delete=models.CASCADE,
        related_name="responses",
    )
    respondent = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="offer_responses",
    )
    platform_links = models.TextField(
        blank=True,
        verbose_name=_("Площадки для отзывов"),
        help_text=_("Укажите ссылки на площадки построчно."),
    )
    message = models.TextField(
        blank=True,
        verbose_name=_("Сообщение"),
        validators=[MaxLengthValidator(4000)],
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name=_("Статус"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("offer", "respondent")
        ordering = ("-created_at",)
        verbose_name = _("Отклик на предложение автора")
        verbose_name_plural = _("Отклики на предложения авторов")

    def __str__(self) -> str:
        return f"{self.respondent} → {self.offer} ({self.get_status_display()})"


class BloggerRequestResponse(models.Model):
    """Отклик автора на заявку блогера."""

    class Status(models.TextChoices):
        PENDING = "pending", _("На рассмотрении")
        ACCEPTED = "accepted", _("Принято")
        DECLINED = "declined", _("Отклонено")
        WITHDRAWN = "withdrawn", _("Отозвано")

    request = models.ForeignKey(
        BloggerRequest,
        on_delete=models.CASCADE,
        related_name="responses",
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="blogger_request_responses",
    )
    message = models.TextField(blank=True, verbose_name=_("Сообщение"))
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name=_("Статус"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("request", "author")
        ordering = ("-created_at",)
        verbose_name = _("Отклик автора на заявку блогера")
        verbose_name_plural = _("Отклики авторов на заявки блогеров")

    def __str__(self) -> str:
        return f"{self.author} → {self.request} ({self.get_status_display()})"


class Collaboration(models.Model):
    """Фактическое сотрудничество между автором и блогером/читателем."""

    class Status(models.TextChoices):
        NEGOTIATION = "negotiation", _("Переговоры")
        ACTIVE = "active", _("В работе")
        COMPLETED = "completed", _("Завершено")
        FAILED = "failed", _("Просрочено")
        CANCELLED = "cancelled", _("Отменено")

    offer = models.ForeignKey(
        AuthorOffer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="collaborations",
    )
    request = models.ForeignKey(
        BloggerRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="collaborations",
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="collaborations_as_author",
    )
    partner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="collaborations_as_partner",
        help_text=_("Блогер или пользователь, который выполняет условия."),
    )
    deadline = models.DateField(verbose_name=_("Дедлайн публикации"))
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEGOTIATION,
    )
    review_links = models.TextField(
        blank=True,
        verbose_name=_("Ссылки на опубликованные отзывы"),
        help_text=_("Укажите ссылки построчно после выполнения условий."),
    )
    author_confirmed = models.BooleanField(default=False, verbose_name=_("Автор подтвердил"))
    partner_confirmed = models.BooleanField(default=False, verbose_name=_("Блогер подтвердил"))
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Сотрудничество")
        verbose_name_plural = _("Сотрудничества")

    def __str__(self) -> str:
        return f"{self.author} ↔ {self.partner} ({self.get_status_display()})"

    def get_review_links(self) -> list[str]:
        return [link.strip() for link in self.review_links.splitlines() if link.strip()]

    def can_be_completed(self) -> bool:
        return self.author_confirmed and self.partner_confirmed and bool(self.review_links)

    def mark_completed(self, links: Iterable[str] | None = None) -> None:
        if links:
            self.review_links = "\n".join(link.strip() for link in links if link.strip())
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.updated_at = timezone.now()
        self.save(update_fields=["review_links", "status", "completed_at", "updated_at"])

    def mark_failed(self) -> None:
        self.status = self.Status.FAILED
        self.updated_at = timezone.now()
        self.save(update_fields=["status", "updated_at"])

    @property
    def needs_attention(self) -> bool:
        today = date.today()
        return self.status == self.Status.ACTIVE and self.deadline < today

    def needs_attention_at(self, today: Optional[date] = None) -> bool:
        today = today or date.today()
        return self.status == self.Status.ACTIVE and self.deadline < today

    @property
    def partner_rating(self) -> Optional[int]:
        try:
            rating = self.partner.blogger_rating
        except BloggerRating.DoesNotExist:  # type: ignore[attr-defined]
            return None
        return rating.score


class BloggerRating(models.Model):
    """Рейтинг блогеров на основе выполненных сотрудничеств."""

    blogger = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="blogger_rating",
    )
    score = models.IntegerField(default=100)
    successful_collaborations = models.PositiveIntegerField(default=0)
    failed_collaborations = models.PositiveIntegerField(default=0)
    total_collaborations = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = _("Рейтинг блогера")
        verbose_name_plural = _("Рейтинги блогеров")

    def __str__(self) -> str:
        return f"{self.blogger} — {self.score}"

    def record_completion(self, success: bool) -> None:
        self.total_collaborations = models.F("total_collaborations") + 1
        update_fields = ["total_collaborations", "score"]
        if success:
            self.successful_collaborations = models.F("successful_collaborations") + 1
            self.score = models.F("score") + 5
            update_fields.append("successful_collaborations")
        else:
            self.failed_collaborations = models.F("failed_collaborations") + 1
            self.score = models.F("score") - 10
            update_fields.append("failed_collaborations")
        self.save(update_fields=update_fields)
        self.refresh_from_db()


@dataclass
class CollaborationStatusUpdate:
    collaboration: Collaboration
    rating_change: Optional[int] = None

    @staticmethod
    def _ensure_blogger_rating(user: User) -> Optional[BloggerRating]:  # type: ignore[name-defined]
        if not user.groups.filter(name="blogger").exists():
            return None
        rating, _ = BloggerRating.objects.get_or_create(blogger=user)
        return rating

    @classmethod
    def confirm_completion(
        cls,
        collaboration: Collaboration,
        review_links: Iterable[str],
    ) -> "CollaborationStatusUpdate":
        cleaned_links = [link.strip() for link in review_links if link.strip()]
        collaboration.review_links = "\n".join(cleaned_links)
        collaboration.status = Collaboration.Status.COMPLETED
        collaboration.completed_at = timezone.now()
        collaboration.updated_at = timezone.now()
        collaboration.save(update_fields=["review_links", "status", "completed_at", "updated_at"])

        rating_change: Optional[int] = None
        blogger_rating = cls._ensure_blogger_rating(collaboration.partner)
        if blogger_rating:
            before = blogger_rating.score
            blogger_rating.record_completion(success=True)
            rating_change = blogger_rating.score - before
        return cls(collaboration=collaboration, rating_change=rating_change)

    @classmethod
    def mark_failed(cls, collaboration: Collaboration) -> "CollaborationStatusUpdate":
        collaboration.status = Collaboration.Status.FAILED
        collaboration.updated_at = timezone.now()
        collaboration.save(update_fields=["status", "updated_at"])

        rating_change: Optional[int] = None
        blogger_rating = cls._ensure_blogger_rating(collaboration.partner)
        if blogger_rating:
            before = blogger_rating.score
            blogger_rating.record_completion(success=False)
            rating_change = blogger_rating.score - before
        return cls(collaboration=collaboration, rating_change=rating_change)