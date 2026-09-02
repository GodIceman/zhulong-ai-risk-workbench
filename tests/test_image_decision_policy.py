import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image, PngImagePlugin

from unified_media_api import build_image_report, extract_image_metadata, process_task


def metadata(**overrides):
    value = {
        "filename": "sample.jpg",
        "file_size": 1024,
        "format": "jpeg",
        "width": 1024,
        "height": 768,
        "exif_present": False,
        "source_hint": "auto",
        "protected_domain": False,
    }
    value.update(overrides)
    return value


def model(ai_score, label, auxiliary_ai_score=None):
    value = {
        "model_id": "primary",
        "model_version": "test",
        "engine_type": "model",
        "ai_score": ai_score,
        "real_score": 1 - ai_score,
        "score": ai_score if label == "ai_generated" else 1 - ai_score,
        "label": label,
        "error": None,
        "auxiliary_models": [],
    }
    if auxiliary_ai_score is not None:
        value["auxiliary_models"].append({
            "model_id": "aux-test",
            "model_version": "test",
            "engine_type": "model",
            "ai_score": auxiliary_ai_score,
            "real_score": 1 - auxiliary_ai_score,
            "label": "ai_generated" if auxiliary_ai_score >= 0.5 else "likely_real",
            "error": None,
        })
    return value


class ImageDecisionPolicyTests(unittest.TestCase):
    def test_protected_capture_blocks_high_risk_ai_verdict(self):
        report = build_image_report(
            "test-protected",
            metadata(format="png", source_hint="screen_capture", protected_domain=True),
            model(0.98, "ai_generated", 0.99),
        )

        self.assertEqual(report["verdict"], "uncertain")
        self.assertEqual(report["risk_level"], "unknown")
        self.assertIn("protected_domain_overrides_ai_model_signal", report["decision"]["reasons"])

    def test_low_provenance_with_only_strong_auxiliary_signal_abstains(self):
        report = build_image_report(
            "test-ai",
            metadata(format="png", source_hint="auto", exif_present=False),
            model(0.2, "likely_real", 0.99),
        )

        self.assertEqual(report["verdict"], "uncertain")
        self.assertEqual(report["risk_level"], "unknown")
        self.assertIsNone(report["confidence"])

    def test_camera_hint_blocks_single_model_ai_signal(self):
        report = build_image_report(
            "test-camera",
            metadata(source_hint="camera_export", exif_present=False),
            model(0.96, "ai_generated", 0.4),
        )

        self.assertEqual(report["verdict"], "uncertain")
        self.assertIsNone(report["confidence"])
        self.assertIn("camera_source_hint_blocks_single_model_ai", report["decision"]["reasons"])

    def test_camera_metadata_and_real_model_can_form_likely_real_verdict(self):
        report = build_image_report(
            "test-real",
            metadata(
                source_hint="camera_export",
                exif_present=True,
                camera_make="Example",
                camera_model="Camera",
                created_time="2026:01:01 00:00:00",
            ),
            model(0.08, "likely_real", 0.1),
        )

        self.assertEqual(report["verdict"], "likely_real")
        self.assertEqual(report["risk_level"], "low")

    def test_report_exposes_scorecard_inputs_and_scores(self):
        report = build_image_report(
            "test-schema",
            metadata(),
            model(0.7, "ai_generated", 0.6),
        )

        decision = report["decision"]
        self.assertEqual(decision["policy_version"], "image-provenance-policy-v10")
        self.assertEqual(decision["mode"], "deterministic_evidence_scorecard")
        self.assertIn("primary_ai_score", decision["risk_inputs"])
        self.assertIn("ai_evidence_strength", decision["evidence_scores"])
        self.assertIn("conflict_score", decision["evidence_scores"])
        self.assertTrue(any(item["type"] == "evidence_fusion" for item in report["evidence"]))

    def test_embedded_aigc_metadata_can_form_medium_risk_without_model_support(self):
        report = build_image_report(
            "test-generator-metadata",
            metadata(
                format="png",
                generator_metadata_detected=True,
                generator_metadata_producers=["Example Generator"],
            ),
            model(0.05, "likely_real", 0.1),
        )

        self.assertEqual(report["verdict"], "ai_generated")
        self.assertEqual(report["risk_level"], "medium")
        self.assertIsNone(report["confidence"])
        self.assertEqual(report["decision"]["confidence_basis"], "embedded_generator_metadata_unverified")
        self.assertIn("embedded_generator_metadata_signal", report["decision"]["reasons"])

    def test_tc260_xmp_metadata_is_parsed_without_exposing_raw_payload(self):
        xmp = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            '<rdf:Description xmlns:TC260="http://www.tc260.org.cn/ns/AIGC/1.0/">'
            '<TC260:AIGC>{"Label":"1","ContentProducer":"doubao","ProduceID":"private-id"}</TC260:AIGC>'
            '</rdf:Description></rdf:RDF></x:xmpmeta>'
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "aigc.png"
            png_info = PngImagePlugin.PngInfo()
            png_info.add_text("XML:com.adobe.xmp", xmp)
            Image.new("RGB", (16, 16), "white").save(path, pnginfo=png_info)

            result = extract_image_metadata(path, path.name, path.stat().st_size)

        self.assertTrue(result["xmp_present"])
        self.assertTrue(result["generator_metadata_detected"])
        self.assertEqual(result["generator_metadata_producers"], ["Doubao"])
        self.assertNotIn("private-id", str(result))

    def test_editing_software_metadata_does_not_force_ai_verdict(self):
        report = build_image_report(
            "test-editor",
            metadata(editing_software_detected=True, editing_software_names=["Adobe Photoshop"]),
            model(0.08, "likely_real", 0.1),
        )

        self.assertEqual(report["verdict"], "likely_real")

    def test_invalid_primary_model_probability_fails_without_a_verdict(self):
        invalid_model = model(0.1, "likely_real")
        invalid_model["ai_score"] = float("nan")

        report = build_image_report("test-invalid-primary", metadata(), invalid_model)

        self.assertEqual(report["verdict"], "failed")
        self.assertEqual(report["risk_level"], "unknown")
        self.assertIsNone(report["confidence"])

    def test_invalid_auxiliary_model_degrades_instead_of_failing(self):
        model_result = model(0.08, "likely_real")
        model_result["auxiliary_models"] = [{
            "model_id": "aux-invalid",
            "model_version": "test",
            "ai_score": None,
            "real_score": None,
            "label": "likely_real",
            "error": None,
        }]

        report = build_image_report("test-invalid-aux", metadata(), model_result)

        self.assertEqual(report["verdict"], "likely_real")
        self.assertEqual(report["decision"]["quality"]["status"], "degraded")
        self.assertEqual(report["decision"]["quality"]["auxiliary_models_failed"], 1)
        self.assertTrue(report["models"][1]["error"])

    def test_pixel_limit_rejects_oversized_dimensions_before_model_call(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "large.png"
            Image.new("RGB", (64, 64), "white").save(path)
            with patch("unified_media_api.MAX_IMAGE_PIXELS", 1000):
                with self.assertRaises(OverflowError):
                    extract_image_metadata(path, path.name, path.stat().st_size)

    def test_process_task_removes_temporary_image_after_detection(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "temporary.png"
            Image.new("RGB", (16, 16), "white").save(path)
            model_result = model(0.08, "likely_real", 0.1)
            with patch("unified_media_api.call_ai_image_detector", return_value=model_result), \
                    patch("unified_media_api.save_report"), \
                    patch("unified_media_api.set_status"):
                process_task("test-cleanup", path, path.name, path.stat().st_size, "image", {})

            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
