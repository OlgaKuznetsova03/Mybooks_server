from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView
from django.views.generic.edit import CreateView, FormView, UpdateView

from .forms import (
    AuthorOfferForm,
    AuthorOfferResponseForm,
    AuthorOfferResponseAcceptForm,
    AuthorOfferResponseCommentForm,
    BloggerGiveawayForm,
    BloggerInvitationForm,
    CommunityBookClubForm,
    BloggerPlatformPresenceFormSet,
    BloggerRequestForm,
    BloggerRequestResponseAcceptForm,
    BloggerRequestResponseCommentForm,
    BloggerRequestResponseForm,
    CollaborationApprovalForm,
    CollaborationReviewForm,
    CollaborationMessageForm,
)
from .models import (
    AuthorOffer,
    AuthorOfferResponse,
    BloggerRequest,
    BloggerRequestResponse,
    BloggerRequestResponseComment,
    BloggerGiveaway,
    BloggerInvitation,
    CommunityBookClub,
    Collaboration,
    CollaborationStatusUpdate,
    CollaborationMessage,
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


def _user_can_respond_to_offer(offer: AuthorOffer, user: User) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if offer.author_id == getattr(user, "id", None):
        return False
    if offer.allow_regular_users:
        return True
    return _user_is_blogger(user)


def _get_offer_response_context(
    offer: AuthorOffer, user: User, form: AuthorOfferResponseForm | None = None
) -> dict:
    if not user.is_authenticated:
        return {}

    existing_response = AuthorOfferResponse.objects.filter(
        offer=offer,
        respondent=user,
    ).first()
    response_form = form or AuthorOfferResponseForm(instance=existing_response)
    can_respond = _user_can_respond_to_offer(offer, user)
    conversation_url = None
    if existing_response:
        conversation_url = reverse(
            "collaborations:offer_response_detail", args=[existing_response.pk]
        )
    return {
        "existing_response": existing_response,
        "response_form": response_form,
        "can_respond": can_respond,
        "response_conversation_url": conversation_url,
    }


def _get_request_response_context(
    request_obj: BloggerRequest,
    user: User,
    form: BloggerRequestResponseForm | None = None,
) -> dict:
    if not user.is_authenticated:
        return {}

    existing_response = (
        BloggerRequestResponse.objects.select_related("book")
        .filter(request=request_obj, responder=user)
        .first()
    )
    response_form = form or BloggerRequestResponseForm(
        instance=existing_response,
        responder=user,
        request_obj=request_obj,
    )
    can_respond = request_obj.blogger_id != user.id and (
        (request_obj.is_for_authors and _user_is_author(user))
        or (request_obj.is_for_bloggers and _user_is_blogger(user))
    )
    conversation_url = None
    if existing_response:
        conversation_url = reverse(
            "collaborations:blogger_request_response_detail",
            args=[existing_response.pk],
        )
    return {
        "existing_response": existing_response,
        "response_form": response_form,
        "can_respond": can_respond,
        "response_conversation_url": conversation_url,
    }


class BloggerCommunityView(View):
    template_name = "collaborations/blogger_community.html"

    def get(self, request):
        active_tab = request.GET.get("tab", "invitations")
        return self._render(request, active_tab=self._sanitize_tab(active_tab))

    def post(self, request):
        section = request.POST.get("section", "invitations")
        active_tab = self._sanitize_tab(section)
        if active_tab == "clubs":
            if not request.user.is_authenticated:
                messages.error(
                    request,
                    _("Войдите, чтобы поделиться информацией о книжном клубе."),
                )
                login_url = f"{reverse('login')}?next={request.path}"
                return redirect(login_url)

            club_form = CommunityBookClubForm(request.POST)
            if club_form.is_valid():
                club = club_form.save(commit=False)
                club.submitted_by = request.user
                club.save()
                messages.success(
                    request,
                    _("Клуб добавлен! Спасибо, что делитесь активностями сообществ."),
                )
                redirect_url = f"{request.path}?tab=clubs"
                return redirect(redirect_url)
            return self._render(
                request,
                club_form=club_form,
                active_tab="clubs",
            )
        
        if not request.user.is_authenticated:
            messages.error(
                request,
                _("Войдите в аккаунт блогера, чтобы добавлять приглашения и розыгрыши."),
            )
            login_url = f"{reverse('login')}?next={request.path}"
            return redirect(login_url)

        if not _user_is_blogger(request.user):
            messages.error(
                request,
                _("Добавлять информацию могут только блогеры."),
            )
            return self._render(request, active_tab=active_tab)

        if active_tab == "giveaways":
            giveaway_form = BloggerGiveawayForm(request.POST)
            invitation_form = BloggerInvitationForm()
            if giveaway_form.is_valid():
                giveaway = giveaway_form.save(commit=False)
                giveaway.blogger = request.user
                giveaway.save()
                messages.success(
                    request,
                    _("Розыгрыш опубликован! Не забудьте обновить информацию после его завершения."),
                )
                redirect_url = f"{request.path}?tab=giveaways"
                return redirect(redirect_url)
            return self._render(
                request,
                invitation_form=invitation_form,
                giveaway_form=giveaway_form,
                active_tab="giveaways",
            )

        invitation_form = BloggerInvitationForm(request.POST)
        giveaway_form = BloggerGiveawayForm()
        if invitation_form.is_valid():
            invitation = invitation_form.save(commit=False)
            invitation.blogger = request.user
            invitation.save()
            messages.success(
                request,
                _("Приглашение опубликовано!"),
            )
            return redirect(request.path)
        return self._render(
            request,
            invitation_form=invitation_form,
            giveaway_form=giveaway_form,
            active_tab="invitations",
        )

    def _render(
        self,
        request,
        *,
        invitation_form: BloggerInvitationForm | None = None,
        giveaway_form: BloggerGiveawayForm | None = None,
        club_form: CommunityBookClubForm | None = None,
        active_tab: str = "invitations",
    ):
        invitations = (
            BloggerInvitation.objects.select_related("blogger")
            .order_by("-created_at")
        )
        today = timezone.now().date()
        giveaways = (
            BloggerGiveaway.objects.select_related("blogger")
            .filter(is_active=True)
            .filter(Q(deadline__isnull=True) | Q(deadline__gte=today))
            .order_by("-created_at")
        )
        book_clubs = (
            CommunityBookClub.objects.select_related("submitted_by")
            .order_by("-created_at")
        )
        can_share_blogger_content = (
            request.user.is_authenticated and _user_is_blogger(request.user)
        )
        can_share_book_clubs = request.user.is_authenticated
        context = {
            "invitations": invitations,
            "giveaways": giveaways,
            "book_clubs": book_clubs,
            "invitation_form": invitation_form or BloggerInvitationForm(),
            "giveaway_form": giveaway_form or BloggerGiveawayForm(),
            "club_form": club_form or CommunityBookClubForm(),
            "active_tab": active_tab,
            "can_share_blogger_content": can_share_blogger_content,
            "can_share_book_clubs": can_share_book_clubs,
        }
        return render(request, self.template_name, context)

    @staticmethod
    def _sanitize_tab(tab: str) -> str:
        if tab not in {"invitations", "giveaways", "clubs"}:
            return "invitations"
        return tab


class CommunityBookClubDetailView(DetailView):
    model = CommunityBookClub
    template_name = "collaborations/community_book_club_detail.html"
    context_object_name = "club"

    def get_queryset(self):
        return super().get_queryset().select_related("submitted_by")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["community_url"] = f"{reverse('collaborations:blogger_community')}?tab=clubs"
        return context


class OfferListView(ListView):
    model = AuthorOffer
    template_name = "collaborations/offer_list.html"
    context_object_name = "offers"
    paginate_by = 10

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("author", "book")
            .prefetch_related("expected_platforms")
        )
        q = self.request.GET.get("q")
        if q:
            queryset = queryset.filter(Q(title__icontains=q) | Q(synopsis__icontains=q))

        audience = self.request.GET.get("audience", "")
        if audience == "bloggers_only":
            queryset = queryset.filter(allow_regular_users=False)
        elif audience == "readers_allowed":
            queryset = queryset.filter(allow_regular_users=True)

        return queryset.filter(is_active=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        is_author = user.is_authenticated and _user_is_author(user)
        is_blogger = user.is_authenticated and _user_is_blogger(user)
        if user.is_authenticated and (is_author or is_blogger):
            context["show_response_inbox"] = True
            pending_count = AuthorOfferResponse.objects.filter(
                offer__author=user,
                status=AuthorOfferResponse.Status.PENDING,
            ).count()
            context["pending_offer_responses_count"] = pending_count
        else:
            context["show_response_inbox"] = False
            context["pending_offer_responses_count"] = 0

        context.update(
            {
                "user_is_author": is_author,
                "user_is_blogger": is_blogger,
                "blogger_request_list_url": reverse(
                    "collaborations:blogger_request_list"
                ),
            }
        )
        if is_blogger:
            context["blogger_request_create_url"] = reverse(
                "collaborations:blogger_request_create"
            )

        context["active_audience_filter"] = (
            self.request.GET.get("audience")
            if self.request.GET.get("audience") in {"", "bloggers_only", "readers_allowed"}
            else ""
        )
        context["audience_filter_options"] = [
            {"value": "", "label": _("Все предложения")},
            {"value": "bloggers_only", "label": _("Только для блогеров")},
            {
                "value": "readers_allowed",
                "label": _("Открытые для блогеров и читателей"),
            },
        ]
        return context
    

class OfferDetailView(DetailView):
    model = AuthorOffer
    template_name = "collaborations/offer_detail.html"
    context_object_name = "offer"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("author", "book")
            .prefetch_related("expected_platforms")
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            _get_offer_response_context(self.object, self.request.user)
        )
        return context


