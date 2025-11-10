"""Template utilities for rendering feature cost notices."""

from __future__ import annotations

import logging
from typing import Any

from django import template
from django.template import TemplateDoesNotExist, loader

logger = logging.getLogger(__name__)

register = template.Library()


@register.simple_tag(takes_context=True)
def render_feature_cost_notice(context: template.Context, *, classes: str = "text-muted small mt-2") -> str:
    """Render the feature cost notice safely.

    The project historically inlined the notice via ``{% include %}``.  On some
    deployments the template may be temporarily unavailable which previously
    caused ``TemplateDoesNotExist`` errors and broke the whole page.  Rendering
    through a template tag lets us degrade gracefully while keeping the markup
    in the original template.
    """

    feature_cost = context.get("feature_cost")
    if not feature_cost:
        return ""

    try:
        notice_template = loader.get_template("includes/feature_cost_notice.html")
    except TemplateDoesNotExist:
        logger.warning(
            "Feature cost template is missing – skipping notice render.",
            exc_info=True,
        )
        return ""

    flattened_context: dict[str, Any] = context.flatten()
    flattened_context["classes"] = classes
    request = context.get("request")

    return notice_template.render(flattened_context, request=request)