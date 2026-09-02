import unittest
from unittest.mock import patch

import video_face_api as video_api
from unified_media_api import build_video_report


def branch(status, verdict, score=0.9, model_id="test-model"):
    return {
        "status": status,
        "verdict": verdict,
        "score": score,
        "confidence": score * 100,
        "model_id": model_id,
        "model_version": "test",
        "release_qualified": False,
        "performance_qualified": False,
        "commercial_use_qualified": False,
        "frame_predictions": [],
        "error": None,
    }


class CombinedVideoServicePolicyTests(unittest.TestCase):
    def analyze_with(self, generated_status, face_status, d3_status):
        sample = video_api.VideoSample(
            frames={},
            full_indices=[],
            wave_indices=[],
            face_indices=[],
            d3_indices=[],
            timestamps={},
            fps=24.0,
            total_frames=96,
            duration_seconds=4.0,
            width=512,
            height=512,
        )
        service_generated_status = (
            "candidate_positive" if generated_status == "positive" else generated_status
        )
        generated = branch(
            service_generated_status,
            "ai_generated_video_suspected"
            if generated_status == "positive"
            else "uncertain",
            model_id=video_api.WAVEREP_MODEL_ID,
        )
        face = branch(
            face_status,
            "face_manipulation_suspected"
            if face_status == "positive"
            else "uncertain",
            model_id=video_api.MODEL_ID,
        )
        face["face_detection_ratio"] = 1.0
        temporal = branch(
            d3_status,
            "temporal_ai_signal" if d3_status == "supporting" else "uncertain",
            score=0.004,
            model_id=video_api.D3_MODEL_ID,
        )
        with (
            patch.object(video_api, "read_video_sample", return_value=sample),
            patch.object(video_api, "analyze_aegis", return_value=generated),
            patch.object(video_api, "_prepare_face_sample", return_value=([], [], 1.0)),
            patch.object(video_api, "_face_branch", return_value=face),
            patch.object(video_api, "analyze_d3", return_value=temporal),
        ):
            return video_api.analyze_video(video_api.Path("unused.mp4"))

    def test_full_generation_signal_forms_specific_positive_verdict(self):
        result = self.analyze_with("positive", "abstained", "supporting")

        self.assertEqual(result["verdict"], "ai_generated_video_suspected")
        self.assertEqual(result["risk_level"], "high")
        self.assertIn("d3_temporal_support", result["decision"]["reasons"])

    def test_face_signal_forms_specific_positive_verdict(self):
        result = self.analyze_with("abstained", "positive", "not_supporting")

        self.assertEqual(result["verdict"], "face_manipulation_suspected")

    def test_two_primary_signals_form_multiple_signal_verdict(self):
        result = self.analyze_with("positive", "positive", "supporting")

        self.assertEqual(result["verdict"], "multiple_video_ai_signals")

    def test_d3_only_can_never_trigger_a_positive_verdict(self):
        result = self.analyze_with("abstained", "abstained", "supporting")

        self.assertEqual(result["verdict"], "uncertain")
        self.assertEqual(result["risk_level"], "unknown")
        self.assertIsNone(result["confidence"])


class CombinedVideoReportTests(unittest.TestCase):
    def test_combined_report_preserves_branch_verdict_and_demo_boundaries(self):
        raw = {
            "success": True,
            "verdict": "ai_generated_video_suspected",
            "score": 0.91,
            "policy_version": video_api.VIDEO_POLICY_VERSION,
            "branches": {
                "full_generation": {"status": "positive"},
                "face_manipulation": {"status": "abstained"},
                "temporal_auxiliary": {"status": "supporting"},
            },
            "models": [
                {
                    "model_id": video_api.WAVEREP_MODEL_ID,
                    "model_version": video_api.WAVEREP_MODEL_VERSION,
                    "role": "full_generation_primary",
                    "score": 0.91,
                    "label": "ai_generated_video_suspected",
                    "status": "positive",
                }
            ],
            "decision": {
                "reasons": ["waverep_generated_signal", "d3_temporal_support"],
                "quality": {"status": "local_demo", "never_certifies_real": True},
            },
            "evidence": [],
            "frame_predictions": [],
            "limitations": ["本地演示，不认证真实。"],
            "media": {"duration_seconds": 4.0},
        }
        report = build_video_report(
            "TASK-TEST",
            {"filename": "sample.mp4"},
            [],
            {
                "model": {
                    "model_id": video_api.VIDEO_ENSEMBLE_ID,
                    "model_version": video_api.VIDEO_ENSEMBLE_VERSION,
                    "label": raw["verdict"],
                    "score": raw["score"],
                    "error": None,
                },
                "raw": raw,
            },
        )

        self.assertEqual(report["verdict"], "ai_generated_video_suspected")
        self.assertEqual(report["risk_level"], "high")
        self.assertFalse(report["decision"]["quality"]["release_qualified"])
        self.assertFalse(report["decision"]["quality"]["temporal_auxiliary_can_trigger"])
        self.assertTrue(report["decision"]["quality"]["never_certifies_real"])


if __name__ == "__main__":
    unittest.main()