class OfferCreateView(LoginRequiredMixin, CreateView):
    model = AuthorOffer
    form_class = AuthorOfferForm
    template_name = "collaborations/offer_form.html"
    success_url = reverse_lazy("collaborations:offer_list")

    def dispatch(self, request, *args, **kwargs):
        if not (_user_is_author(request.user) or _user_is_blogger(request.user)):
            messages.error(
                request,
                _("Создавать предложения могут только авторы и блогеры."),
            )
            return redirect("collaborations:offer_list")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.author = self.request.user
        messages.success(self.request, _("Предложение опубликовано."))
        return super().form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["author"] = self.request.user
        return kwargs
    
def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("is_editing", False)
        return context


class OfferUpdateView(LoginRequiredMixin, UpdateView):
    model = AuthorOffer
    form_class = AuthorOfferForm
    template_name = "collaborations/offer_form.html"

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.has_perm("collaborations.change_authoroffer"):
            return queryset
        return queryset.filter(author=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["author"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, _("Предложение обновлено."))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("collaborations:offer_detail", args=[self.object.pk])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("is_editing", True)
        return context
    

class OfferRespondView(LoginRequiredMixin, FormView):
    form_class = AuthorOfferResponseForm

    def dispatch(self, request, *args, **kwargs):
        self.offer = get_object_or_404(AuthorOffer, pk=kwargs["pk"])
        if self.offer.author_id == request.user.id:
            messages.error(request, _("Вы не можете откликнуться на собственное предложение."))
            return redirect("collaborations:offer_detail", pk=self.offer.pk)
        if not _user_can_respond_to_offer(self.offer, request.user):
            if not self.offer.allow_regular_users and not _user_is_blogger(request.user):
                messages.error(request, _("Только блогеры могут откликаться на это предложение."))
            else:
                messages.error(request, _("Вы не можете откликнуться на это предложение."))
            return redirect("collaborations:offer_detail", pk=self.offer.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response, created = AuthorOfferResponse.objects.get_or_create(
            offer=self.offer,
            respondent=self.request.user,
            defaults={
                "message": form.cleaned_data.get("message", ""),
                "platform_links": form.cleaned_data.get("platform_links", ""),
            },
        )
        if not created:
            response.message = form.cleaned_data.get("message", "")
            response.platform_links = form.cleaned_data.get("platform_links", "")
            response.status = AuthorOfferResponse.Status.PENDING
            response.save(
                update_fields=["message", "platform_links", "status", "updated_at"]
            )
            messages.info(self.request, _("Отклик обновлён."))
        else:
            messages.success(self.request, _("Отклик отправлен автору."))
        response.register_activity(self.request.user)
        return redirect("collaborations:offer_detail", pk=self.offer.pk)

    def form_invalid(self, form):
        context = {"offer": self.offer, "object": self.offer}
        context.update(
            _get_offer_response_context(self.offer, self.request.user, form)
        )
        return render(
            self.request,
            "collaborations/offer_detail.html",
            context,
            status=400,
        )

class OfferResponseListView(LoginRequiredMixin, ListView):
    model = AuthorOfferResponse
    template_name = "collaborations/offer_response_list.html"
    context_object_name = "responses"
    paginate_by = 10

    def dispatch(self, request, *args, **kwargs):
        if not (_user_is_author(request.user) or _user_is_blogger(request.user)):
            messages.error(
                request,
                _("Только авторы и блогеры могут просматривать отклики на свои предложения."),
            )
            return redirect("collaborations:offer_list")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("offer", "respondent")
            .filter(offer__author=self.request.user)
        )
        status = self.request.GET.get("status")
        if status in dict(AuthorOfferResponse.Status.choices):
            queryset = queryset.filter(status=status)
        return queryset.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = AuthorOfferResponse.objects.filter(offer__author=self.request.user)
        status_counts = {
            item["status"]: item["total"]
            for item in qs.values("status").annotate(total=Count("id"))
        }
        context.update(
            {
                "active_status": self.request.GET.get("status", ""),
                "status_options": [
                    {
                        "value": value,
                        "label": label,
                        "count": status_counts.get(value, 0),
                    }
                    for value, label in AuthorOfferResponse.Status.choices
                ],
                "total_responses": qs.count(),
            }
        )
        return context


class OfferResponseDetailView(LoginRequiredMixin, View):
    template_name = "collaborations/offer_response_detail.html"

    def dispatch(self, request, *args, **kwargs):
        self.response = get_object_or_404(
            AuthorOfferResponse.objects.select_related(
                "offer", "offer__author", "respondent"
            ),
            pk=kwargs["pk"],
        )
        if not self.response.is_participant(request.user):
            messages.error(request, _("Вы не участвуете в этом отклике."))
            return redirect("collaborations:offer_list")
        return super().dispatch(request, *args, **kwargs)

    def get_back_url(self) -> str:
        if self.request.user.id == self.response.offer.author_id:
            return reverse("collaborations:offer_responses")
        return reverse("collaborations:offer_detail", args=[self.response.offer_id])

    def get_context_data(self, form: AuthorOfferResponseCommentForm | None = None) -> dict:
        can_comment = self.response.allows_discussion()
        context = {
            "response": self.response,
            "offer": self.response.offer,
            "comments": self.response.comments.select_related("author").order_by(
                "created_at"
            ),
            "can_comment": can_comment,
            "is_author": self.request.user.id == self.response.offer.author_id,
            "back_url": self.get_back_url(),
        }
        if (
            context["is_author"]
            and self.response.status == AuthorOfferResponse.Status.PENDING
        ):
            context["accept_url"] = reverse(
                "collaborations:offer_response_accept", args=[self.response.pk]
            )
            context["decline_url"] = reverse(
                "collaborations:offer_response_decline", args=[self.response.pk]
            )
        if can_comment:
            context["form"] = form or AuthorOfferResponseCommentForm()
        return context

    def get(self, request, *args, **kwargs):
        self.response.mark_read(request.user)
        return render(
            request,
            self.template_name,
            self.get_context_data(),
        )

    def post(self, request, *args, **kwargs):
        self.response.mark_read(request.user)
        if not self.response.allows_discussion():
            messages.error(
                request,
                _("Обсуждение закрыто: отклик уже подтверждён или отклонён."),
            )
            return redirect(
                "collaborations:offer_response_detail", pk=self.response.pk
            )

        form = AuthorOfferResponseCommentForm(request.POST)
        if form.is_valid():
            comment = self.response.comments.create(
                author=request.user,
                text=form.cleaned_data["text"],
            )
            self.response.register_activity(request.user, comment.created_at)
            messages.success(request, _("Комментарий отправлен."))
            return redirect(
                "collaborations:offer_response_detail", pk=self.response.pk
            )

        return render(
            request,
            self.template_name,
            self.get_context_data(form=form),
            status=400,
        )


class OfferResponseAcceptView(LoginRequiredMixin, FormView):
    form_class = AuthorOfferResponseAcceptForm
    template_name = "collaborations/offer_response_accept.html"

    def dispatch(self, request, *args, **kwargs):
        self.response = get_object_or_404(
            AuthorOfferResponse.objects.select_related("offer", "respondent"),
            pk=kwargs["pk"],
        )
        if self.response.offer.author_id != request.user.id:
            messages.error(request, _("Нельзя управлять откликом другого автора."))
            return redirect("collaborations:offer_list")
        if self.response.status == AuthorOfferResponse.Status.WITHDRAWN:
            messages.error(request, _("Этот отклик был отозван."))
            return redirect("collaborations:offer_responses")
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        collaboration = Collaboration.objects.filter(
            offer=self.response.offer,
            partner=self.response.respondent,
        ).first()
        if collaboration:
            initial["deadline"] = collaboration.deadline
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["response"] = self.response
        context["platform_links"] = [
            link for link in self.response.platform_links.splitlines() if link.strip()
        ]
        context["comments"] = self.response.comments.select_related("author").order_by(
            "created_at"
        )
        return context

    def form_valid(self, form):
        deadline = form.cleaned_data["deadline"]
        response = self.response
        collaboration, _created = Collaboration.objects.get_or_create(
            offer=response.offer,
            partner=response.respondent,
            defaults={
                "author": response.offer.author,
                "deadline": deadline,
                "status": Collaboration.Status.NEGOTIATION,
                "author_approved": True,
                "partner_approved": False,
            },
        )
        collaboration.deadline = deadline
        collaboration.status = Collaboration.Status.NEGOTIATION
        collaboration.author_confirmed = False
        collaboration.partner_confirmed = False
        collaboration.author_approved = True
        collaboration.partner_approved = False
        collaboration.review_links = ""
        collaboration.completed_at = None
        collaboration.updated_at = timezone.now()
        collaboration.save(
            update_fields=[
                "deadline",
                "status",
                "author_confirmed",
                "partner_confirmed",
                "author_approved",
                "partner_approved",
                "review_links",
                "completed_at",
                "updated_at",
            ]
        )

        if response.status != AuthorOfferResponse.Status.ACCEPTED:
            response.move_discussion_to_collaboration(collaboration)
            response.status = AuthorOfferResponse.Status.ACCEPTED
            response.save(update_fields=["status", "updated_at"])

        response.register_activity(self.request.user)
        collaboration.register_activity(self.request.user)
        messages.success(
            self.request,
            _(
                "Отклик принят. Запрос отправлен партнёру, ожидаем подтверждения и согласия с дедлайном."
            ),
        )
        return redirect("collaborations:offer_responses")


class OfferResponseDeclineView(LoginRequiredMixin, View):
    def post(self, request, pk: int):
        response = get_object_or_404(
            AuthorOfferResponse.objects.select_related("offer", "respondent"),
            pk=pk,
        )
        if response.offer.author_id != request.user.id:
            messages.error(request, _("Нельзя управлять откликом другого автора."))
            return redirect("collaborations:offer_list")

        if response.status != AuthorOfferResponse.Status.DECLINED:
            response.status = AuthorOfferResponse.Status.DECLINED
            response.save(update_fields=["status", "updated_at"])

        collaboration = Collaboration.objects.filter(
            offer=response.offer,
            partner=response.respondent,
        ).first()
        if collaboration and collaboration.status not in {
            Collaboration.Status.CANCELLED,
            Collaboration.Status.COMPLETED,
        }:
            collaboration.status = Collaboration.Status.CANCELLED
            collaboration.author_confirmed = False
            collaboration.partner_confirmed = False
            collaboration.author_approved = False
            collaboration.partner_approved = False
            collaboration.updated_at = timezone.now()
            collaboration.save(
                update_fields=[
                    "status",
                    "author_confirmed",
                    "partner_confirmed",
                    "author_approved",
                    "partner_approved",
                    "updated_at",
                ]
            )
            collaboration.register_activity(request.user)

        response.register_activity(request.user)
        messages.info(request, _("Отклик отклонён."))
        return redirect("collaborations:offer_responses")


class OfferResponseWithdrawView(LoginRequiredMixin, View):
    """Позволяет блогеру или читателю отозвать собственный отклик."""

    def post(self, request, pk: int):
        response = get_object_or_404(
            AuthorOfferResponse.objects.select_related("offer", "respondent"),
            pk=pk,
            respondent=request.user,
        )

        if response.status != AuthorOfferResponse.Status.PENDING:
            messages.error(
                request,
                _("Нельзя отозвать отклик: автор уже дал ответ."),
            )
            return redirect("collaborations:collaboration_list")

        response.status = AuthorOfferResponse.Status.WITHDRAWN
        response.save(update_fields=["status", "updated_at"])
        response.register_activity(request.user)
        messages.success(request, _("Вы отозвали отклик."))
        return redirect("collaborations:collaboration_list")


class BloggerRequestResponseListView(LoginRequiredMixin, ListView):
    model = BloggerRequestResponse
    template_name = "collaborations/blogger_request_response_list.html"
    context_object_name = "responses"
    paginate_by = 10

    def dispatch(self, request, *args, **kwargs):
        if not _user_is_blogger(request.user):
            messages.error(
                request,
                _("Только блогеры могут просматривать отклики на свои предложения."),
            )
            return redirect("collaborations:blogger_request_list")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("request", "responder", "book")
            .filter(request__blogger=self.request.user)
            .order_by("-created_at")
        )
        status = self.request.GET.get("status")
        if status in dict(BloggerRequestResponse.Status.choices):
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = BloggerRequestResponse.objects.filter(request__blogger=self.request.user)
        status_counts = {
            item["status"]: item["total"]
            for item in qs.values("status").annotate(total=Count("id"))
        }
        unread_ids = set(
            BloggerRequestResponse.objects.unread_for(self.request.user).values_list(
                "id", flat=True
            )
        )
        context.update(
            {
                "active_status": self.request.GET.get("status", ""),
                "status_options": [
                    {
                        "value": value,
                        "label": label,
                        "count": status_counts.get(value, 0),
                    }
                    for value, label in BloggerRequestResponse.Status.choices
                ],
                "total_responses": qs.count(),
                "unread_response_ids": unread_ids,
            }
        )
        return context


