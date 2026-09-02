import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from unified_media_api import build_image_report, call_ai_image_detector


def metadata(**overrides):
    value = {
        "filename": "sample.jpg",
        "file_size": 1024,
        "format": "jpeg",
        "width": 1200,
        "height": 800,
        "exif_present": True,
        "camera_make": "Example Camera",
        "camera_model": "Model 1",
        "created_time": "2026:01:01 12:00:00",
        "source_hint": "auto",
        "protected_domain": False,
        "screen_capture_likely": False,
        "generator_metadata_detected": False,
        "generator_metadata_producers": [],
    }
    value.update(overrides)
    return value


def model(ai_score, label, release_qualified):
    auxiliary_score = 0.99 if label == "ai_generated" else 0.05
    return {
        "model_id": "release-policy-primary",
        "model_version": "test",
        "engine_type": "model",
        "ai_score": ai_score,
        "real_score": 1 - ai_score,
        "score": ai_score if label == "ai_generated" else 1 - ai_score,
        "label": label,
        "error": None,
        "runtime_manifest_qualified": True,
        "performance_qualified": release_qualified,
        "commercial_use_qualified": release_qualified,
        "release_qualified": release_qualified,
        "release_qualification_reason": (
            "runtime_performance_and_license_qualified"
            if release_qualified
            else "performance_not_qualified"
        ),
        "license_review": {"warnings": []},
        "auxiliary_models": [
            {
                "model_id": "release-policy-auxiliary",
                "model_version": "test",
                "engine_type": "model",
                "ai_score": auxiliary_score,
                "real_score": 1 - auxiliary_score,
                "score": max(auxiliary_score, 1 - auxiliary_score),
                "label": (
                    "ai_generated"
                    if auxiliary_score >= 0.5
                    else "likely_real"
                ),
                "error": None,
            }
        ],
    }


class ImageReleasePolicyTests(unittest.TestCase):
    def test_unqualified_model_consensus_cannot_form_ai_verdict(self):
        report = build_image_report(
            "unqualified-ai",
            metadata(),
            model(0.98, "ai_generated", release_qualified=False),
        )

        self.assertEqual(report["verdict"], "uncertain")
        self.assertEqual(report["risk_level"], "unknown")
        self.assertIsNone(report["confidence"])
        self.assertEqual(report["decision"]["quality"]["status"], "experimental")
        self.assertIn(
            "image_model_not_release_qualified",
            report["decision"]["reasons"],
        )

    def test_unqualified_real_signal_cannot_certify_real_content(self):
        report = build_image_report(
            "unqualified-real",
            metadata(),
            model(0.02, "likely_real", release_qualified=False),
        )

        self.assertEqual(report["verdict"], "uncertain")
        self.assertIsNone(report["confidence"])

    def test_generator_metadata_remains_a_medium_risk_non_model_signal(self):
        report = build_image_report(
            "generator-metadata",
            metadata(
                generator_metadata_detected=True,
                generator_metadata_producers=["Example Generator"],
            ),
            model(0.02, "likely_real", release_qualified=False),
        )

        self.assertEqual(report["verdict"], "ai_generated")
        self.assertEqual(report["risk_level"], "medium")
        self.assertIsNone(report["confidence"])
        self.assertEqual(report["decision"]["quality"]["status"], "metadata_only")

    def test_unified_client_propagates_image_release_gates(self):
        class Response:
            status_code = 200
            content = b"{}"

            @staticmethod
            def json():
                return {
                    "success": True,
                    "model": "pinned-image-model",
                    "model_revision": "abc123",
                    "processor_id": "pinned-image-model",
                    "processor_revision": "def456",
                    "is_ai": True,
                    "ai_score": 98,
                    "real_score": 2,
                    "auxiliary_models": [],
                    "runtime_manifest_qualified": True,
                    "performance_qualified": False,
                    "commercial_use_qualified": False,
                    "release_qualified": False,
                    "release_qualification_reason": "performance_not_qualified",
                    "runtime_fingerprint": "sha256:test",
                    "license_review": {"warnings": ["non-commercial model"]},
                }

        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "sample.jpg"
            path.write_bytes(b"fixture")
            with patch("unified_media_api.requests.post", return_value=Response()):
                result = call_ai_image_detector(path, "sample.jpg")

        self.assertTrue(result["runtime_manifest_qualified"])
        self.assertFalse(result["performance_qualified"])
        self.assertFalse(result["commercial_use_qualified"])
        self.assertFalse(result["release_qualified"])
        self.assertEqual(result["model_revision"], "abc123")
        self.assertEqual(result["runtime_fingerprint"], "sha256:test")


if __name__ == "__main__":
    unittest.main()
