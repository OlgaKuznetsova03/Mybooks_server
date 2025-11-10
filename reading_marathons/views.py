from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DetailView, ListView

from accounts.services import charge_feature_access, InsufficientCoinsError

from user_ratings.services import award_for_marathon_confirmation

from .forms import (
    MarathonEntryForm,
    MarathonEntryStatusForm,
    ReadingMarathonForm,
)
from .models import MarathonEntry, MarathonParticipant, ReadingMarathon


class MarathonListView(ListView):
    model = ReadingMarathon
    queryset = ReadingMarathon.objects.prefetch_related("themes").all()
    context_object_name = "marathons"
    template_name = "reading_marathons/list.html"


class MarathonCreateView(LoginRequiredMixin, CreateView):
    form_class = ReadingMarathonForm
    template_name = "reading_marathons/create.html"

    def form_valid(self, form: ReadingMarathonForm) -> HttpResponse:
        user = self.request.user
        try:
            with transaction.atomic():
                charge_feature_access(
                    user.profile,
                    description=_("Создание марафона"),
                )
                form.instance.creator = user
                response = super().form_valid(form)
        except InsufficientCoinsError:
            form.add_error(None, _("Недостаточно монет для создания марафона."))
            return self.form_invalid(form)

        messages.success(self.request, _("Марафон создан. Пригласите друзей к чтению!"))
        return response

    def get_success_url(self) -> str:
        return self.object.get_absolute_url()


class MarathonDetailView(DetailView):
    model = ReadingMarathon
    slug_field = "slug"
    slug_url_kwarg = "slug"
    template_name = "reading_marathons/detail.html"
    context_object_name = "marathon"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        marathon: ReadingMarathon = context["marathon"]
        participants = marathon.participants.select_related("user").order_by("joined_at")
        participant = None
        if self.request.user.is_authenticated:
            participant = participants.filter(user=self.request.user).first()
        context["participant"] = participant
        context["participants"] = participants
        if participant and participant.is_approved:
            context["entry_form"] = MarathonEntryForm(
                marathon=marathon,
                user=self.request.user,
                initial={"status": MarathonEntry.Status.PLANNED},
            )
        participant_groups = self._build_participant_groups(marathon)
        context["participant_groups"] = participant_groups
        context["participant_entries"] = [
            (participant_obj, participant_groups.get(participant_obj, []))
            for participant_obj in participants
        ]
        context["entry_status"] = MarathonEntry.Status
        context["completion_status"] = MarathonEntry.CompletionStatus
        return context

    def _build_participant_groups(self, marathon: ReadingMarathon) -> Dict[MarathonParticipant, list]:
        groups: Dict[MarathonParticipant, list] = defaultdict(list)
        entries = (
            MarathonEntry.objects.filter(participant__marathon=marathon)
            .select_related("participant__user", "theme", "book", "book__primary_isbn")
            .prefetch_related("book__isbn")
            .order_by("participant__user__username", "theme__order", "created_at")
        )
        for entry in entries:
            groups[entry.participant].append(entry)
        return groups


@login_required
def marathon_join(request: HttpRequest, slug: str) -> HttpResponse:
    marathon = get_object_or_404(ReadingMarathon, slug=slug)
    participant, created = MarathonParticipant.objects.get_or_create(
        marathon=marathon,
        user=request.user,
    )
    if created:
        if marathon.join_policy == ReadingMarathon.JoinPolicy.REQUEST:
            participant.status = MarathonParticipant.Status.PENDING
            participant.save(update_fields=["status"])
            messages.info(
                request,
                _("Заявка отправлена. Создатель марафона подтвердит участие."),
            )
        else:
            messages.success(request, _("Вы присоединились к марафону!"))
    else:
        messages.warning(request, _("Вы уже участвуете в марафоне."))
    return redirect(marathon.get_absolute_url())


@login_required
def marathon_participant_approve(request: HttpRequest, pk: int) -> HttpResponse:
    participant = get_object_or_404(
        MarathonParticipant.objects.select_related("marathon", "user"),
        pk=pk,
    )
    if participant.marathon.creator != request.user:
        return HttpResponseForbidden()
    participant.status = MarathonParticipant.Status.APPROVED
    participant.save(update_fields=["status"])
    messages.success(request, _("Участник одобрен."))
    return redirect(participant.marathon.get_absolute_url())