class BloggerRequestResponseDetailView(LoginRequiredMixin, View):
    template_name = "collaborations/blogger_request_response_detail.html"

    def dispatch(self, request, *args, **kwargs):
        self.response = get_object_or_404(
            BloggerRequestResponse.objects.select_related(
                "request", "request__blogger", "responder", "book"
            ),
            pk=kwargs["pk"],
        )
        if not self.response.is_participant(request.user):
            messages.error(request, _("Вы не участвуете в этом отклике."))
            return redirect("collaborations:blogger_request_list")
        return super().dispatch(request, *args, **kwargs)

    def get_back_url(self) -> str:
        if self.request.user.id == self.response.request.blogger_id:
            return reverse("collaborations:blogger_request_responses")
        return reverse(
            "collaborations:blogger_request_detail", args=[self.response.request_id]
        )

    def get_context_data(
        self, form: BloggerRequestResponseCommentForm | None = None
    ) -> dict:
        can_comment = self.response.allows_discussion()
        context = {
            "response": self.response,
            "request_obj": self.response.request,
            "comments": self.response.comments.select_related("author").order_by(
                "created_at"
            ),
            "can_comment": can_comment,
            "is_blogger": self.request.user.id == self.response.request.blogger_id,
            "is_responder": self.request.user.id == self.response.responder_id,
            "back_url": self.get_back_url(),
        }
        if can_comment:
            context["form"] = form or BloggerRequestResponseCommentForm()
        return context

    def get(self, request, *args, **kwargs):
        self.response.mark_read(request.user)
        return render(
            request,
            self.template_name,
            self.get_context_data(),
        )

    def post(self, request, *args, **kwargs):
        if not self.response.allows_discussion():
            messages.error(
                request,
                _("Обсуждение закрыто: отклик уже подтверждён или отклонён."),
            )
            return redirect(
                "collaborations:blogger_request_response_detail", pk=self.response.pk
            )

        form = BloggerRequestResponseCommentForm(request.POST)
        if form.is_valid():
            BloggerRequestResponseComment.objects.create(
                response=self.response,
                author=request.user,
                text=form.cleaned_data["text"],
            )
            self.response.register_activity(request.user)
            messages.success(request, _("Комментарий отправлен."))
            return redirect(
                "collaborations:blogger_request_response_detail", pk=self.response.pk
            )

        return render(
            request,
            self.template_name,
            self.get_context_data(form=form),
            status=400,
        )


