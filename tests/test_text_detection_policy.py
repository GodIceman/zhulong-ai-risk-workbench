import unittest
from unittest.mock import patch

from werkzeug.test import Client

import ai_image_api as api


def segment(score, characters=100):
    return {
        "ai_signal_score": score,
        "character_count": characters,
    }


class TextDetectionPolicyTests(unittest.TestCase):
    def test_high_signal_requires_document_score_and_segment_consensus(self):
        result = api.aggregate_text_signals([
            segment(0.98),
            segment(0.92),
            segment(0.70),
        ])

        self.assertEqual(result["verdict"], "ai_style_suspected")
        self.assertEqual(result["risk_level"], "high")
        self.assertGreaterEqual(result["strong_ai_segment_ratio"], 0.5)

    def test_low_signal_never_certifies_human_authorship(self):
        result = api.aggregate_text_signals([
            segment(0.01),
            segment(0.04),
            segment(0.10),
        ])

        self.assertEqual(result["verdict"], "no_strong_ai_signal")
        self.assertNotIn("human", result["verdict"])

    def test_mixed_segments_abstain(self):
        result = api.aggregate_text_signals([
            segment(0.97),
            segment(0.03),
        ])

        self.assertEqual(result["verdict"], "uncertain")
        self.assertEqual(result["risk_level"], "unknown")
        self.assertIsNone(result["classification_confidence"])

    def test_single_overconfident_segment_never_forms_document_verdict(self):
        result = api.aggregate_text_signals([
            segment(0.999, characters=180),
        ])

        self.assertEqual(result["verdict"], "uncertain")
        self.assertEqual(result["risk_level"], "unknown")
        self.assertIn("insufficient_independent_segments", result["decision_reasons"])

    def test_segment_builder_samples_across_long_document(self):
        text = "\n".join(
            f"第 {index} 段：" + ("用于检测的中文内容。" * 40)
            for index in range(api.TEXT_MAX_SEGMENTS + 10)
        )

        normalized, segments = api.build_text_segments(text)

        self.assertTrue(normalized)
        self.assertEqual(len(segments), api.TEXT_MAX_SEGMENTS)
        self.assertEqual(segments[0]["index"], 0)
        self.assertIn("第 0 段", segments[0]["text"])
        self.assertGreater(segments[-1]["end"], len(normalized) - 300)

    def test_short_text_returns_insufficient_without_loading_model(self):
        with patch.object(api, "load_text_model") as load_mock:
            result = api.detect_ai_text("文字太短。")

        self.assertEqual(result["verdict"], "insufficient_text")
        load_mock.assert_not_called()

    def test_endpoint_exposes_experimental_release_boundary(self):
        client = Client(api.app)
        detector_result = {
            "verdict": "ai_style_suspected",
            "risk_level": "high",
            "ai_signal_score": 0.93,
            "classification_confidence": 0.93,
            "segments": [],
            "segment_count": 1,
            "analyzed_character_count": 100,
            "total_character_count": 100,
            "analysis_coverage": 1.0,
            "score_dispersion": 0.0,
            "decision_reasons": ["fixture"],
            "latency_ms": 12,
        }

        with patch.object(api, "detect_ai_text", return_value=detector_result):
            response = client.post(
                "/api/text/detect",
                json={"text": "这是一段长度足够的测试文字。" * 10},
            )

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertFalse(payload["release_qualified"])
        self.assertFalse(payload["commercial_use_qualified"])
        self.assertEqual(payload["policy_version"], api.TEXT_POLICY_VERSION)


if __name__ == "__main__":
    unittest.main()
