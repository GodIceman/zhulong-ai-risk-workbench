import unittest
from types import SimpleNamespace

from scripts.eval_video_detection import calculate_video_release_gates


def gate_args():
    return SimpleNamespace(
        max_real_high_risk=0,
        max_deepfake_as_real=0,
        max_generated_as_real=0,
        max_errors=0,
        min_real_clear_rate=0.5,
        min_deepfake_clear_rate=0.5,
        min_generated_clear_rate=0.5,
        max_p95_latency_ms=30000,
    )


class VideoReleaseGateTests(unittest.TestCase):
    def test_balanced_clear_results_pass(self):
        rows = [
            {"label": "real", "actual_verdict": "likely_real", "elapsed_ms": 100},
            {"label": "deepfake", "actual_verdict": "deepfake_suspected", "elapsed_ms": 200},
            {"label": "ai_generated", "actual_verdict": "ai_generated", "elapsed_ms": 300},
        ]

        gates = calculate_video_release_gates(rows, gate_args())

        self.assertTrue(all(gate["passed"] for gate in gates))

    def test_all_uncertain_fails_coverage_gates(self):
        rows = [
            {"label": "real", "actual_verdict": "uncertain", "elapsed_ms": 100},
            {"label": "deepfake", "actual_verdict": "uncertain", "elapsed_ms": 200},
            {"label": "ai_generated", "actual_verdict": "uncertain", "elapsed_ms": 300},
        ]

        gates = {gate["name"]: gate for gate in calculate_video_release_gates(rows, gate_args())}

        self.assertFalse(gates["real_clear_rate"]["passed"])
        self.assertFalse(gates["deepfake_clear_rate"]["passed"])
        self.assertFalse(gates["generated_clear_rate"]["passed"])

    def test_cross_classification_fails_safety_gates(self):
        rows = [
            {"label": "real", "actual_verdict": "deepfake_suspected", "elapsed_ms": 100},
            {"label": "deepfake", "actual_verdict": "likely_real", "elapsed_ms": 200},
            {"label": "ai_generated", "actual_verdict": "likely_real", "elapsed_ms": 300},
        ]

        gates = {gate["name"]: gate for gate in calculate_video_release_gates(rows, gate_args())}

        self.assertFalse(gates["real_high_risk_count"]["passed"])
        self.assertFalse(gates["deepfake_as_real_count"]["passed"])
        self.assertFalse(gates["generated_as_real_count"]["passed"])


if __name__ == "__main__":
    unittest.main()
