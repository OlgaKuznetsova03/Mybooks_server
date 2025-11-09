from __future__ import annotations

import zipfile
from typing import Iterable

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


_DANGEROUS_EXTENSIONS: tuple[str, ...] = (
    ".exe",
    ".bat",
    ".cmd",
    ".sh",
    ".ps1",
    ".js",
    ".vbs",
    ".dll",
    ".scr",
    ".msi",
    ".com",
    ".jar",
    ".py",
)


def _contains_traversal(parts: Iterable[str]) -> bool:
    for part in parts:
        if part in {"..", "."}:
            return True
    return False


def validate_epub_attachment(upload) -> None:
    """Проверяет, что загруженный файл является безопасным EPUB."""

    filename = getattr(upload, "name", "") or ""
    if not filename.lower().endswith(".epub"):
        raise ValidationError(_("Можно прикрепить только файлы в формате EPUB."))

    initial_position = None
    if hasattr(upload, "tell"):
        try:
            initial_position = upload.tell()
        except Exception:  # pragma: no cover - несовместимый файловый объект
            initial_position = None

    try:
        with zipfile.ZipFile(upload) as archive:
            corrupted = archive.testzip()
            if corrupted is not None:
                raise ValidationError(
                    _("Файл EPUB повреждён: %(filename)s") % {"filename": corrupted}
                )

            try:
                mimetype_data = archive.read("mimetype")
            except KeyError as exc:
                raise ValidationError(
                    _("Файл EPUB не содержит обязательного файла mimetype."),
                ) from exc

            if b"application/epub+zip" not in mimetype_data.strip():
                raise ValidationError(
                    _("Некорректное содержимое файла mimetype у загруженного EPUB."),
                )

            for member in archive.namelist():
                normalized = member.replace("\\", "/")
                parts = [part for part in normalized.split("/") if part]
                if _contains_traversal(parts):
                    raise ValidationError(
                        _("Обнаружены подозрительные пути внутри EPUB архива."),
                    )
                lowered = normalized.lower()
                if lowered.endswith(_DANGEROUS_EXTENSIONS):
                    raise ValidationError(
                        _("EPUB содержит потенциально опасные вложения."),
                    )
    except zipfile.BadZipFile as exc:
        raise ValidationError(
            _("Файл повреждён или не является корректным EPUB."),
        ) from exc
    finally:
        if hasattr(upload, "seek"):
            try:
                if initial_position is not None:
                    upload.seek(initial_position)
                else:
                    upload.seek(0)
            except Exception:  # pragma: no cover - защита от редких реализаций
                pass