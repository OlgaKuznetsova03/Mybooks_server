from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from books.models import Book, Rating

User = settings.AUTH_USER_MODEL


class ReadingMarathonQuerySet(models.QuerySet):
    def active(self) -> "ReadingMarathonQuerySet":
        today = timezone.localdate()
        return self.filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=today)
        )

    def upcoming(self) -> "ReadingMarathonQuerySet":
        today = timezone.localdate()
        return self.filter(start_date__gt=today)

    def past(self) -> "ReadingMarathonQuerySet":
        today = timezone.localdate()
        return self.filter(end_date__lt=today)


class ReadingMarathon(models.Model):
    class JoinPolicy(models.TextChoices):
        OPEN = "open", _("Свободное участие")
        REQUEST = "request", _("По запросу")

    class BookSubmissionPolicy(models.TextChoices):
        AUTO = "auto", _("Участники добавляют книги без подтверждения")
        APPROVAL = "approval", _("Требуется подтверждение создателя")

    class CompletionPolicy(models.TextChoices):
        AUTO = "auto", _("Этап засчитывается автоматически")
        APPROVAL = "approval", _("Создатель подтверждает выполнение этапа")

    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_reading_marathons",
        verbose_name=_("Создатель"),
    )
    title = models.CharField(max_length=255, verbose_name=_("Название"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))
    cover = models.ImageField(
        upload_to="marathons/covers/",
        blank=True,
        null=True,
        verbose_name=_("Обложка"),
    )
    start_date = models.DateField(verbose_name=_("Дата начала"))
    end_date = models.DateField(blank=True, null=True, verbose_name=_("Дата окончания"))
    join_policy = models.CharField(
        max_length=20,
        choices=JoinPolicy.choices,
        default=JoinPolicy.OPEN,
        verbose_name=_("Вступление"),
    )
    book_submission_policy = models.CharField(
        max_length=20,
        choices=BookSubmissionPolicy.choices,
        default=BookSubmissionPolicy.AUTO,
        verbose_name=_("Добавление книг"),
    )
    completion_policy = models.CharField(
        max_length=20,
        choices=CompletionPolicy.choices,
        default=CompletionPolicy.AUTO,
        verbose_name=_("Зачёт этапа"),
    )
    slug = models.SlugField(max_length=255, unique=True, verbose_name=_("URL"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создано"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлено"))

    objects = ReadingMarathonQuerySet.as_manager()

    class Meta:
        ordering = ("-start_date", "-created_at")
        verbose_name = _("Книжный марафон")
        verbose_name_plural = _("Книжные марафоны")

    def __str__(self) -> str:  # pragma: no cover - simple display
        return self.title

    def clean(self) -> None:
        super().clean()
        if self.pk and self.themes.count() > 30:
            raise ValidationError({"themes": _("В марафоне может быть не больше 30 тем.")})

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            base_slug = slugify(self.title) or "marathon"
            slug = base_slug
            suffix = 1
            while ReadingMarathon.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                suffix += 1
                slug = f"{base_slug}-{suffix}"
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("reading_marathons:detail", kwargs={"slug": self.slug})

    @property
    def status(self) -> str:
        today = timezone.localdate()
        if self.start_date > today:
            return "upcoming"
        if self.end_date and self.end_date < today:
            return "past"
        return "active"


class MarathonTheme(models.Model):
    marathon = models.ForeignKey(
        ReadingMarathon,
        on_delete=models.CASCADE,
        related_name="themes",
        verbose_name=_("Марафон"),
    )
    title = models.CharField(max_length=255, verbose_name=_("Название темы"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))
    order = models.PositiveIntegerField(default=1, verbose_name=_("Порядок"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создано"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлено"))

    class Meta:
        ordering = ("order", "id")
        verbose_name = _("Тема марафона")
        verbose_name_plural = _("Темы марафона")

    def __str__(self) -> str:  # pragma: no cover - simple display
        return self.title


class MarathonParticipant(models.Model):
    class Status(models.TextChoices):
        APPROVED = "approved", _("Участник")
        PENDING = "pending", _("Ожидает подтверждения")

    marathon = models.ForeignKey(
        ReadingMarathon,
        on_delete=models.CASCADE,
        related_name="participants",
        verbose_name=_("Марафон"),
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="marathon_participations",
        verbose_name=_("Пользователь"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.APPROVED,
        verbose_name=_("Статус"),
    )
    joined_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Присоединился"))

    class Meta:
        unique_together = ("marathon", "user")
        verbose_name = _("Участник марафона")
        verbose_name_plural = _("Участники марафона")

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.user} — {self.marathon}"

    @property
    def is_approved(self) -> bool:
        return self.status == self.Status.APPROVED


class MarathonEntry(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", _("Запланирована")
        READING = "reading", _("Читаю")
        COMPLETED = "completed", _("Прочитано")

    class CompletionStatus(models.TextChoices):
        IN_PROGRESS = "in_progress", _("В процессе")
        AWAITING_REVIEW = "awaiting_review", _("Ожидает проверки")
        CONFIRMED = "confirmed", _("Подтверждено")

    participant = models.ForeignKey(
        MarathonParticipant,
        on_delete=models.CASCADE,
        related_name="entries",
        verbose_name=_("Участник"),
    )
    theme = models.ForeignKey(
        MarathonTheme,
        on_delete=models.CASCADE,
        related_name="entries",
        verbose_name=_("Тема"),
    )
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name="marathon_entries",
        verbose_name=_("Книга"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PLANNED,
        verbose_name=_("Статус чтения"),
    )
    progress = models.PositiveIntegerField(default=0, verbose_name=_("Прогресс"))
    book_approved = models.BooleanField(default=True, verbose_name=_("Книга подтверждена"))
    completion_status = models.CharField(
        max_length=20,
        choices=CompletionStatus.choices,
        default=CompletionStatus.IN_PROGRESS,
        verbose_name=_("Завершение"),
    )
    notes = models.TextField(blank=True, verbose_name=_("Заметки участника"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Добавлено"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлено"))

    class Meta:
        ordering = ("theme", "-created_at")
        verbose_name = _("Книга в марафоне")
        verbose_name_plural = _("Книги в марафоне")
        unique_together = ("participant", "theme", "book")

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.book} — {self.participant}"

    def clean(self) -> None:
        super().clean()
        if not 0 <= self.progress <= 100:
            raise ValidationError({"progress": _("Прогресс должен быть в пределах от 0 до 100.")})

    def has_review(self) -> bool:
        cached = getattr(self, "_has_review_cache", None)
        if cached is not None:
            return bool(cached)
        exists = Rating.objects.filter(
            book=self.book,
            user=self.participant.user,
            review__isnull=False,
        ).exclude(review="").exists()
        self._has_review_cache = exists
        return exists

    def mark_completed(self, *, auto: bool) -> None:
        self.status = self.Status.COMPLETED
        if auto:
            self.completion_status = self.CompletionStatus.CONFIRMED
        else:
            self.completion_status = self.CompletionStatus.AWAITING_REVIEW
        self.save(update_fields=["status", "completion_status", "updated_at"])