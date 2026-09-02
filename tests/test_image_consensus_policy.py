import unittest

from unified_media_api import build_image_report, enrich_image_source_context


def metadata(**overrides):
    value = {
        "filename": "sample.jpg",
        "file_size": 1024,
        "format": "jpeg",
        "width": 1024,
        "height": 768,
        "exif_present": False,
        "camera_make": None,
        "camera_model": None,
        "created_time": None,
        "source_hint": "auto",
        "protected_domain": False,
        "screen_capture_likely": False,
        "generator_metadata_detected": False,
        "generator_metadata_producers": [],
    }
    value.update(overrides)
    return value


def model(ai_score, label, auxiliary_ai_score=None):
    value = {
        "model_id": "primary-consensus-test",
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
        value["auxiliary_models"].append(
            {
                "model_id": "auxiliary-consensus-test",
                "model_version": "test",
                "engine_type": "model",
                "ai_score": auxiliary_ai_score,
                "real_score": 1 - auxiliary_ai_score,
                "score": (
                    auxiliary_ai_score
                    if auxiliary_ai_score >= 0.5
                    else 1 - auxiliary_ai_score
                ),
                "label": (
                    "ai_generated"
                    if auxiliary_ai_score >= 0.5
                    else "likely_real"
                ),
                "error": None,
            }
        )
    return value


class ImageConsensusPolicyTests(unittest.TestCase):
    def test_calibrated_primary_model_can_form_ai_generated_verdict(self):
        report = build_image_report(
            "primary-only-strong-ai",
            metadata(),
            model(0.96, "ai_generated"),
        )

        self.assertEqual(report["verdict"], "ai_generated")
        self.assertEqual(report["risk_level"], "high")
        self.assertEqual(report["confidence"], 0.96)
        self.assertIn("calibrated_primary_ai_signal", report["decision"]["reasons"])

    def test_auxiliary_model_alone_cannot_form_ai_generated_verdict(self):
        report = build_image_report(
            "auxiliary-only-strong-ai",
            metadata(
                filename="small-raster.png",
                format="png",
                width=1024,
                height=768,
            ),
            model(0.1, "likely_real", auxiliary_ai_score=0.99),
        )

        self.assertEqual(report["verdict"], "uncertain")
        self.assertEqual(report["risk_level"], "unknown")
        self.assertIsNone(report["confidence"])

    def test_display_sized_png_without_exif_is_automatically_protected(self):
        for width, height in ((1366, 768), (1920, 1080), (2560, 1440)):
            with self.subTest(resolution=f"{width}x{height}"):
                source_context = enrich_image_source_context(
                    metadata(
                        filename=f"image-{width}x{height}.png",
                        format="png",
                        width=width,
                        height=height,
                        exif_present=False,
                    ),
                    {"source_hint": "auto"},
                )
                report = build_image_report(
                    f"display-png-{width}x{height}",
                    source_context,
                    model(0.98, "ai_generated", auxiliary_ai_score=0.99),
                )

                self.assertEqual(
                    (
                        source_context["protected_domain"],
                        report["decision"]["risk_inputs"]["protected_domain"],
                        report["verdict"],
                        report["risk_level"],
                    ),
                    (True, True, "uncertain", "unknown"),
                )

    def test_non_protected_consensus_can_form_high_risk_ai_verdict(self):
        source_context = enrich_image_source_context(
            metadata(
                filename="ordinary-photo.jpg",
                format="jpeg",
                width=1024,
                height=768,
            ),
            {"source_hint": "auto"},
        )
        report = build_image_report(
            "non-protected-consensus",
            source_context,
            model(0.9, "ai_generated", auxiliary_ai_score=0.95),
        )

        self.assertFalse(report["decision"]["risk_inputs"]["protected_domain"])
        self.assertEqual(report["verdict"], "ai_generated")
        self.assertEqual(report["risk_level"], "high")

    def test_explicit_generator_metadata_can_form_medium_risk_verdict(self):
        report = build_image_report(
            "explicit-generator-metadata",
            metadata(
                filename="display-sized.png",
                format="png",
                width=1920,
                height=1080,
                protected_domain=True,
                screen_capture_likely=True,
                generator_metadata_detected=True,
                generator_metadata_producers=["Example Generator"],
            ),
            model(0.05, "likely_real", auxiliary_ai_score=0.1),
        )

        self.assertEqual(report["verdict"], "ai_generated")
        self.assertEqual(report["risk_level"], "medium")
        self.assertIsNone(report["confidence"])
        self.assertIn(
            "embedded_generator_metadata_signal",
            report["decision"]["reasons"],
        )


if __name__ == "__main__":
    unittest.main()
