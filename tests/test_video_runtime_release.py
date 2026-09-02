import math
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch
from werkzeug.test import Client

import video_face_api as api


class _FakeProcessor:
    def __call__(self, images, return_tensors):
        assert return_tensors == "pt"
        return {"pixel_values": torch.zeros((len(images), 3, 2, 2))}


class _FakeModel:
    def __call__(self, pixel_values):
        return torch.tensor([[0.0, 2.0]] * len(pixel_values))


class VideoRuntimeReleaseTests(unittest.TestCase):
    def test_default_runtime_matches_manifest_but_license_fails_closed(self):
        metadata = api.get_release_metadata()

        self.assertEqual(
            api._fingerprint(api.RELEASE_MANIFEST),
            api.RELEASE_MANIFEST_FINGERPRINT,
        )
        self.assertTrue(metadata["runtime_manifest_qualified"])
        self.assertEqual(
            metadata["runtime_qualification_reason"],
            "runtime_matches_release_manifest",
        )
        self.assertTrue(metadata["performance_qualified"])
        self.assertEqual(
            metadata["performance_evaluation_id"],
            api.PERFORMANCE_EVALUATION_ID,
        )
        self.assertEqual(
            metadata["performance_evaluation_summary"]["real_videos_warned"],
            0,
        )
        self.assertEqual(
            metadata["performance_evaluation_summary"]["face_swap_videos_warned"],
            9,
        )
        self.assertFalse(metadata["commercial_use_qualified"])
        self.assertFalse(metadata["release_qualified"])
        self.assertEqual(
            metadata["release_qualification_reason"],
            "license_not_qualified_for_commercial_release",
        )
        self.assertEqual(
            metadata["runtime_fingerprint"],
            metadata["release_manifest_fingerprint"],
        )
        self.assertEqual(metadata["model_revision"], api.VERIFIED_MODEL_REVISION)
        self.assertEqual(
            metadata["processor_revision"],
            api.VERIFIED_PROCESSOR_REVISION,
        )
        self.assertEqual(metadata["threshold"], api.DEFAULT_THRESHOLD)

    def test_revision_or_threshold_drift_fails_closed(self):
        with patch.object(api, "MODEL_REVISION", "0" * 40):
            model_drift = api.get_release_metadata()
        with patch.object(api, "PROCESSOR_REVISION", "1" * 40):
            processor_drift = api.get_release_metadata()
        with patch.object(api, "THRESHOLD", 0.51):
            threshold_drift = api.get_release_metadata()

        for metadata in (model_drift, processor_drift, threshold_drift):
            self.assertFalse(metadata["runtime_manifest_qualified"])
            self.assertFalse(metadata["release_qualified"])
            self.assertEqual(
                metadata["runtime_qualification_reason"],
                "runtime_differs_from_release_manifest",
            )
            self.assertEqual(
                metadata["release_qualification_reason"],
                "runtime_not_qualified",
            )
            self.assertNotEqual(
                metadata["runtime_fingerprint"],
                metadata["release_manifest_fingerprint"],
            )

    def test_threshold_validation_rejects_unsafe_values(self):
        for raw_value in ("", "not-a-number", "0", "1", "-0.1", "1.1", "nan", "inf"):
            value, error = api._parse_threshold(raw_value)
            self.assertIsNone(value, raw_value)
            self.assertIsNotNone(error, raw_value)

        for raw_value in ("0.01", "0.5", "0.99"):
            value, error = api._parse_threshold(raw_value)
            self.assertTrue(math.isfinite(value), raw_value)
            self.assertIsNone(error, raw_value)

    def test_health_exposes_release_configuration(self):
        with patch.object(api, "model", object()):
            response = Client(api.app).get("/api/deepfake/health")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["runtime_manifest_qualified"])
        self.assertTrue(payload["performance_qualified"])
        self.assertFalse(payload["commercial_use_qualified"])
        self.assertFalse(payload["release_qualified"])
        self.assertEqual(payload["fingerprint"], payload["runtime_fingerprint"])
        self.assertEqual(payload["threshold"], api.DEFAULT_THRESHOLD)
        self.assertEqual(payload["model_revision"], api.VERIFIED_MODEL_REVISION)
        self.assertEqual(
            payload["processor_revision"],
            api.VERIFIED_PROCESSOR_REVISION,
        )
        self.assertTrue(payload["license_review"]["warnings"])
        self.assertTrue(
            any(
                item["model_id"] == api.PROCESSOR_ID
                and item["license_id"] == "unknown"
                and item["review_required"] is True
                for item in payload["license_review"]["dependencies"]
            )
        )
        self.assertTrue(
            any(
                item["model_id"] == api.MODEL_ID
                and item["license_id"] == "mit"
                and item["commercial_use_allowed"] is True
                for item in payload["license_review"]["dependencies"]
            )
        )

    def test_analysis_response_exposes_release_configuration(self):
        frames = [np.zeros((2, 2, 3), dtype=np.uint8)] * api.FRAME_COUNT
        timestamps = [0.0, 1.0, 2.0, 3.0]
        with (
            patch.object(api, "read_frames", return_value=(frames, timestamps, 1.0)),
            patch.object(api, "processor", _FakeProcessor()),
            patch.object(api, "model", _FakeModel()),
        ):
            payload = api.analyze(Path("unused.mp4"))

        self.assertTrue(payload["success"])
        self.assertTrue(payload["runtime_manifest_qualified"])
        self.assertTrue(payload["performance_qualified"])
        self.assertFalse(payload["commercial_use_qualified"])
        self.assertFalse(payload["release_qualified"])
        self.assertEqual(payload["fingerprint"], payload["runtime_fingerprint"])
        self.assertEqual(
            payload["runtime_fingerprint"],
            payload["release_manifest_fingerprint"],
        )
        self.assertEqual(payload["threshold"], api.DEFAULT_THRESHOLD)
        self.assertEqual(payload["model_revision"], api.VERIFIED_MODEL_REVISION)
        self.assertEqual(
            payload["processor_revision"],
            api.VERIFIED_PROCESSOR_REVISION,
        )
        self.assertEqual(
            payload["performance_evaluation_id"],
            api.PERFORMANCE_EVALUATION_ID,
        )


if __name__ == "__main__":
    unittest.main()
