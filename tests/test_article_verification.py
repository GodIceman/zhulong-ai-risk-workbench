import unittest
from unittest.mock import patch

from werkzeug.test import Client

import article_verification
import unified_media_api


ARTICLE_TEXT = """# 示例核查文章

某机构在 2025 年发布了 120 项标准。[1]
报告显示，该指标同比增长 18%。
我认为未来可能会继续增长。

[1] https://example.org/report?id=1&utm_source=test
重复链接：https://example.org/report?id=1
"""


class ImmediateThread:
    def __init__(self, target, args=(), daemon=None):
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self):
        self.target(*self.args)


def text_detection(label="uncertain", score=0.52):
    return {
        "model_id": "chinese-ai-text-detector",
        "model_version": "AnxForever/chinese-ai-detector-bert",
        "model_revision": "fixture",
        "engine_type": "model",
        "label": label,
        "score": score,
        "ai_signal_score": score,
        "classification_confidence": 0.75,
        "risk_level": (
            "high"
            if label == "ai_style_suspected"
            else "low"
            if label == "no_strong_ai_signal"
            else "unknown"
        ),
        "latency_ms": 25,
        "error": None,
        "segments": [{
            "segment_id": "text-segment-01",
            "text": "示例段落",
            "character_count": 100,
            "ai_signal_score": score,
            "signal_level": "mixed",
        }],
        "segment_count": 1,
        "analysis_coverage": 1.0,
        "strong_ai_segment_ratio": 0.0,
        "weak_ai_segment_ratio": 0.0,
        "decision_reasons": ["fixture"],
        "policy_version": "text-ai-style-policy-v1",
        "release_qualified": False,
    }