@login_required
def marathon_entry_create(request: HttpRequest, slug: str) -> HttpResponse:
    marathon = get_object_or_404(ReadingMarathon, slug=slug)
    participant = get_object_or_404(
        MarathonParticipant,
        marathon=marathon,
        user=request.user,
    )
    if not participant.is_approved:
        messages.error(request, _("Дождитесь подтверждения участия."))
        return redirect(marathon.get_absolute_url())

    if request.method == "POST":
        form = MarathonEntryForm(request.POST, marathon=marathon, user=request.user)
        if form.is_valid():
            entry: MarathonEntry = form.save(commit=False)
            entry.participant = participant
            if marathon.book_submission_policy == ReadingMarathon.BookSubmissionPolicy.APPROVAL:
                entry.book_approved = False
            entry.save()
            messages.success(request, _("Книга добавлена в ваш марафон."))
            return redirect(marathon.get_absolute_url())
    else:
        form = MarathonEntryForm(marathon=marathon, user=request.user)
    return render(
        request,
        "reading_marathons/entry_form.html",
        {"marathon": marathon, "form": form},
    )


@login_required
def marathon_entry_update(request: HttpRequest, pk: int) -> HttpResponse:
    entry = get_object_or_404(
        MarathonEntry.objects.select_related("participant__marathon", "participant__user"),
        pk=pk,
    )
    marathon = entry.participant.marathon
    if entry.participant.user != request.user:
        return HttpResponseForbidden()

    if request.method == "POST":
        previous_completion = entry.completion_status
        form = MarathonEntryStatusForm(request.POST, instance=entry)
        if form.is_valid():
            previous_completion = entry.completion_status
            entry = form.save()
            if (
                entry.status == MarathonEntry.Status.COMPLETED
                and marathon.completion_policy == ReadingMarathon.CompletionPolicy.AUTO
                and entry.has_review()
            ):
                if entry.completion_status != MarathonEntry.CompletionStatus.CONFIRMED:
                    entry.completion_status = MarathonEntry.CompletionStatus.CONFIRMED
                    entry.save(update_fields=["completion_status", "updated_at"])
                    completion_became_confirmed = True
            elif entry.status == MarathonEntry.Status.COMPLETED:
                if entry.completion_status != MarathonEntry.CompletionStatus.AWAITING_REVIEW:
                    entry.completion_status = MarathonEntry.CompletionStatus.AWAITING_REVIEW
                    entry.save(update_fields=["completion_status", "updated_at"])
            elif entry.status != MarathonEntry.Status.COMPLETED:
                if entry.completion_status != MarathonEntry.CompletionStatus.IN_PROGRESS:
                    entry.completion_status = MarathonEntry.CompletionStatus.IN_PROGRESS
                    entry.save(update_fields=["completion_status", "updated_at"])
            if (
                entry.completion_status == MarathonEntry.CompletionStatus.CONFIRMED
                and (completion_became_confirmed or previous_completion != MarathonEntry.CompletionStatus.CONFIRMED)
            ):
                award_for_marathon_confirmation(entry)
            messages.success(request, _("Прогресс по книге обновлён."))
            return redirect(marathon.get_absolute_url())
    else:
        form = MarathonEntryStatusForm(instance=entry)
    return render(
        request,
        "reading_marathons/entry_update.html",
        {"entry": entry, "marathon": marathon, "form": form},
    )


@login_required
def marathon_entry_approve(request: HttpRequest, pk: int) -> HttpResponse:
    entry = get_object_or_404(
        MarathonEntry.objects.select_related("participant__marathon", "participant__user"),
        pk=pk,
    )
    marathon = entry.participant.marathon
    if marathon.creator != request.user:
        return HttpResponseForbidden()

    entry.book_approved = True
    entry.save(update_fields=["book_approved", "updated_at"])
    messages.success(request, _("Книга подтверждена и добавлена на полку."))
    return redirect(marathon.get_absolute_url())


@login_required
def marathon_entry_confirm_completion(request: HttpRequest, pk: int) -> HttpResponse:
    entry = get_object_or_404(
        MarathonEntry.objects.select_related("participant__marathon", "participant__user"),
        pk=pk,
    )
    marathon = entry.participant.marathon
    if marathon.creator != request.user:
        return HttpResponseForbidden()

    if entry.status != MarathonEntry.Status.COMPLETED:
        messages.error(request, _("Участник ещё не завершил чтение книги."))
        return redirect(marathon.get_absolute_url())

    previous_completion = entry.completion_status
    entry.completion_status = MarathonEntry.CompletionStatus.CONFIRMED
    entry.save(update_fields=["completion_status", "updated_at"])
    if previous_completion != MarathonEntry.CompletionStatus.CONFIRMED:
        award_for_marathon_confirmation(entry)
    messages.success(request, _("Этап зачтён."))
    return redirect(marathon.get_absolute_url())