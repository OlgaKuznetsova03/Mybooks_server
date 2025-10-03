from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import DetailView, ListView
from django.views.generic.edit import CreateView, FormView

from .forms import (
    AuthorOfferForm,
    AuthorOfferResponseForm,
    BloggerPlatformPresenceFormSet,
    BloggerRequestForm,
    BloggerRequestResponseForm,
    CollaborationReviewForm,
)
from .models import (
    AuthorOffer,
    AuthorOfferResponse,
    BloggerRequest,
    BloggerRequestResponse,
    Collaboration,
    CollaborationStatusUpdate,
)

User = get_user_model()


def _user_is_blogger(user: User) -> bool:
    profile = getattr(user, "profile", None)
    if profile is not None and hasattr(profile, "is_blogger"):
        try:
            return bool(profile.is_blogger)
        except Exception:  # pragma: no cover - безопасная защита
            return False
    return user.groups.filter(name="blogger").exists()


def _user_is_author(user: User) -> bool:
    profile = getattr(user, "profile", None)
    if profile is not None and hasattr(profile, "is_author"):
        try:
            return bool(profile.is_author)
        except Exception:  # pragma: no cover
            return False
    return user.groups.filter(name="author").exists()


class OfferListView(ListView):
    model = AuthorOffer
    template_name = "collaborations/offer_list.html"
    context_object_name = "offers"
    paginate_by = 10

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("author")
            .prefetch_related("expected_platforms")
        )
        q = self.request.GET.get("q")
        if q:
            queryset = queryset.filter(Q(title__icontains=q) | Q(synopsis__icontains=q))
        return queryset.filter(is_active=True)


class OfferDetailView(DetailView):
    model = AuthorOffer
    template_name = "collaborations/offer_detail.html"
    context_object_name = "offer"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context["response_form"] = AuthorOfferResponseForm()
            context["existing_response"] = AuthorOfferResponse.objects.filter(
                offer=self.object,
                respondent=self.request.user,
            ).first()
            context["can_respond"] = (
                self.object.author_id != self.request.user.id
                and (
                    self.object.allow_regular_users
                    or _user_is_blogger(self.request.user)
                )
            )
        return context


class OfferCreateView(LoginRequiredMixin, CreateView):
    model = AuthorOffer
    form_class = AuthorOfferForm
    template_name = "collaborations/offer_form.html"
    success_url = reverse_lazy("collaborations:offer_list")

    def dispatch(self, request, *args, **kwargs):
        if not _user_is_author(request.user):
            messages.error(request, _("Создавать предложения могут только авторы."))
            return redirect("collaborations:offer_list")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.author = self.request.user
        messages.success(self.request, _("Предложение опубликовано."))
        return super().form_valid(form)


class OfferRespondView(LoginRequiredMixin, FormView):
    form_class = AuthorOfferResponseForm

    def dispatch(self, request, *args, **kwargs):
        self.offer = get_object_or_404(AuthorOffer, pk=kwargs["pk"])
        if self.offer.author_id == request.user.id:
            messages.error(request, _("Вы не можете откликнуться на собственное предложение."))
            return redirect("collaborations:offer_detail", pk=self.offer.pk)
        if not self.offer.allow_regular_users and not _user_is_blogger(request.user):
            messages.error(request, _("Только блогеры могут откликаться на это предложение."))
            return redirect("collaborations:offer_detail", pk=self.offer.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response, created = AuthorOfferResponse.objects.get_or_create(
            offer=self.offer,
            respondent=self.request.user,
            defaults={"message": form.cleaned_data.get("message", "")},
        )
        if not created:
            response.message = form.cleaned_data.get("message", "")
            response.status = AuthorOfferResponse.Status.PENDING
            response.save(update_fields=["message", "status", "updated_at"])
            messages.info(self.request, _("Отклик обновлён."))
        else:
            messages.success(self.request, _("Отклик отправлен автору."))
        return redirect("collaborations:offer_detail", pk=self.offer.pk)


class BloggerRequestListView(ListView):
    model = BloggerRequest
    template_name = "collaborations/blogger_request_list.html"
    context_object_name = "requests"
    paginate_by = 10

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("blogger")
            .prefetch_related("preferred_genres", "review_formats", "platforms")
        )
        q = self.request.GET.get("q")
        if q:
            queryset = queryset.filter(Q(title__icontains=q) | Q(additional_info__icontains=q))
        return queryset.filter(is_active=True)


class BloggerRequestDetailView(DetailView):
    model = BloggerRequest
    template_name = "collaborations/blogger_request_detail.html"
    context_object_name = "request_obj"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context["response_form"] = BloggerRequestResponseForm()
            context["existing_response"] = BloggerRequestResponse.objects.filter(
                request=self.object,
                author=self.request.user,
            ).first()
            context["can_respond"] = (
                self.object.blogger_id != self.request.user.id
                and _user_is_author(self.request.user)
            )
        return context


