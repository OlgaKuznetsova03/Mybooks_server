from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.messages.api import MessageFailure

from .models import (
    DAILY_LOGIN_REWARD_COINS,
    WELCOME_BONUS_COINS,
    CoinTransaction,
    Profile,
)

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        profile = Profile.objects.create(user=instance)
        profile.credit_coins(
            WELCOME_BONUS_COINS,
            transaction_type=CoinTransaction.Type.SIGNUP_BONUS,
            description="Приветственный бонус за регистрацию",
        )


@receiver(user_logged_in)
def reward_daily_login(sender, user, request, **kwargs):
    try:
        profile = user.profile
    except Profile.DoesNotExist:
        return

    tx = profile.grant_daily_login_reward()
    if tx and request is not None:
        try:
            messages.success(
                request,
                f"Вы получили {DAILY_LOGIN_REWARD_COINS} монет за ежедневный вход!",
            )
        except MessageFailure:
            pass
