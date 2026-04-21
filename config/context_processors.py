from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings


DEFAULT_DESCRIPTION = (
    "Калейдоскоп книг — сайт для читателей: каталог книг, отзывы и рейтинги, "
    "домашняя библиотека, совместные чтения, книжные марафоны, игры и статистика чтения."
)


def static_version(_: object) -> dict[str, str]:
    """Expose the cache-busting static version to templates."""
    return {"STATIC_VERSION": getattr(settings, "STATIC_VERSION", "1")}


def seo_defaults(request) -> dict[str, str]:
    """Expose global SEO defaults for meta tags and canonical links."""

    query_dict = request.GET.copy()
    for removable in ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"):
        query_dict.pop(removable, None)

    canonical_url = request.build_absolute_uri(request.path)
    if query_dict:
        canonical_url = f"{canonical_url}?{urlencode(query_dict, doseq=True)}"

    robots = "index,follow"
    noindex_path_prefixes = (
        "/accounts/login/",
        "/accounts/signup/",
        "/accounts/password-reset/",
        "/accounts/reset/",
        "/accounts/logout/",
    )
    if request.path.startswith(noindex_path_prefixes):
        robots = "noindex,nofollow"

    if any(param in request.GET for param in ("page", "sort", "q")):
        robots = "noindex,follow"
        canonical_url = request.build_absolute_uri(request.path)

    return {
        "seo_description": DEFAULT_DESCRIPTION,
        "seo_robots": robots,
        "canonical_url": canonical_url,
    }