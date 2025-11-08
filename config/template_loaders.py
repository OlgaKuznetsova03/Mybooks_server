"""Custom template loaders for safer filesystem access.

These loaders gracefully handle permission issues so that Django can
fallback to bundled templates instead of raising an error when a custom
template cannot be read due to restrictive filesystem permissions.
"""

from __future__ import annotations

import logging
from django.template import TemplateDoesNotExist
from django.template.loaders.filesystem import Loader as FilesystemLoader

logger = logging.getLogger(__name__)


class SafeFilesystemLoader(FilesystemLoader):
    """Filesystem loader that ignores templates with insufficient permissions.

    The default filesystem loader raises a :class:`PermissionError` when a
    template file exists but cannot be read. In production environments where
    deployment users differ from application users, custom templates may end up
    with restrictive permissions. Instead of surfacing an HTTP 500 error, we
    treat these templates as missing so Django can fall back to templates
    provided by installed apps (e.g. Django's admin templates).
    """

    def get_contents(self, origin):  # type: ignore[override]
        try:
            return super().get_contents(origin)
        except PermissionError as exc:  # pragma: no cover - depends on FS state
            logger.warning(
                "Skipping template %s due to permission error: %s",
                origin.name,
                exc,
            )
            raise TemplateDoesNotExist(origin) from exc