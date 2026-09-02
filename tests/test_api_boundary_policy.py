import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import unified_media_api
from werkzeug.test import Client


class ApiBoundaryPolicyTests(unittest.TestCase):
    def test_new_task_id_has_a_32_character_hexadecimal_nonce(self):
        task_id = unified_media_api.create_task_id()

        self.assertRegex(task_id, re.compile(r"^TASK-\d{8}-[0-9A-F]{32}$"))
        self.assertTrue(unified_media_api.is_valid_task_id(task_id))

    def test_reports_are_memory_only_when_persistence_is_disabled_by_default(self):
        self.assertFalse(unified_media_api.PERSIST_REPORTS)

        with TemporaryDirectory() as temporary_directory:
            report_directory = Path(temporary_directory)
            task_id = unified_media_api.create_task_id()
            report = {
                "task_id": task_id,
                "verdict": "uncertain",
                "summary": "memory-only regression fixture",
            }

            with patch.object(unified_media_api, "REPORT_DIR", report_directory), \
                    patch.object(unified_media_api, "TASKS", {}):
                unified_media_api.save_report(task_id, report)

                self.assertFalse((report_directory / f"{task_id}.json").exists())
                self.assertEqual(
                    unified_media_api.task_snapshot(task_id)["report"],
                    report,
                )

    def test_cors_allows_local_frontend_and_rejects_unlisted_origin(self):
        client = Client(unified_media_api.app)

        local_response = client.get(
            "/api/info",
            headers={"Origin": "http://localhost:3000"},
        )
        unlisted_response = client.get(
            "/api/info",
            headers={"Origin": "https://evil.example"},
        )

        self.assertEqual(local_response.status_code, 200)
        self.assertEqual(
            local_response.headers.get("Access-Control-Allow-Origin"),
            "http://localhost:3000",
        )
        self.assertEqual(unlisted_response.status_code, 200)
        self.assertIsNone(
            unlisted_response.headers.get("Access-Control-Allow-Origin"),
        )


if __name__ == "__main__":
    unittest.main()
