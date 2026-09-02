import unittest

from unified_media_api import (
    build_image_report,
    build_image_risk_inputs,
    enrich_image_source_context,
)


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
    }
    value.update(overrides)
    return value


def model(ai_score, label, auxiliary_ai_score=None):
    value = {
        "model_id": "primary-test",
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
                "model_id": "auxiliary-test",
                "model_version": "test",
                "engine_type": "model",
                "ai_score": auxiliary_ai_score,
                "real_score": 1 - auxiliary_ai_score,
                "label": (
                    "ai_generated"
                    if auxiliary_ai_score >= 0.5
                    else "likely_real"
                ),
                "error": None,
            }
        )
    return value


class SourceHintPolicyTests(unittest.TestCase):
    def test_strong_auxiliary_ai_signal_cannot_be_upgraded_to_likely_real(self):
        model_result = model(0.08, "likely_real", auxiliary_ai_score=0.99)

        for source_hint in ("auto", "camera_export"):
            with self.subTest(source_hint=source_hint):
                report = build_image_report(
                    f"strong-aux-{source_hint}",
                    metadata(source_hint=source_hint),
                    model_result,
                )

                self.assertNotEqual(report["verdict"], "likely_real")

    def test_unverified_camera_export_declaration_cannot_upgrade_weak_provenance(self):
        model_result = model(0.08, "likely_real", auxiliary_ai_score=0.1)
        base_metadata = metadata(format="png", exif_present=False)

        automatic_report = build_image_report(
            "weak-provenance-auto",
            {**base_metadata, "source_hint": "auto"},
            model_result,
        )
        declared_camera_report = build_image_report(
            "weak-provenance-declared-camera",
            {**base_metadata, "source_hint": "camera_export"},
            model_result,
        )

        self.assertEqual(automatic_report["verdict"], "uncertain")
        self.assertEqual(declared_camera_report["verdict"], "uncertain")
        self.assertFalse(
            declared_camera_report["decision"]["risk_inputs"]["camera_provenance"]
        )

    def test_user_screen_or_game_declaration_can_only_force_abstention(self):
        model_result = model(0.98, "ai_generated", auxiliary_ai_score=0.99)
        automatic_report = build_image_report(
            "high-ai-auto",
            enrich_image_source_context(metadata(), {"source_hint": "auto"}),
            model_result,
        )
        self.assertEqual(automatic_report["verdict"], "ai_generated")

        for source_hint in ("screen_capture", "game_capture"):
            with self.subTest(source_hint=source_hint):
                declared_metadata = enrich_image_source_context(
                    metadata(),
                    {"source_hint": source_hint},
                )
                report = build_image_report(
                    f"protected-{source_hint}",
                    declared_metadata,
                    model_result,
                )

                self.assertEqual(report["verdict"], "uncertain")
                self.assertIsNone(report["confidence"])
                self.assertIn(
                    "protected_domain_overrides_ai_model_signal",
                    report["decision"]["reasons"],
                )

    def test_camera_provenance_is_derived_from_machine_metadata_not_user_hint(self):
        declared_only_inputs = build_image_risk_inputs(
            metadata(source_hint="camera_export"),
            model(0.08, "likely_real", auxiliary_ai_score=0.1),
        )
        machine_metadata_inputs = build_image_risk_inputs(
            metadata(
                source_hint="auto",
                exif_present=True,
                camera_make="Example Camera Corp.",
                camera_model="Example Camera",
                created_time="2026:01:01 00:00:00",
            ),
            model(0.08, "likely_real", auxiliary_ai_score=0.1),
        )

        self.assertFalse(declared_only_inputs["camera_provenance"])
        self.assertTrue(machine_metadata_inputs["camera_provenance"])


if __name__ == "__main__":
    unittest.main()
