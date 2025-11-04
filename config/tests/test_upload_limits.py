from django.test import SimpleTestCase
from django.conf import settings

from accounts.forms import ProfileForm
from books.forms import BookForm, LenientImageField


class UploadLimitSettingsTests(SimpleTestCase):
    def test_global_limits_cover_configured_max(self) -> None:
        base_limit_mb = max(settings.MAX_IMAGE_UPLOAD_MB, settings.MAX_AVATAR_UPLOAD_MB)
        expected_bytes = base_limit_mb * 1024 * 1024
        self.assertGreaterEqual(settings.FILE_UPLOAD_MAX_MEMORY_SIZE, expected_bytes)
        self.assertGreaterEqual(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, expected_bytes)

    def test_book_form_respects_global_limit(self) -> None:
        field = BookForm.base_fields["cover"]
        self.assertIsInstance(field, LenientImageField)
        self.assertEqual(field.max_size, settings.MAX_IMAGE_UPLOAD_MB)

    def test_profile_form_respects_global_limit(self) -> None:
        field = ProfileForm.base_fields["avatar"]
        self.assertIsInstance(field, LenientImageField)
        self.assertEqual(field.max_size, settings.MAX_AVATAR_UPLOAD_MB)