class BloggerRequestResponseAcceptView(LoginRequiredMixin, FormView):
    form_class = BloggerRequestResponseAcceptForm
    template_name = "collaborations/blogger_request_response_accept.html"

    def dispatch(self, request, *args, **kwargs):
        self.response = get_object_or_404(
            BloggerRequestResponse.objects.select_related("request", "responder", "book"),
            pk=kwargs["pk"],
        )
        if self.response.request.blogger_id != request.user.id:
            messages.error(request, _("Нельзя управлять откликом другого блогера."))
            return redirect("collaborations:blogger_request_list")
        if self.response.status == BloggerRequestResponse.Status.WITHDRAWN:
            messages.error(request, _("Этот отклик был отозван."))
            return redirect("collaborations:blogger_request_responses")
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        collaboration = Collaboration.objects.filter(
            request=self.response.request,
            author=self.response.responder,
        ).first()
        if collaboration:
            initial["deadline"] = collaboration.deadline
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["response"] = self.response
        context["comments"] = self.response.comments.select_related("author").order_by(
            "created_at"
        )
        return context

    def form_valid(self, form):
        deadline = form.cleaned_data["deadline"]
        response = self.response
        collaboration, _created = Collaboration.objects.get_or_create(
            request=response.request,
            author=response.responder,
            defaults={
                "partner": response.request.blogger,
                "deadline": deadline,
                "status": Collaboration.Status.NEGOTIATION,
                "partner_approved": True,
                "author_approved": False,
            },
        )
        collaboration.partner = response.request.blogger
        collaboration.deadline = deadline
        collaboration.status = Collaboration.Status.NEGOTIATION
        collaboration.author_confirmed = False
        collaboration.partner_confirmed = False
        collaboration.partner_approved = True
        collaboration.author_approved = False
        collaboration.review_links = ""
        collaboration.completed_at = None
        collaboration.updated_at = timezone.now()
        collaboration.save(
            update_fields=[
                "partner",
                "deadline",
                "status",
                "author_confirmed",
                "partner_confirmed",
                "author_approved",
                "partner_approved",
                "review_links",
                "completed_at",
                "updated_at",
            ]
        )

        if response.status != BloggerRequestResponse.Status.ACCEPTED:
            response.status = BloggerRequestResponse.Status.ACCEPTED
            response.save(update_fields=["status", "updated_at"])

        response.move_discussion_to_collaboration(collaboration)
        response.register_activity(self.request.user)

        collaboration.register_activity(self.request.user)
        messages.success(
            self.request,
            _(
                "Отклик принят. Мы попросили автора подтвердить участие и согласовать дедлайн."
            ),
        )
        return redirect("collaborations:blogger_request_responses")


