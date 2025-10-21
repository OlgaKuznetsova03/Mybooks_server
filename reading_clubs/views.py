from __future__ import annotations

from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Prefetch
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from user_ratings.services import award_for_discussion_post

from .forms import DiscussionPostForm, ReadingClubForm, ReadingNormForm
from .models import DiscussionPost, ReadingClub, ReadingNorm, ReadingParticipant


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
        reading_club: ReadingClub = form.save(commit=False)
        reading_club.creator = self.request.user
        reading_club.save()
        ReadingParticipant.objects.get_or_create(
            reading=reading_club,
            user=self.request.user,
            defaults={"status": ReadingParticipant.Status.APPROVED},
        )
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
                    queryset=ReadingNorm.objects.order_by("order", "discussion_opens_at").annotate(
                        post_count=Count("posts")
                    ),
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
        context["topics"] = reading.topics.all()
        context["approved_participants"] = [
            participant for participant in participants
            if participant.status == ReadingParticipant.Status.APPROVED
        ]
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
        return render(request, self.template_name, {"form": form, "reading": self.reading})

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        form = ReadingNormForm(request.POST)
        if form.is_valid():
            topic: ReadingNorm = form.save(commit=False)
            topic.reading = self.reading
            topic.save()
            messages.success(request, "Норма добавлена в совместные чтения.")
            return redirect(self.reading.get_absolute_url())
        return render(request, self.template_name, {"form": form, "reading": self.reading})


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
                    ).order_by("created_at"),
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
        context.update(
            {
                "reading": reading,
                "is_participant": is_participant,
                "can_post": can_post,
                "form": form,
                "reply_to_post": reply_to_post,
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