class BloggerRequestCreateView(LoginRequiredMixin, View):
    template_name = "collaborations/blogger_request_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not _user_is_blogger(request.user):
            messages.error(request, _("Только блогеры могут создавать такие заявки."))
            return redirect("collaborations:blogger_request_list")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        form = BloggerRequestForm()
        formset = BloggerPlatformPresenceFormSet()
        return render(request, self.template_name, {"form": form, "formset": formset})

    def post(self, request):
        form = BloggerRequestForm(request.POST)
        if form.is_valid():
            blogger_request = form.save(commit=False)
            blogger_request.blogger = request.user
            formset = BloggerPlatformPresenceFormSet(request.POST, instance=blogger_request)
            if formset.is_valid():
                blogger_request.save()
                form.save_m2m()
                formset.save()
                messages.success(request, _("Заявка блогера опубликована."))
                return redirect("collaborations:blogger_request_list")
        else:
            formset = BloggerPlatformPresenceFormSet(request.POST)
        return render(request, self.template_name, {"form": form, "formset": formset})


class BloggerRequestRespondView(LoginRequiredMixin, FormView):
    form_class = BloggerRequestResponseForm

    def dispatch(self, request, *args, **kwargs):
        self.request_obj = get_object_or_404(BloggerRequest, pk=kwargs["pk"])
        if self.request_obj.blogger_id == request.user.id:
            messages.error(request, _("Вы не можете откликнуться на собственную заявку."))
            return redirect("collaborations:blogger_request_detail", pk=self.request_obj.pk)
        if not _user_is_author(request.user):
            messages.error(request, _("Откликаться на заявки могут только авторы."))
            return redirect("collaborations:blogger_request_detail", pk=self.request_obj.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response, created = BloggerRequestResponse.objects.get_or_create(
            request=self.request_obj,
            author=self.request.user,
            defaults={"message": form.cleaned_data.get("message", "")},
        )
        if not created:
            response.message = form.cleaned_data.get("message", "")
            response.status = BloggerRequestResponse.Status.PENDING
            response.save(update_fields=["message", "status", "updated_at"])
            messages.info(self.request, _("Отклик обновлён."))
        else:
            messages.success(self.request, _("Отклик отправлен блогеру."))
        return redirect("collaborations:blogger_request_detail", pk=self.request_obj.pk)


class CollaborationListView(LoginRequiredMixin, ListView):
    model = Collaboration
    template_name = "collaborations/collaboration_list.html"
    context_object_name = "collaborations"

    def get_queryset(self):
        return (
            Collaboration.objects.filter(
                Q(author=self.request.user) | Q(partner=self.request.user)
            )
            .select_related("author", "partner", "offer", "request")
            .order_by("-created_at")
        )


class CollaborationReviewUpdateView(LoginRequiredMixin, View):
    template_name = "collaborations/collaboration_review_form.html"

    def get_object(self, pk: int) -> Collaboration:
        return get_object_or_404(
            Collaboration,
            pk=pk,
            partner=self.request.user,
        )

    def get(self, request, pk: int):
        collaboration = self.get_object(pk)
        form = CollaborationReviewForm(instance=collaboration)
        return render(request, self.template_name, {"form": form, "collaboration": collaboration})

    def post(self, request, pk: int):
        collaboration = self.get_object(pk)
        form = CollaborationReviewForm(request.POST, instance=collaboration)
        if form.is_valid():
            collaboration.partner_confirmed = True
            collaboration.review_links = form.cleaned_data["review_links"]
            collaboration.status = Collaboration.Status.ACTIVE
            collaboration.updated_at = timezone.now()
            collaboration.save(update_fields=["partner_confirmed", "review_links", "status", "updated_at"])
            messages.success(request, _("Ссылки на отзывы отправлены автору."))
            return redirect("collaborations:collaboration_list")
        return render(request, self.template_name, {"form": form, "collaboration": collaboration})


@login_required
def confirm_collaboration_completion(request, pk: int):
    collaboration = get_object_or_404(
        Collaboration,
        pk=pk,
        author=request.user,
    )
    links = collaboration.get_review_links()
    if not links:
        messages.error(request, _("Нельзя подтвердить сотрудничество без ссылок на отзывы."))
        return redirect("collaborations:collaboration_list")

    update = CollaborationStatusUpdate.confirm_completion(collaboration, links)
    collaboration.author_confirmed = True
    collaboration.save(update_fields=["author_confirmed"])

    if update.rating_change is not None:
        messages.success(
            request,
            _("Сотрудничество завершено. Рейтинг блогера изменился на %(delta)s баллов.")
            % {"delta": update.rating_change},
        )
    else:
        messages.success(request, _("Сотрудничество завершено."))
    return redirect("collaborations:collaboration_list")


@login_required
def mark_collaboration_failed(request, pk: int):
    collaboration = get_object_or_404(
        Collaboration,
        pk=pk,
        author=request.user,
    )
    update = CollaborationStatusUpdate.mark_failed(collaboration)
    if update.rating_change is not None:
        messages.warning(
            request,
            _("Сотрудничество отмечено как просроченное. Рейтинг блогера изменился на %(delta)s баллов."),
            extra_tags="warning",
        )
    else:
        messages.warning(request, _("Сотрудничество отмечено как просроченное."), extra_tags="warning")
    return redirect("collaborations:collaboration_list")