class ArticleVerificationTests(unittest.TestCase):
    def test_every_claim_span_points_to_exact_normalized_text(self):
        analysis = article_verification.analyze_article_text(ARTICLE_TEXT)

        self.assertGreater(analysis["material_claim_count"], 0)
        normalized = analysis["normalized_text"]
        for claim in analysis["claims"]:
            span = claim["source_span"]
            self.assertEqual(
                normalized[span["start"]:span["end"]],
                span["quote"],
            )

    def test_urls_are_canonicalized_and_deduplicated_without_fetching(self):
        analysis = article_verification.analyze_article_text(ARTICLE_TEXT)

        self.assertEqual(analysis["explicit_source_count"], 1)
        source = analysis["sources"][0]
        self.assertEqual(source["canonical_url"], "https://example.org/report?id=1")
        self.assertEqual(source["verification_status"], "not_fetched")
        self.assertEqual(len(source["occurrences"]), 2)

    def test_user_declared_origin_never_becomes_verified_provenance(self):
        analysis = article_verification.analyze_article_text(
            ARTICLE_TEXT,
            declared_url="https://publisher.example/story",
            declared_author="用户填写作者",
        )

        self.assertEqual(
            analysis["declared_origin"]["verification_status"],
            "unverified_user_declaration",
        )

    def test_opinion_or_prediction_is_out_of_scope(self):
        analysis = article_verification.analyze_article_text(
            "我认为未来可能会继续增长。"
        )

        self.assertEqual(analysis["material_claim_count"], 0)
        self.assertEqual(analysis["out_of_scope_claim_count"], 1)
        self.assertEqual(analysis["claims"][0]["assessment"], "out_of_scope")

    def test_reference_url_is_not_split_into_bogus_claims(self):
        analysis = article_verification.analyze_article_text(ARTICLE_TEXT)

        self.assertEqual(analysis["material_claim_count"], 2)
        self.assertEqual(analysis["out_of_scope_claim_count"], 1)
        claim_quotes = [
            claim["source_span"]["quote"] for claim in analysis["claims"]
        ]
        self.assertFalse(any("utm_source" in quote for quote in claim_quotes))
        self.assertFalse(any(quote.startswith("[1] http") for quote in claim_quotes))

    def test_offline_report_is_insufficient_evidence_not_article_truth(self):
        analysis = article_verification.analyze_article_text(ARTICLE_TEXT)
        report = unified_media_api.build_article_report(
            unified_media_api.create_task_id(),
            analysis,
            text_detection(),
        )

        self.assertEqual(report["verdict"], "uncertain")
        self.assertEqual(report["risk_level"], "unknown")
        self.assertIsNone(report["confidence"])
        self.assertEqual(report["decision"]["coverage"]["checked_claims"], 0)
        self.assertFalse(report["decision"]["quality"]["network_used"])
        self.assertNotIn("文章真实", report["summary"])
        self.assertNotIn("AI 写作概率", report["summary"])
        self.assertEqual(
            report["article"]["text_detection"]["label"],
            "uncertain",
        )

    def test_article_without_checkable_claims_has_no_checkable_claims_verdict(self):
        analysis = article_verification.analyze_article_text(
            "我认为未来可能会出现更好的结果。"
        )
        report = unified_media_api.build_article_report(
            unified_media_api.create_task_id(),
            analysis,
            text_detection("no_strong_ai_signal", 0.08),
        )

        self.assertEqual(report["verdict"], "no_strong_ai_signal")
        self.assertEqual(report["risk_level"], "low")
        self.assertIsNone(report["confidence"])

    def test_article_task_completes_even_when_evidence_is_insufficient(self):
        task_id = unified_media_api.create_task_id()
        article_input = {
            "text": article_verification.normalize_article_text(ARTICLE_TEXT),
            "title": "示例",
            "declared_url": "",
            "declared_author": "",
            "declared_published_at": "",
        }
        options = {
            "mode": "offline_inventory",
            "allow_network": False,
            "max_material_claims": 20,
        }

        with patch.object(unified_media_api, "TASKS", {}), patch.object(
            unified_media_api,
            "call_ai_text_detector",
            return_value=text_detection(),
        ):
            unified_media_api.process_article_task(task_id, article_input, options)
            task = unified_media_api.task_snapshot(task_id)

        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["report"]["verdict"], "uncertain")
        self.assertNotIn(ARTICLE_TEXT, str(task))

    def test_article_endpoint_rejects_network_and_invalid_input_before_task(self):
        client = Client(unified_media_api.app)

        empty_response = client.post(
            "/api/articles/verify",
            json={"input": {"kind": "text", "text": ""}},
        )
        network_response = client.post(
            "/api/articles/verify",
            json={
                "input": {"kind": "text", "text": ARTICLE_TEXT},
                "options": {
                    "mode": "online_verify",
                    "allow_network": False,
                },
            },
        )
        unavailable_response = client.post(
            "/api/articles/verify",
            json={
                "input": {"kind": "text", "text": ARTICLE_TEXT},
                "options": {
                    "mode": "online_verify",
                    "allow_network": True,
                },
            },
        )

        self.assertEqual(
            empty_response.get_json()["error"]["code"],
            "INVALID_ARTICLE_INPUT",
        )
        self.assertEqual(
            network_response.get_json()["error"]["code"],
            "NETWORK_NOT_ALLOWED",
        )
        self.assertEqual(unavailable_response.status_code, 503)
        self.assertEqual(
            unavailable_response.get_json()["error"]["code"],
            "NETWORK_VERIFIER_UNAVAILABLE",
        )

    def test_article_endpoint_creates_queryable_completed_report(self):
        client = Client(unified_media_api.app)
        with patch.object(
            unified_media_api,
            "call_ai_text_detector",
            return_value=text_detection("ai_style_suspected", 0.94),
        ), patch.object(unified_media_api, "TASKS", {}), patch.object(
            unified_media_api.threading,
            "Thread",
            ImmediateThread,
        ):
            created_response = client.post(
                "/api/articles/verify",
                json={
                    "input": {
                        "kind": "text",
                        "title": "接口契约样例",
                        "text": ARTICLE_TEXT,
                    },
                    "options": {
                        "mode": "offline_inventory",
                        "allow_network": False,
                        "max_material_claims": 20,
                    },
                },
            )
            task_id = created_response.get_json()["task_id"]
            status_response = client.get(f"/api/tasks/{task_id}")
            report_response = client.get(f"/api/tasks/{task_id}/report")

        self.assertEqual(created_response.status_code, 200)
        self.assertEqual(status_response.get_json()["status"], "completed")
        report = report_response.get_json()["report"]
        self.assertEqual(report["media_type"], "article")
        self.assertEqual(report["verdict"], "ai_style_suspected")
        self.assertEqual(report["risk_level"], "high")
        self.assertIsNone(report["confidence"])


if __name__ == "__main__":
    unittest.main()