class BloggerRequestResponseDeclineView(LoginRequiredMixin, View):
    def post(self, request, pk: int):
        response = get_object_or_404(
            BloggerRequestResponse.objects.select_related("request", "responder"),
            pk=pk,
        )
        if response.request.blogger_id != request.user.id:
            messages.error(request, _("Нельзя управлять откликом другого блогера."))
            return redirect("collaborations:blogger_request_list")

        if response.status != BloggerRequestResponse.Status.DECLINED:
            response.status = BloggerRequestResponse.Status.DECLINED
            response.save(update_fields=["status", "updated_at"])
            BloggerRequestResponse.objects.select_related("request", "responder"),

        collaboration = Collaboration.objects.filter(
            request=response.request,
            author=response.responder,
        ).first()
        if collaboration and collaboration.status not in {
            Collaboration.Status.CANCELLED,
            Collaboration.Status.COMPLETED,
        }:
            collaboration.status = Collaboration.Status.CANCELLED
            collaboration.author_confirmed = False
            collaboration.partner_confirmed = False
            collaboration.author_approved = False
            collaboration.partner_approved = False
            collaboration.updated_at = timezone.now()
            collaboration.save(
                update_fields=[
                    "status",
                    "author_confirmed",
                    "partner_confirmed",
                    "author_approved",
                    "partner_approved",
                    "updated_at",
                ]
            )
            collaboration.register_activity(request.user)

        # BloggerRequestResponse does not track threaded discussions, so we update collaboration only.
        messages.info(request, _("Отклик отклонён."))
        return redirect("collaborations:blogger_request_responses")


