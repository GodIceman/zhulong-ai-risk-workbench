import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.eval_media_detection import evaluate_row


def uncertain_report():
    return {
        "verdict": "uncertain",
        "risk_level": "unknown",
        "confidence": None,
        "summary": "fixture",
        "evidence": [],
        "models": [],
        "decision": {},
        "metadata": {},
    }


class EvalInputIsolationTests(unittest.TestCase):
    def test_release_evaluation_neutralizes_manifest_hint_and_filename(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            sample = root / "known-ai-screenshot.png"
            sample.write_bytes(b"fixture")
            row = {
                "file_path": sample.name,
                "label": "ai_generated",
                "domain": "general",
                "source_hint": "camera_export",
                "expected_verdict": "ai_generated",
            }

            with patch(
                "scripts.eval_media_detection.upload",
                return_value="TASK-20260718-" + ("A" * 32),
            ) as upload_mock, patch(
                "scripts.eval_media_detection.wait_for_report",
                return_value=uncertain_report(),
            ):
                result = evaluate_row(
                    "http://127.0.0.1:5002",
                    root,
                    row,
                    timeout=1,
                    prepare_large_images=False,
                    use_manifest_source_hints=False,
                )

        self.assertEqual(result["source_hint_used"], "auto")
        self.assertEqual(result["upload_name_used"], "sample.png")
        self.assertEqual(upload_mock.call_args.kwargs["upload_name"], "sample.png")
        self.assertEqual(upload_mock.call_args.args[2], "auto")

    def test_contextual_evaluation_requires_explicit_opt_in(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            sample = root / "known-ai-screenshot.png"
            sample.write_bytes(b"fixture")
            row = {
                "file_path": sample.name,
                "label": "ai_generated",
                "domain": "general",
                "source_hint": "camera_export",
                "expected_verdict": "ai_generated",
            }

            with patch(
                "scripts.eval_media_detection.upload",
                return_value="TASK-20260718-" + ("A" * 32),
            ) as upload_mock, patch(
                "scripts.eval_media_detection.wait_for_report",
                return_value=uncertain_report(),
            ):
                result = evaluate_row(
                    "http://127.0.0.1:5002",
                    root,
                    row,
                    timeout=1,
                    prepare_large_images=False,
                    use_manifest_source_hints=True,
                )

        self.assertEqual(result["source_hint_used"], "camera_export")
        self.assertEqual(result["upload_name_used"], sample.name)
        self.assertEqual(upload_mock.call_args.kwargs["upload_name"], sample.name)
        self.assertEqual(upload_mock.call_args.args[2], "camera_export")


if __name__ == "__main__":
    unittest.main()
