from __future__ import annotations

from typing import Iterable

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from django.db.models.functions import Coalesce

from books.models import Book

User = get_user_model()


class ReadingClubQuerySet(models.QuerySet):
    def with_message_count(self) -> "ReadingClubQuerySet":
        message_count_subquery = Subquery(
            DiscussionPost.objects.filter(topic__reading=OuterRef("pk"))
            .order_by()
            .values("topic__reading")
            .annotate(total=Count("pk"))
            .values("total")[:1],
            output_field=IntegerField(),
        )
        approved_participant_count_subquery = Subquery(
            ReadingParticipant.objects.filter(
                reading=OuterRef("pk"),
                status=ReadingParticipant.Status.APPROVED,
            )
            .order_by()
            .values("reading")
            .annotate(total=Count("pk"))
            .values("total")[:1],
            output_field=IntegerField(),
        )
        return self.annotate(
            message_count=Coalesce(message_count_subquery, 0),
            approved_participant_count=Coalesce(
                approved_participant_count_subquery, 0
            ),
        )

    def active(self) -> "ReadingClubQuerySet":
        today = timezone.localdate()
        return self.filter(
            start_date__lte=today,
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=today)
        )

    def upcoming(self) -> "ReadingClubQuerySet":
        today = timezone.localdate()
        return self.filter(start_date__gt=today)

    def past(self) -> "ReadingClubQuerySet":
        today = timezone.localdate()
        return self.filter(end_date__lt=today)


class ReadingClub(models.Model):
    class JoinPolicy(models.TextChoices):
        OPEN = "open", _("Открыто для всех")
        REQUEST = "request", _("По запросу")

    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name="reading_clubs",
        verbose_name=_("Книга"),
    )
    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_reading_clubs",
        verbose_name=_("Создатель"),
    )
    title = models.CharField(max_length=255, verbose_name=_("Название"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))
    start_date = models.DateField(verbose_name=_("Дата начала"))
    end_date = models.DateField(blank=True, null=True, verbose_name=_("Дата окончания"))
    join_policy = models.CharField(
        max_length=20,
        choices=JoinPolicy.choices,
        default=JoinPolicy.OPEN,
        verbose_name=_("Присоединение"),
    )
    slug = models.SlugField(max_length=255, unique=True, verbose_name=_("URL"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создано"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлено"))

    objects = ReadingClubQuerySet.as_manager()

    class Meta:
        ordering = ("-start_date", "-created_at")
        verbose_name = _("Совместное чтение")
        verbose_name_plural = _("Совместные чтения")

    def __str__(self) -> str:  # pragma: no cover - simple display
        return self.title

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            base_slug = slugify(self.title) or "reading"
            slug = base_slug
            suffix = 1
            while ReadingClub.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                suffix += 1
                slug = f"{base_slug}-{suffix}"
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("reading_clubs:detail", kwargs={"slug": self.slug})

    @property
    def status(self) -> str:
        today = timezone.localdate()
        if self.start_date > today:
            return "upcoming"
        if self.end_date and self.end_date < today:
            return "past"
        return "active"

    @property
    def message_count(self) -> int:
        cached = getattr(self, "_message_count", None)
        if cached is not None:
            return int(cached)
        return self.posts.count()
    
    @message_count.setter
    def message_count(self, value: int | None) -> None:
        self._message_count = None if value is None else int(value)

    def set_prefetched_message_count(self, value: int) -> None:
        self._message_count = value

    def get_participants(self, approved_only: bool = True) -> Iterable["ReadingParticipant"]:
        qs = self.participants.select_related("user")
        if approved_only:
            qs = qs.filter(status=ReadingParticipant.Status.APPROVED)
        return qs.order_by("-joined_at")

    @property
    def posts(self):
        return DiscussionPost.objects.filter(topic__reading=self)

    @property
    def approved_participant_count(self) -> int:
        cached = getattr(self, "_approved_participant_count", None)
        if cached is not None:
            return int(cached)
        return self.participants.filter(status=ReadingParticipant.Status.APPROVED).count()

    @approved_participant_count.setter
    def approved_participant_count(self, value: int | None) -> None:
        self._approved_participant_count = None if value is None else int(value)
        

class ReadingParticipant(models.Model):
    class Status(models.TextChoices):
        APPROVED = "approved", _("Участник")
        PENDING = "pending", _("Ожидает подтверждения")

    reading = models.ForeignKey(
        ReadingClub,
        on_delete=models.CASCADE,
        related_name="participants",
        verbose_name=_("Совместное чтение"),
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="reading_participations",
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
        unique_together = ("reading", "user")
        verbose_name = _("Участник совместного чтения")
        verbose_name_plural = _("Участники совместных чтений")

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.user} — {self.reading}"


class ReadingNorm(models.Model):
    reading = models.ForeignKey(
        ReadingClub,
        on_delete=models.CASCADE,
        related_name="topics",
        verbose_name=_("Совместное чтение"),
    )
    title = models.CharField(max_length=255, verbose_name=_("Название нормы"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))
    order = models.PositiveIntegerField(default=1, verbose_name=_("Порядок"))
    discussion_opens_at = models.DateField(verbose_name=_("Дата открытия обсуждения"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создано"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлено"))

    class Meta:
        ordering = ("order", "discussion_opens_at", "id")
        verbose_name = _("Норма чтения")
        verbose_name_plural = _("Нормы чтения")

    def __str__(self) -> str:  # pragma: no cover - simple display
        return self.title

    def is_open(self) -> bool:
        return self.discussion_opens_at <= timezone.localdate()

    def get_absolute_url(self) -> str:
        return reverse(
            "reading_clubs:topic_detail",
            kwargs={"slug": self.reading.slug, "pk": self.pk},
        )


class DiscussionPost(models.Model):
    topic = models.ForeignKey(
        ReadingNorm,
        on_delete=models.CASCADE,
        related_name="posts",
        verbose_name=_("Тема"),
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="replies",
        null=True,
        blank=True,
        verbose_name=_("Ответ на"),
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="reading_posts",
        verbose_name=_("Автор"),
    )
    content = models.TextField(verbose_name=_("Сообщение"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создано"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлено"))

    class Meta:
        ordering = ("created_at", "id")
        verbose_name = _("Сообщение обсуждения")
        verbose_name_plural = _("Сообщения обсуждений")

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.author}: {self.content[:30]}"