class BloggerRequestResponseWithdrawView(LoginRequiredMixin, View):
    """Позволяет автору отозвать отклик на заявку блогера."""

    def post(self, request, pk: int):
        response = get_object_or_404(
            BloggerRequestResponse.objects.select_related("request", "responder"),
            pk=pk,
            responder=request.user,
        )

        if response.status != BloggerRequestResponse.Status.PENDING:
            messages.error(
                request,
                _("Нельзя отозвать отклик: блогер уже ответил."),
            )
            return redirect("collaborations:collaboration_list")

        response.status = BloggerRequestResponse.Status.WITHDRAWN
        response.save(update_fields=["status", "updated_at"])
        response.register_activity(request.user)
        messages.success(request, _("Вы отозвали отклик."))
        return redirect("collaborations:collaboration_list")


class CollaborationApprovalView(LoginRequiredMixin, FormView):
    form_class = CollaborationApprovalForm
    template_name = "collaborations/collaboration_approval.html"

    def dispatch(self, request, *args, **kwargs):
        self.collaboration = get_object_or_404(
            Collaboration.objects.select_related("author", "partner", "offer", "request"),
            pk=kwargs["pk"],
        )
        if not self.collaboration.is_participant(request.user):
            messages.error(
                request,
                _("Только участники могут подтверждать сотрудничество."),
            )
            return redirect("collaborations:collaboration_list")

        self.pending_role = self._get_pending_role(request.user)
        if self.pending_role is None:
            messages.info(
                request,
                _("Подтверждение не требуется или уже выполнено."),
            )
            return redirect("collaborations:collaboration_detail", pk=self.collaboration.pk)
        return super().dispatch(request, *args, **kwargs)

    def _get_pending_role(self, user: User) -> str | None:
        if user.id == self.collaboration.partner_id and self.collaboration.waiting_for_partner_confirmation:
            return "partner"
        if user.id == self.collaboration.author_id and self.collaboration.waiting_for_author_confirmation:
            return "author"
        return None

    def get_initial(self):
        initial = super().get_initial()
        initial["deadline"] = self.collaboration.deadline
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "collaboration": self.collaboration,
                "pending_role": self.pending_role,
            }
        )
        return context

    def form_valid(self, form):
        deadline = form.cleaned_data["deadline"]
        collaboration = self.collaboration
        collaboration.deadline = deadline
        collaboration.updated_at = timezone.now()
        update_fields = ["deadline", "updated_at"]

        if self.pending_role == "partner":
            collaboration.partner_approved = True
            update_fields.append("partner_approved")
        elif self.pending_role == "author":
            collaboration.author_approved = True
            update_fields.append("author_approved")

        collaboration.save(update_fields=update_fields)
        collaboration.register_activity(self.request.user)

        if collaboration.author_approved and collaboration.partner_approved:
            messages.success(
                self.request,
                _("Сотрудничество подтверждено обеими сторонами. Можно приступать к работе."),
            )
        else:
            messages.success(
                self.request,
                _("Подтверждение сохранено. Сообщим второй стороне о вашем решении."),
            )
        return redirect("collaborations:collaboration_detail", pk=collaboration.pk)


class CollaborationNotificationsView(LoginRequiredMixin, TemplateView):
    template_name = "collaborations/notifications_overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        pending_offer_responses = AuthorOfferResponse.objects.filter(
            offer__author=user,
            status=AuthorOfferResponse.Status.PENDING,
        ).select_related("offer", "respondent")

        pending_blogger_request_responses = BloggerRequestResponse.objects.filter(
            request__blogger=user,
            status=BloggerRequestResponse.Status.PENDING,
        ).select_related("request", "responder", "book")

        pending_partner_collaborations = Collaboration.objects.filter(
            partner=user,
            author_approved=True,
            partner_approved=False,
            status__in=[Collaboration.Status.NEGOTIATION, Collaboration.Status.ACTIVE],
        ).select_related("author", "partner", "offer", "request")

        pending_author_collaborations = Collaboration.objects.filter(
            author=user,
            partner_approved=True,
            author_approved=False,
            status__in=[Collaboration.Status.NEGOTIATION, Collaboration.Status.ACTIVE],
        ).select_related("author", "partner", "offer", "request")

        unread_offer_threads = (
            AuthorOfferResponse.objects.unread_for(user)
            .select_related("offer", "offer__author", "respondent")
            .order_by("-last_activity_at")
        )

        unread_blogger_request_threads = (
            BloggerRequestResponse.objects.unread_for(user)
            .select_related("request", "request__blogger", "responder", "book")
            .order_by("-last_activity_at")
        )

        unread_collaborations = (
            Collaboration.objects.unread_for(user)
            .select_related("author", "partner", "offer", "request")
            .order_by("-last_activity_at")
        )

        context.update(
            {
                "pending_offer_responses": pending_offer_responses,
                "pending_blogger_request_responses": pending_blogger_request_responses,
                "pending_partner_collaborations": pending_partner_collaborations,
                "pending_author_collaborations": pending_author_collaborations,
                "unread_offer_threads": unread_offer_threads,
                "unread_blogger_request_threads": unread_blogger_request_threads,
                "unread_collaborations": unread_collaborations,
            }
        )
        return context


