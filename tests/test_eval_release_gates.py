import unittest
from types import SimpleNamespace

from scripts.eval_media_detection import calculate_release_gates


def gate_args():
    return SimpleNamespace(
        min_safety_rate=1.0,
        max_real_as_ai=0,
        max_ai_as_real=0,
        max_errors=0,
        min_ai_clear_detection_rate=0.50,
        min_ai_non_metadata_clear_rate=0.50,
        max_overall_uncertain_rate=0.50,
        max_ai_uncertain_rate=0.50,
        max_real_uncertain_rate=0.50,
        min_camera_likely_real_rate=0.75,
        max_p95_latency_ms=5000,
    )


class ReleaseGateTests(unittest.TestCase):
    def test_safe_rows_pass_all_release_gates(self):
        manifest = [
            {"label": "real", "domain": "camera"},
            {"label": "ai_generated", "domain": "general"},
        ]
        rows = [
            {"pass": True, "actual_verdict": "likely_real", "elapsed_ms": 900},
            {
                "pass": True,
                "actual_verdict": "ai_generated",
                "generator_metadata_detected": False,
                "elapsed_ms": 1200,
            },
        ]

        gates = calculate_release_gates(rows, manifest, gate_args())

        self.assertTrue(all(gate["passed"] for gate in gates))

    def test_confident_cross_classification_fails_release_gates(self):
        manifest = [
            {"label": "real", "domain": "camera"},
            {"label": "ai_generated", "domain": "general"},
        ]
        rows = [
            {"pass": False, "actual_verdict": "ai_generated", "elapsed_ms": 900},
            {"pass": False, "actual_verdict": "likely_real", "elapsed_ms": 1200},
        ]

        gates = {gate["name"]: gate for gate in calculate_release_gates(rows, manifest, gate_args())}

        self.assertFalse(gates["product_safety_rate"]["passed"])
        self.assertFalse(gates["real_as_ai_count"]["passed"])
        self.assertFalse(gates["ai_as_real_count"]["passed"])
        self.assertFalse(gates["camera_likely_real_rate"]["passed"])

    def test_failed_detection_fails_error_gate(self):
        manifest = [{"label": "real", "domain": "camera"}]
        rows = [{"pass": False, "actual_verdict": "failed", "elapsed_ms": 700}]

        gates = {gate["name"]: gate for gate in calculate_release_gates(rows, manifest, gate_args())}

        self.assertEqual(gates["error_count"]["actual"], 1)
        self.assertFalse(gates["error_count"]["passed"])

    def test_slow_detection_fails_latency_gate(self):
        manifest = [{"label": "real", "domain": "camera"}]
        rows = [{"pass": True, "actual_verdict": "likely_real", "elapsed_ms": 6200}]

        gates = {gate["name"]: gate for gate in calculate_release_gates(rows, manifest, gate_args())}

        self.assertEqual(gates["p95_latency_ms"]["actual"], 6200)
        self.assertFalse(gates["p95_latency_ms"]["passed"])

    def test_all_uncertain_cannot_pass_as_safe_release(self):
        manifest = [
            {"label": "real", "domain": "camera"},
            {"label": "ai_generated", "domain": "general"},
        ]
        rows = [
            {"pass": True, "actual_verdict": "uncertain", "elapsed_ms": 700},
            {
                "pass": True,
                "actual_verdict": "uncertain",
                "generator_metadata_detected": False,
                "elapsed_ms": 800,
            },
        ]

        gates = {gate["name"]: gate for gate in calculate_release_gates(rows, manifest, gate_args())}

        self.assertTrue(gates["product_safety_rate"]["passed"])
        self.assertFalse(gates["ai_clear_detection_rate"]["passed"])
        self.assertFalse(gates["ai_non_metadata_clear_rate"]["passed"])
        self.assertFalse(gates["overall_uncertain_rate"]["passed"])
        self.assertFalse(gates["ai_uncertain_rate"]["passed"])
        self.assertFalse(gates["real_uncertain_rate"]["passed"])

    def test_metadata_only_ai_set_fails_non_metadata_coverage_gate(self):
        manifest = [
            {"label": "real", "domain": "camera"},
            {"label": "ai_generated", "domain": "general"},
        ]
        rows = [
            {"pass": True, "actual_verdict": "likely_real", "elapsed_ms": 700},
            {
                "pass": True,
                "actual_verdict": "ai_generated",
                "generator_metadata_detected": True,
                "elapsed_ms": 800,
            },
        ]

        gates = {gate["name"]: gate for gate in calculate_release_gates(rows, manifest, gate_args())}

        self.assertTrue(gates["ai_clear_detection_rate"]["passed"])
        self.assertEqual(gates["ai_non_metadata_clear_rate"]["actual"], "missing")
        self.assertFalse(gates["ai_non_metadata_clear_rate"]["passed"])

    def test_few_metadata_hits_do_not_hide_low_ai_coverage(self):
        manifest = [
            {"label": "real", "domain": "camera"},
            {"label": "ai_generated", "domain": "general"},
            {"label": "ai_generated", "domain": "general"},
            {"label": "ai_generated", "domain": "general"},
            {"label": "ai_generated", "domain": "general"},
        ]
        rows = [
            {"pass": True, "actual_verdict": "likely_real", "elapsed_ms": 700},
            {
                "pass": True,
                "actual_verdict": "ai_generated",
                "generator_metadata_detected": True,
                "elapsed_ms": 800,
            },
            {
                "pass": True,
                "actual_verdict": "uncertain",
                "generator_metadata_detected": False,
                "elapsed_ms": 800,
            },
            {
                "pass": True,
                "actual_verdict": "uncertain",
                "generator_metadata_detected": False,
                "elapsed_ms": 800,
            },
            {
                "pass": True,
                "actual_verdict": "uncertain",
                "generator_metadata_detected": False,
                "elapsed_ms": 800,
            },
        ]

        gates = {gate["name"]: gate for gate in calculate_release_gates(rows, manifest, gate_args())}

        self.assertEqual(gates["ai_clear_detection_rate"]["actual"], 0.25)
        self.assertFalse(gates["ai_clear_detection_rate"]["passed"])
        self.assertEqual(gates["ai_non_metadata_clear_rate"]["actual"], 0.0)
        self.assertFalse(gates["ai_non_metadata_clear_rate"]["passed"])
        self.assertEqual(gates["ai_uncertain_rate"]["actual"], 0.75)
        self.assertFalse(gates["ai_uncertain_rate"]["passed"])


if __name__ == "__main__":
    unittest.main()
