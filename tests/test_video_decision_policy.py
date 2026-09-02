import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from unified_media_api import build_video_report, call_deepfake_video_detector


def detector(label="deepfake_suspected", score=0.99, release_qualified=False, error=None):
    return {
        "model": {
            "model_id": "video-test-model",
            "model_version": "test",
            "engine_type": "model",
            "score": score,
            "label": label,
            "latency_ms": 10,
            "error": error,
            "release_qualified": release_qualified,
        },
        "raw": {},
    }


class VideoDecisionPolicyTests(unittest.TestCase):
    def test_unqualified_suspicious_model_is_experimental_only(self):
        report = build_video_report("video-test", {}, [], detector())

        self.assertEqual(report["verdict"], "uncertain")
        self.assertEqual(report["risk_level"], "unknown")
        self.assertIsNone(report["confidence"])
        self.assertEqual(report["models"][0]["score"], 0.99)
        self.assertEqual(report["decision"]["quality"]["status"], "experimental")
        self.assertIn("video_model_not_release_qualified", report["decision"]["reasons"])

    def test_unqualified_real_model_cannot_form_likely_real_verdict(self):
        report = build_video_report(
            "video-test-real",
            {},
            [],
            detector(label="likely_real", score=0.95),
        )

        self.assertEqual(report["verdict"], "uncertain")
        self.assertIsNone(report["confidence"])

    def test_release_qualified_model_can_form_verdict(self):
        report = build_video_report(
            "video-test-qualified",
            {},
            [],
            detector(release_qualified=True),
        )

        self.assertEqual(report["verdict"], "deepfake_suspected")
        self.assertEqual(report["risk_level"], "high")
        self.assertEqual(report["confidence"], 0.99)

    def test_positive_only_model_abstention_never_becomes_real(self):
        report = build_video_report(
            "video-test-abstain",
            {},
            [],
            detector(label="uncertain", score=0.2, release_qualified=True),
        )

        self.assertEqual(report["verdict"], "uncertain")
        self.assertEqual(report["risk_level"], "unknown")
        self.assertIsNone(report["confidence"])
        self.assertIn("qualified_positive_only_model_abstained", report["decision"]["reasons"])

    def test_model_error_still_returns_failed_report(self):
        report = build_video_report(
            "video-test-failed",
            {},
            [],
            detector(label="failed", score=0, error="unavailable"),
        )

        self.assertEqual(report["verdict"], "failed")
        self.assertIsNone(report["confidence"])

    def test_unified_client_requires_all_video_release_gates(self):
        class Response:
            status_code = 200
            content = b"{}"

            @staticmethod
            def json():
                return {
                    "success": True,
                    "verdict": "deepfake_suspected",
                    "score": 0.99,
                    "model_id": "pinned-video-model",
                    "model_version": "test",
                    "runtime_manifest_qualified": True,
                    "runtime_qualification_reason": "runtime_matches_release_manifest",
                    "performance_qualified": True,
                    "commercial_use_qualified": False,
                    "release_qualified": False,
                    "release_qualification_reason": "license_not_qualified_for_commercial_release",
                    "runtime_fingerprint": "sha256:same",
                    "release_manifest_fingerprint": "sha256:same",
                    "license_review": {"warnings": ["processor license review"]},
                }

        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "sample.mp4"
            path.write_bytes(b"fixture")
            with patch("unified_media_api.requests.post", return_value=Response()):
                result = call_deepfake_video_detector(path, "sample.mp4")

        model_result = result["model"]
        self.assertTrue(model_result["runtime_manifest_qualified"])
        self.assertTrue(model_result["performance_qualified"])
        self.assertFalse(model_result["commercial_use_qualified"])
        self.assertFalse(model_result["release_qualified"])


if __name__ == "__main__":
    unittest.main()