class BloggerRequestListView(ListView):
    model = BloggerRequest
    template_name = "collaborations/blogger_request_list.html"
    context_object_name = "requests"
    paginate_by = 10

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("blogger", "blogger__profile")
            .prefetch_related("preferred_genres", "review_formats", "platforms")
        )
        q = self.request.GET.get("q")
        if q:
            queryset = queryset.filter(Q(title__icontains=q) | Q(additional_info__icontains=q))
        return queryset.filter(is_active=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        is_blogger = user.is_authenticated and _user_is_blogger(user)
        is_author = user.is_authenticated and _user_is_author(user)
        if is_blogger:
            context["show_response_inbox"] = True
            pending_count = BloggerRequestResponse.objects.filter(
                request__blogger=user,
                status=BloggerRequestResponse.Status.PENDING,
            ).count()
            context["pending_request_responses_count"] = pending_count
        else:
            context["show_response_inbox"] = False
            context["pending_request_responses_count"] = 0
        context.update(
            {
                "user_is_author": is_author,
                "user_is_blogger": is_blogger,
                "offer_list_url": reverse("collaborations:offer_list"),
            }
        )
        if is_author or is_blogger:
            context["offer_create_url"] = reverse("collaborations:offer_create")
        return context


class BloggerRequestDetailView(DetailView):
    model = BloggerRequest
    template_name = "collaborations/blogger_request_detail.html"
    context_object_name = "request_obj"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            _get_request_response_context(
                self.object, self.request.user
            )
        )
        return context


class BloggerRequestCreateView(LoginRequiredMixin, View):
    template_name = "collaborations/blogger_request_form.html"
    page_title = _("Новая заявка блогера")
    intro_text = _(
        "Заполните информацию о себе и площадках, чтобы авторы могли предложить сотрудничество."
    )
    submit_label = _("Опубликовать")
    is_edit = False

    def dispatch(self, request, *args, **kwargs):
        if not _user_is_blogger(request.user):
            messages.error(request, _("Только блогеры могут создавать такие заявки."))
            return redirect("collaborations:blogger_request_list")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, form, formset):
        return {
            "form": form,
            "formset": formset,
            "page_title": self.page_title,
            "intro_text": self.intro_text,
            "submit_label": self.submit_label,
            "is_edit": self.is_edit,
            "cancel_url": reverse("collaborations:blogger_request_list"),
        }
    
    def get(self, request):
        form = BloggerRequestForm()
        formset = BloggerPlatformPresenceFormSet()
        return render(request, self.template_name, self.get_context_data(form, formset))

    def post(self, request):
        form = BloggerRequestForm(request.POST)
        formset = BloggerPlatformPresenceFormSet(request.POST)
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
        return render(request, self.template_name, self.get_context_data(form, formset))


class BloggerRequestUpdateView(LoginRequiredMixin, View):
    template_name = "collaborations/blogger_request_form.html"
    page_title = _("Редактирование заявки блогера")
    intro_text = _(
        "Обновите описание и площадки, чтобы авторы видели актуальную информацию."
    )
    submit_label = _("Сохранить изменения")
    is_edit = True

    def dispatch(self, request, *args, **kwargs):
        if not _user_is_blogger(request.user):
            messages.error(request, _("Только блогеры могут редактировать свои заявки."))
            return redirect("collaborations:blogger_request_list")
        self.request_obj = get_object_or_404(
            BloggerRequest, pk=kwargs["pk"], blogger=request.user
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, form, formset):
        return {
            "form": form,
            "formset": formset,
            "page_title": self.page_title,
            "intro_text": self.intro_text,
            "submit_label": self.submit_label,
            "is_edit": self.is_edit,
            "request_obj": self.request_obj,
            "cancel_url": reverse(
                "collaborations:blogger_request_detail", args=[self.request_obj.pk]
            ),
        }

    def get(self, request, pk):
        form = BloggerRequestForm(instance=self.request_obj)
        formset = BloggerPlatformPresenceFormSet(instance=self.request_obj)
        return render(request, self.template_name, self.get_context_data(form, formset))

    def post(self, request, pk):
        form = BloggerRequestForm(request.POST, instance=self.request_obj)
        formset = BloggerPlatformPresenceFormSet(
            request.POST, instance=self.request_obj
        )
        if form.is_valid() and formset.is_valid():
            blogger_request = form.save(commit=False)
            blogger_request.blogger = request.user
            blogger_request.save()
            form.save_m2m()
            formset.save()
            messages.success(request, _("Заявка блогера обновлена."))
            return redirect(
                "collaborations:blogger_request_detail", pk=self.request_obj.pk
            )
        return render(request, self.template_name, self.get_context_data(form, formset))

