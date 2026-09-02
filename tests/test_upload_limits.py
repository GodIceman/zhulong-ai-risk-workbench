import io
import unittest
from unittest.mock import patch

from werkzeug.datastructures import FileStorage

import unified_media_api


class UploadLimitTests(unittest.TestCase):
    def test_default_image_limit_is_20_mb(self):
        self.assertEqual(unified_media_api.DEFAULT_MAX_IMAGE_BYTES, 20 * 1024 * 1024)

    def test_oversized_image_has_actionable_error(self):
        upload = FileStorage(
            stream=io.BytesIO(b"x" * 1025),
            filename="sample.png",
            content_type="image/png",
        )

        with patch.object(unified_media_api, "MAX_IMAGE_BYTES", 1024):
            with self.assertRaisesRegex(OverflowError, "压缩文件或缩小分辨率"):
                unified_media_api.validate_upload(upload)


if __name__ == "__main__":
    unittest.main()
