from django import template
from django.urls import reverse
from django.utils.html import format_html


register = template.Library()


@register.simple_tag
def profile_link(user, text=None, css_class=""):
    if not user:
        return ""
    url = reverse("profile", args=[user.username])
    display_text = text or user.get_full_name() or user.username
    if css_class:
        return format_html('<a class="{}" href="{}">{}</a>', css_class, url, display_text)
    return format_html('<a href="{}">{}</a>', url, display_text)


@register.simple_tag
def profile_url(user):
    if not user:
        return ""
    return reverse("profile", args=[user.username])