class BloggerRequestRespondView(LoginRequiredMixin, FormView):
    form_class = BloggerRequestResponseForm

    def dispatch(self, request, *args, **kwargs):
        self.request_obj = get_object_or_404(BloggerRequest, pk=kwargs["pk"])
        if self.request_obj.is_for_authors:
            if not _user_is_author(request.user):
                messages.error(request, _("Откликаться на эту заявку могут только авторы."))
                return redirect(
                    "collaborations:blogger_request_detail", pk=self.request_obj.pk
                )
        elif self.request_obj.is_for_bloggers:
            if not _user_is_blogger(request.user):
                messages.error(request, _("Откликаться на эту заявку могут только блогеры."))
                return redirect(
                    "collaborations:blogger_request_detail", pk=self.request_obj.pk
                )
        else:
            if not _user_is_author(request.user):
                messages.error(request, _("Откликаться на заявки могут только авторы."))
                return redirect(
                    "collaborations:blogger_request_detail", pk=self.request_obj.pk
                )
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(
            {
                "responder": self.request.user,
                "request_obj": self.request_obj,
            }
        )
        return kwargs

    def form_valid(self, form):
        responder_type = form.expected_responder_type()
        message = form.cleaned_data.get("message", "")
        book = form.cleaned_data.get("book")
        platform_link = form.cleaned_data.get("platform_link", "")
        response, created = BloggerRequestResponse.objects.get_or_create(
            request=self.request_obj,
            responder=self.request.user,
            defaults={
                "message": message,
                "book": book,
                "platform_link": platform_link,
                "responder_type": responder_type,
            },
        )
        if not created:
            response.message = message
            response.book = book
            response.platform_link = platform_link
            response.responder_type = responder_type
            response.status = BloggerRequestResponse.Status.PENDING
            response.save(
                update_fields=[
                    "message",
                    "book",
                    "platform_link",
                    "responder_type",
                    "status",
                    "updated_at",
                ]
            )
            messages.info(self.request, _("Отклик обновлён."))
        else:
            messages.success(self.request, _("Отклик отправлен блогеру."))
            response.register_activity(self.request.user)
        return redirect("collaborations:blogger_request_detail", pk=self.request_obj.pk)

    def form_invalid(self, form):
        context = {"request_obj": self.request_obj, "object": self.request_obj}
        context.update(
            _get_request_response_context(self.request_obj, self.request.user, form)
        )
        return render(
            self.request,
            "collaborations/blogger_request_detail.html",
            context,
            status=400,
        )


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        offer_responses = (
            AuthorOfferResponse.objects.filter(respondent=user)
            .exclude(status=AuthorOfferResponse.Status.ACCEPTED)
            .select_related("offer", "offer__author")
            .order_by("-created_at")
        )
        blogger_request_responses = (
            BloggerRequestResponse.objects.filter(responder=user)
            .exclude(status=BloggerRequestResponse.Status.ACCEPTED)
            .select_related("request", "request__blogger", "book")
            .order_by("-created_at")
        )
        pending_count = (
            offer_responses.filter(status=AuthorOfferResponse.Status.PENDING).count()
            + blogger_request_responses.filter(
                status=BloggerRequestResponse.Status.PENDING
            ).count()
        )
        context.update(
            {
                "my_offer_responses": offer_responses,
                "my_blogger_request_responses": blogger_request_responses,
                "pending_response_count": pending_count,
            }
        )
        return context


class CollaborationDetailView(LoginRequiredMixin, View):
    template_name = "collaborations/collaboration_detail.html"

    def get_object(self, pk: int) -> Collaboration:
        return get_object_or_404(
            Collaboration.objects.select_related("author", "partner", "offer", "request")
            .prefetch_related("messages__author"),
            pk=pk,
        )

    def _ensure_participant(self, request, collaboration: Collaboration):
        if collaboration.is_participant(request.user):
            return True
        messages.error(
            request,
            _("Переписка доступна только участникам сотрудничества."),
        )
        return False

    def _get_context(self, collaboration: Collaboration, form: CollaborationMessageForm):
        return {
            "collaboration": collaboration,
            "conversation_messages": collaboration.messages.select_related("author"),
            "form": form,
            "can_post": collaboration.allows_discussion(),
            "deadline_passed": collaboration.deadline < timezone.now().date(),
        }

    def get(self, request, pk: int):
        collaboration = self.get_object(pk)
        if not self._ensure_participant(request, collaboration):
            return redirect("collaborations:collaboration_list")
        collaboration.mark_read(request.user)
        form = CollaborationMessageForm()
        return render(
            request,
            self.template_name,
            self._get_context(collaboration, form),
        )

    def post(self, request, pk: int):
        collaboration = self.get_object(pk)
        if not self._ensure_participant(request, collaboration):
            return redirect("collaborations:collaboration_list")

        form = CollaborationMessageForm(request.POST)
        if not collaboration.allows_discussion():
            messages.error(
                request,
                _("Переписка недоступна: сотрудничество завершено или отменено."),
            )
            return redirect("collaborations:collaboration_detail", pk=collaboration.pk)

        if form.is_valid():
            message = CollaborationMessage.objects.create(
                collaboration=collaboration,
                author=request.user,
                text=form.cleaned_data["text"],
            )
            collaboration.register_activity(request.user, message.created_at)
            messages.success(request, _("Сообщение отправлено."))
            return redirect("collaborations:collaboration_detail", pk=collaboration.pk)

        collaboration.mark_read(request.user)
        context = self._get_context(collaboration, form)
        return render(request, self.template_name, context, status=400)


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
            collaboration.register_activity(request.user)
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
    collaboration.register_activity(request.user)

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
    collaboration.register_activity(request.user)
    if update.rating_change is not None:
        messages.warning(
            request,
            _("Сотрудничество отмечено как просроченное. Рейтинг блогера изменился на %(delta)s баллов."),
            extra_tags="warning",
        )
    else:
        messages.warning(request, _("Сотрудничество отмечено как просроченное."), extra_tags="warning")
    return redirect("collaborations:collaboration_list")