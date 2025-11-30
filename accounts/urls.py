from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views
from .forms import EmailAuthenticationForm
from . import webhooks
from .views import yookassa_webhook

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="accounts/login.html",
            authentication_form=EmailAuthenticationForm,
    ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("premium/", views.premium_overview, name="premium_overview"),
    path("premium/checkout/", views.premium_create_payment, name="premium_create_payment"),
    path(
        "api/premium/yookassa/webhook/",
        views.yookassa_webhook,
        name="yookassa_webhook",
    ),
    path("me/print/monthly/", views.profile_monthly_print, name="profile_monthly_print"),
    path("me/print/monthly/pdf/", views.profile_monthly_pdf, name="profile_monthly_pdf"),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset_form.html",
            email_template_name="accounts/password_reset_email.txt",
            subject_template_name="accounts/password_reset_subject.txt",
            success_url=reverse_lazy("password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    path("me/", views.profile, name="my_profile"),
    path("u/<str:username>/", views.profile, name="profile"),
    path("me/edit/", views.profile_edit, name="profile_edit"),
    path("api/reward-ads/config/", views.reward_ad_config, name="reward_ad_config"),
    path("api/reward-ads/claim/", views.claim_reward_ad_api, name="reward_ad_claim"),
    path('webhooks/yookassa/', webhooks.yookassa_webhook, name='yookassa-webhook'),
]