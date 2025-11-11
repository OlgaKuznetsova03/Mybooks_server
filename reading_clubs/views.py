from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Prefetch, Subquery
from django.http import Http404, HttpRequest, HttpResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from django.db.models.functions import Coalesce

from accounts.services import charge_feature_access, InsufficientCoinsError
from user_ratings.services import award_for_discussion_post

from django.shortcuts import get_object_or_404, redirect, render

from .forms import DiscussionPostForm, ReadingClubForm, ReadingNormForm
from .models import DiscussionPost, ReadingClub, ReadingNorm, ReadingParticipant
from shelves.models import BookProgress, ShelfItem
from shelves.services import ALL_DEFAULT_READ_SHELF_NAMES


def _format_reply_prefill(post: DiscussionPost) -> str:
    author_name = post.author.get_full_name() or post.author.username
    quoted_lines = "\n".join(f"> {line}" for line in post.content.splitlines())
    if not quoted_lines:
        quoted_lines = ">"
    return f"Ответ на {author_name}:\n{quoted_lines}\n\n"


def _resolve_parent_post(topic: ReadingNorm, parent_value: str | None) -> DiscussionPost | None:
    if not parent_value:
        return None
    try:
        parent_id = int(parent_value)
    except (TypeError, ValueError):
        return None
    try:
        return topic.posts.select_related("author").get(pk=parent_id)
    except DiscussionPost.DoesNotExist:
        return None


def _build_post_threads(posts: Iterable[DiscussionPost]) -> list[DiscussionPost]:
    posts_list = list(posts)
    children_map: dict[int | None, list[DiscussionPost]] = defaultdict(list)
    for post in posts_list:
        children_map[post.parent_id].append(post)
    for post in posts_list:
        children = children_map.get(post.pk, ())
        setattr(post, "thread_children", list(children))
    return list(children_map.get(None, ()))


@dataclass
class ReadingClubGrouping:
    title: str
    slug: str
    description: str
    queryset: list[ReadingClub]


class ReadingClubListView(ListView):
    template_name = "reading_clubs/list.html"
    context_object_name = "groupings"

    def get_queryset(self):  # type: ignore[override]
        base_qs = (
            ReadingClub.objects.select_related("book", "book__primary_isbn", "creator")
            .with_message_count()
            .prefetch_related("participants", "book__isbn")
            .order_by("start_date", "title")
        )
        today = timezone.localdate()
        active = []
        upcoming = []
        past = []
        for club in base_qs:
            club.set_prefetched_message_count(club.message_count)
            if club.start_date > today:
                upcoming.append(club)
            elif club.end_date and club.end_date < today:
                past.append(club)
            else:
                active.append(club)
        return [
            ReadingClubGrouping(
                title="Актуальные совместные чтения",
                slug="active",
                description="Участники уже обсуждают книгу прямо сейчас.",
                queryset=active,
            ),
            ReadingClubGrouping(
                title="Предстоящие совместные чтения",
                slug="upcoming",
                description="Записывайтесь заранее, чтобы не пропустить старт.",
                queryset=upcoming,
            ),
            ReadingClubGrouping(
                title="Завершённые совместные чтения",
                slug="past",
                description="История обсуждений и впечатлений участников.",
                queryset=past,
            ),
        ]


class ReadingClubCreateView(LoginRequiredMixin, FormView):
    template_name = "reading_clubs/create.html"
    form_class = ReadingClubForm

    def get_initial(self):
        initial = super().get_initial()
        book_id = self.request.GET.get("book")
        if book_id:
            initial["book"] = book_id
        return initial

    def form_valid(self, form: ReadingClubForm):  # type: ignore[override]
        user = self.request.user
        reading_club: ReadingClub = form.save(commit=False)

        try:
            with transaction.atomic():
                charge_feature_access(
                    user.profile,
                    description=_("Создание совместного чтения"),
                )
                reading_club.creator = user
                reading_club.save()
                ReadingParticipant.objects.get_or_create(
                    reading=reading_club,
                    user=user,
                    defaults={"status": ReadingParticipant.Status.APPROVED},
                )
        except InsufficientCoinsError:
            form.add_error(None, _("Недостаточно монет для создания совместного чтения."))
            return self.form_invalid(form)

        messages.success(
            self.request,
            "Совместное чтение создано. Теперь добавьте нормы и пригласите участников!",
        )
        return redirect(reading_club.get_absolute_url())


