from __future__ import annotations

from django.conf import settings


def static_version(_: object) -> dict[str, str]:
    """Expose the cache-busting static version to templates."""
    return {"STATIC_VERSION": getattr(settings, "STATIC_VERSION", "1")}