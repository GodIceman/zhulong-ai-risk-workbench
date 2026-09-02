import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import unified_media_api
from werkzeug.test import Client


class ReportPathSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)

        self.root = Path(self.temporary_directory.name)
        self.report_directory = self.root / "reports"
        self.report_directory.mkdir()

        report_dir_patch = patch.object(
            unified_media_api,
            "REPORT_DIR",
            self.report_directory,
        )
        tasks_patch = patch.object(unified_media_api, "TASKS", {})
        report_dir_patch.start()
        tasks_patch.start()
        self.addCleanup(report_dir_patch.stop)
        self.addCleanup(tasks_patch.stop)

        self.client = Client(unified_media_api.app)

    def test_path_traversal_task_id_cannot_read_report_directory_sibling(self):
        secret_marker = "outside-report-directory"
        (self.root / "secret.json").write_text(
            json.dumps({"secret": secret_marker}),
            encoding="utf-8",
        )

        response = self.client.get("/api/tasks/..%5Csecret/report")

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["code"], "INVALID_TASK_ID")
        self.assertNotIn(secret_marker, response.get_data(as_text=True))

    def test_malformed_task_ids_are_rejected(self):
        malformed_task_ids = (
            "not-a-task-id",
            "TASK-20260718-ABCDEF12",
            f"TASK-20260718-{'G' * 32}",
            f"task-20260718-{'A' * 32}",
        )

        for task_id in malformed_task_ids:
            with self.subTest(task_id=task_id):
                response = self.client.get(f"/api/tasks/{task_id}/report")

                self.assertEqual(response.status_code, 400)
                payload = response.get_json()
                self.assertFalse(payload["success"])
                self.assertEqual(payload["error"]["code"], "INVALID_TASK_ID")

    def test_valid_task_id_returns_report_from_report_directory(self):
        task_id = f"TASK-20260718-{'A1' * 16}"
        expected_report = {
            "task_id": task_id,
            "verdict": "uncertain",
            "summary": "regression fixture",
        }
        (self.report_directory / f"{task_id}.json").write_text(
            json.dumps(expected_report),
            encoding="utf-8",
        )

        response = self.client.get(f"/api/tasks/{task_id}/report")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"success": True, "report": expected_report},
        )


if __name__ == "__main__":
    unittest.main()