class ReadingClubDetailView(DetailView):
    model = ReadingClub
    slug_field = "slug"
    slug_url_kwarg = "slug"
    context_object_name = "reading"
    template_name = "reading_clubs/detail.html"

    def get_queryset(self):  # type: ignore[override]
        return (
            ReadingClub.objects.select_related("book", "creator")
            .prefetch_related(
                Prefetch(
                    "topics",
                    queryset=self._topics_with_post_count(),
                ),
                Prefetch(
                    "participants",
                    queryset=ReadingParticipant.objects.select_related("user"),
                ),
            )
            .with_message_count()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        reading: ReadingClub = context["reading"]
        participants = list(reading.participants.all())
        topics = list(reading.topics.all())
        context["topics"] = topics
        approved_participants = [
            participant
            for participant in participants
            if participant.status == ReadingParticipant.Status.APPROVED
        ]
        self._attach_progress(reading, approved_participants)
        context["approved_participants"] = approved_participants
        context["pending_participants"] = [
            participant for participant in participants
            if participant.status == ReadingParticipant.Status.PENDING
        ]
        context["is_participant"] = False
        if self.request.user.is_authenticated:
            context["is_participant"] = reading.participants.filter(
                user=self.request.user,
                status=ReadingParticipant.Status.APPROVED,
            ).exists()
        return context

    def _topics_with_post_count(self):
        post_count_subquery = Subquery(
            DiscussionPost.objects.filter(topic=OuterRef("pk"))
            .order_by()
            .values("topic")
            .annotate(total=Count("pk"))
            .values("total")[:1],
            output_field=IntegerField(),
        )
        return (
            ReadingNorm.objects.order_by("order", "discussion_opens_at")
            .annotate(post_count=Coalesce(post_count_subquery, 0))
        )

    def _attach_progress(
        self,
        reading: ReadingClub,
        participants: list[ReadingParticipant],
    ) -> None:
        if not participants:
            return

        user_ids = [participant.user_id for participant in participants]
        progress_qs = BookProgress.objects.filter(
            user_id__in=user_ids,
            book=reading.book,
            event__isnull=True,
        )
        progress_map = {progress.user_id: progress for progress in progress_qs}
        read_users = set(
            ShelfItem.objects.filter(
                shelf__user_id__in=user_ids,
                shelf__name__in=ALL_DEFAULT_READ_SHELF_NAMES,
                book=reading.book,
            ).values_list("shelf__user_id", flat=True)
        )

        for participant in participants:
            participant.reading_progress_percent = None
            participant.reading_progress_source = None
            progress = progress_map.get(participant.user_id)

            percent: float | None = None
            if progress and progress.percent is not None:
                try:
                    percent = float(progress.percent)
                except (TypeError, ValueError):
                    percent = None
            if percent is not None:
                percent = max(0.0, min(percent, 100.0))

            if participant.user_id in read_users and (percent is None or percent < 100.0):
                percent = 100.0
                participant.reading_progress_source = "shelf"
            elif percent is not None:
                participant.reading_progress_source = "progress"

            if percent is not None:
                participant.reading_progress_percent = round(percent)


@login_required
def reading_join(request: HttpRequest, slug: str) -> HttpResponse:
    reading = get_object_or_404(ReadingClub, slug=slug)
    participant, created = ReadingParticipant.objects.get_or_create(
        reading=reading,
        user=request.user,
        defaults={
            "status": ReadingParticipant.Status.APPROVED
            if reading.join_policy == ReadingClub.JoinPolicy.OPEN
            else ReadingParticipant.Status.PENDING
        },
    )
    if not created:
        if participant.status == ReadingParticipant.Status.APPROVED:
            messages.info(request, "Вы уже участвуете в этих совместных чтениях.")
        else:
            messages.info(request, "Ваша заявка уже ожидает подтверждения.")
        return redirect(reading.get_absolute_url())

    if reading.join_policy == ReadingClub.JoinPolicy.OPEN:
        messages.success(request, "Вы присоединились к совместным чтениям!")
    else:
        messages.success(request, "Заявка отправлена создателю совместных чтений.")
    return redirect(reading.get_absolute_url())


@login_required
def reading_approve_participant(request: HttpRequest, slug: str, participant_id: int) -> HttpResponse:
    reading = get_object_or_404(ReadingClub, slug=slug)
    if reading.creator != request.user:
        raise Http404
    participant = get_object_or_404(ReadingParticipant, pk=participant_id, reading=reading)
    if request.method == "POST":
        participant.status = ReadingParticipant.Status.APPROVED
        participant.save(update_fields=["status"])
        messages.success(request, f"{participant.user} теперь участвует в совместных чтениях.")
    return redirect(reading.get_absolute_url())


class ReadingNormCreateView(LoginRequiredMixin, View):
    template_name = "reading_clubs/topic_form.html"

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        self.reading = get_object_or_404(ReadingClub, slug=kwargs["slug"])
        if self.reading.creator != request.user:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        form = ReadingNormForm()
        return self._render(form, request)

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        form = ReadingNormForm(request.POST)
        if form.is_valid():
            topic: ReadingNorm = form.save(commit=False)
            topic.reading = self.reading
            topic.save()
            messages.success(request, "Норма добавлена в совместные чтения.")
            return redirect(self.reading.get_absolute_url())
        return self._render(form, request)

    def _render(self, form: ReadingNormForm, request: HttpRequest) -> HttpResponse:
        context = {
            "form": form,
            "reading": self.reading,
            "topic": None,
            "form_mode": "create",
        }
        return render(request, self.template_name, context)


class ReadingNormUpdateView(LoginRequiredMixin, View):
    template_name = "reading_clubs/topic_form.html"

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        self.reading = get_object_or_404(ReadingClub, slug=kwargs["slug"])
        self.topic = get_object_or_404(ReadingNorm, pk=kwargs["pk"], reading=self.reading)
        if self.reading.creator != request.user:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        form = ReadingNormForm(instance=self.topic)
        return self._render(form, request)

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        form = ReadingNormForm(request.POST, instance=self.topic)
        if form.is_valid():
            form.save()
            messages.success(request, "Изменения нормы сохранены.")
            return redirect(self.reading.get_absolute_url())
        return self._render(form, request)

    def _render(self, form: ReadingNormForm, request: HttpRequest) -> HttpResponse:
        context = {
            "form": form,
            "reading": self.reading,
            "topic": self.topic,
            "form_mode": "update",
        }
        return render(request, self.template_name, context)


class ReadingTopicDetailView(DetailView):
    model = ReadingNorm
    template_name = "reading_clubs/topic_detail.html"
    context_object_name = "topic"

    def get_queryset(self):  # type: ignore[override]
        return (
            ReadingNorm.objects.select_related("reading", "reading__book", "reading__creator")
            .prefetch_related(
                Prefetch(
                    "posts",
                    queryset=DiscussionPost.objects.select_related(
                        "author",
                        "parent",
                        "parent__author",
                    ).order_by("created_at", "id"),
                ),
            )
        )


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        topic: ReadingNorm = context["topic"]
        reading = topic.reading
        user = self.request.user
        is_participant = False
        can_post = False
        if user.is_authenticated:
            is_participant = reading.participants.filter(
                user=user,
                status=ReadingParticipant.Status.APPROVED,
            ).exists()
            can_post = is_participant and topic.is_open()
            form = None
        reply_to_post = None
        if can_post:
            reply_to_post = self._get_reply_post(topic)
            initial = {}
            if reply_to_post:
                initial["content"] = _format_reply_prefill(reply_to_post)
            form = DiscussionPostForm(initial=initial)
        threaded_posts = _build_post_threads(topic.posts.all())
        context.update(
            {
                "reading": reading,
                "is_participant": is_participant,
                "can_post": can_post,
                "form": form,
                "reply_to_post": reply_to_post,
                "threaded_posts": threaded_posts,
            }
        )
        return context

    def _get_reply_post(self, topic: ReadingNorm) -> DiscussionPost | None:
        return _resolve_parent_post(topic, self.request.GET.get("reply_to"))
    

@method_decorator(login_required, name="dispatch")
class DiscussionPostCreateView(View):
    def post(self, request: HttpRequest, slug: str, pk: int) -> HttpResponse:
        topic = get_object_or_404(
            ReadingNorm.objects.select_related("reading"),
            pk=pk,
            reading__slug=slug,
        )
        reading = topic.reading
        if not topic.is_open():
            messages.error(request, "Обсуждение этой нормы ещё не открыто.")
            return redirect(topic.get_absolute_url())
        if not reading.participants.filter(
            user=request.user,
            status=ReadingParticipant.Status.APPROVED,
        ).exists():
            messages.error(request, "Только участники могут оставлять сообщения.")
            return redirect(topic.get_absolute_url())
        parent_post = _resolve_parent_post(topic, request.POST.get("parent"))
        form = DiscussionPostForm(request.POST)
        if form.is_valid():
            post: DiscussionPost = form.save(commit=False)
            post.topic = topic
            post.author = request.user
            if parent_post:
                post.parent = parent_post
            post.save()
            award_for_discussion_post(post)
            messages.success(request, "Сообщение добавлено.")
            return redirect(topic.get_absolute_url())
        context = {
            "topic": topic,
            "reading": reading,
            "form": form,
            "is_participant": True,
            "can_post": True,
            "reply_to_post": parent_post,
        }
        return render(request, "reading_clubs/topic_detail.html", context)