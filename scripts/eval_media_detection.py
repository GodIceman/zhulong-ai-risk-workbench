#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run the small media-detection regression manifest against the local API."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, TextIO

try:
    import requests
except ImportError:  # pragma: no cover - exercised only in an unprepared shell
    requests = None

try:
    from PIL import Image
except ImportError:  # pragma: no cover - evaluation can still run for normal files
    Image = None


TERMINAL_STATUSES = {"completed", "failed", "uncertain"}
LARGE_IMAGE_THRESHOLD_BYTES = 18 * 1024 * 1024
LARGE_IMAGE_MAX_EDGE = 2400
FIELDNAMES = [
    "file_path", "expected_verdict", "source_hint_used", "actual_verdict", "risk_level",
    "confidence", "model_score", "auxiliary_model_score", "decision_reasons",
    "policy_version", "ai_evidence_strength", "real_evidence_strength",
    "provenance_strength", "source_ambiguity", "conflict_score", "conflict_level",
    "generator_metadata_detected", "generator_metadata_producers",
    "editing_software_detected", "content_credentials_status",
    "elapsed_ms", "upload_path", "upload_name_used", "pass", "strict_pass", "summary",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate /api/media/analyze with a manifest CSV.")
    parser.add_argument("--manifest", default="eval/manifest.csv", help="Path to manifest CSV.")
    parser.add_argument("--base-url", default="http://127.0.0.1:5002", help="Unified media API base URL.")
    parser.add_argument("--output", default="", help="Optional output CSV path.")
    parser.add_argument("--summary-output", default="", help="Optional Markdown summary output path.")
    parser.add_argument("--timeout", type=int, default=180, help="Seconds to wait per task.")
    parser.add_argument(
        "--prepare-large-images",
        dest="prepare_large_images",
        action="store_true",
        default=True,
        help="Resize very large images before upload so eval measures model behavior, not upload limits.",
    )
    parser.add_argument(
        "--no-prepare-large-images",
        dest="prepare_large_images",
        action="store_false",
        help="Upload large images without preparing a smaller evaluation copy.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero unless actual verdict exactly matches expected_verdict.",
    )
    parser.add_argument(
        "--use-manifest-source-hints",
        action="store_true",
        help=(
            "Use source_hint values from the manifest. Disabled by default so "
            "release evaluation does not receive truth-correlated user declarations."
        ),
    )
    parser.add_argument(
        "--release-gate",
        action="store_true",
        help="Apply image-module release gates in addition to per-row safety checks.",
    )
    parser.add_argument("--min-safety-rate", type=float, default=1.0)
    parser.add_argument("--max-real-as-ai", type=int, default=0)
    parser.add_argument("--max-ai-as-real", type=int, default=0)
    parser.add_argument("--max-errors", type=int, default=0)
    parser.add_argument(
        "--min-ai-clear-detection-rate",
        type=float,
        default=0.50,
        help="Minimum share of labeled AI images receiving an ai_generated verdict.",
    )
    parser.add_argument(
        "--min-ai-non-metadata-clear-rate",
        type=float,
        default=0.50,
        help=(
            "Minimum ai_generated verdict rate among labeled AI images without "
            "embedded generator metadata. A release set with no such samples fails this gate."
        ),
    )
    parser.add_argument(
        "--max-overall-uncertain-rate",
        type=float,
        default=0.50,
        help="Maximum uncertain verdict rate across the complete release set.",
    )
    parser.add_argument(
        "--max-ai-uncertain-rate",
        type=float,
        default=0.50,
        help="Maximum uncertain verdict rate among labeled AI images.",
    )
    parser.add_argument(
        "--max-real-uncertain-rate",
        type=float,
        default=0.50,
        help="Maximum uncertain verdict rate among labeled real images.",
    )
    parser.add_argument("--min-camera-likely-real-rate", type=float, default=0.75)
    parser.add_argument("--max-p95-latency-ms", type=int, default=5000)
    return parser.parse_args()


def read_manifest(path: Path) -> Iterable[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def prepare_upload_file(file_path: Path, manifest_root: Path, enabled: bool) -> Path:
    if not enabled or file_path.stat().st_size <= LARGE_IMAGE_THRESHOLD_BYTES:
        return file_path
    if Image is None:
        return file_path

    digest = hashlib.sha1(str(file_path.resolve()).encode("utf-8")).hexdigest()[:12]
    prepared_dir = manifest_root / "logs" / "eval" / "prepared"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    prepared_path = prepared_dir / f"{file_path.stem}-{digest}.jpg"
    if prepared_path.exists():
        return prepared_path

    with Image.open(file_path) as image:
        image = image.convert("RGB")
        image.thumbnail((LARGE_IMAGE_MAX_EDGE, LARGE_IMAGE_MAX_EDGE), Image.Resampling.LANCZOS)
        image.save(prepared_path, format="JPEG", quality=90, optimize=True)
    return prepared_path


def upload(base_url: str, file_path: Path, source_hint: str, upload_name: Optional[str] = None) -> str:
    if requests is None:
        raise RuntimeError("Missing dependency: requests. Please run with .\\.venv-modern\\Scripts\\python.exe.")

    with file_path.open("rb") as handle:
        response = requests.post(
            f"{base_url}/api/media/analyze",
            files={"file": (upload_name or file_path.name, handle)},
            data={"options": json.dumps({"source_hint": source_hint}, ensure_ascii=False)},
            timeout=30,
        )
    if not response.ok:
        try:
            payload = response.json()
            error = payload.get("error") or {}
            if isinstance(error, dict):
                code = error.get("code") or f"HTTP {response.status_code}"
                message = error.get("message") or response.text
                raise RuntimeError(f"{code}: {message}")
            raise RuntimeError(str(error))
        except ValueError:
            pass
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError(payload.get("error") or "upload failed")
    return str(payload["task_id"])


def wait_for_report(base_url: str, task_id: str, timeout: int) -> Dict[str, Any]:
    if requests is None:
        raise RuntimeError("Missing dependency: requests. Please run with .\\.venv-modern\\Scripts\\python.exe.")

    deadline = time.time() + timeout
    while time.time() < deadline:
        status_response = requests.get(f"{base_url}/api/tasks/{task_id}", timeout=10)
        status_response.raise_for_status()
        status_payload = status_response.json()
        status = status_payload.get("status")
        if status in TERMINAL_STATUSES:
            report_response = requests.get(f"{base_url}/api/tasks/{task_id}/report", timeout=10)
            report_response.raise_for_status()
            return report_response.json()["report"]
        time.sleep(1)
    raise TimeoutError(f"task {task_id} timed out")


def extract_model_score(report: Dict[str, Any]) -> Optional[float]:
    for item in report.get("evidence") or []:
        if item.get("model_score") is not None:
            return float(item["model_score"])
    for model in report.get("models") or []:
        if model.get("ai_score") is not None:
            return float(model["ai_score"])
    return None


def extract_auxiliary_model_score(report: Dict[str, Any]) -> Optional[float]:
    scores = []
    for item in report.get("evidence") or []:
        if item.get("type") == "auxiliary_model_score" and item.get("model_score") is not None:
            scores.append(float(item["model_score"]))
    for model in report.get("models") or []:
        model_id = str(model.get("model_id") or "")
        if model_id.startswith("aux-") and model.get("ai_score") is not None:
            scores.append(float(model["ai_score"]))
    return max(scores) if scores else None


def row_passes(row: Dict[str, str], report: Dict[str, Any]) -> bool:
    expected = row.get("expected_verdict", "")
    label = row.get("label", "")
    domain = row.get("domain", "")
    verdict = report.get("verdict")
    risk_level = report.get("risk_level")
    if domain in {"game_capture", "screen_capture"}:
        return not (verdict == "ai_generated" and risk_level == "high")
    if label == "real":
        return verdict in {"likely_real", "uncertain"}
    if label == "ai_generated":
        return verdict in {"ai_generated", "uncertain"}
    if expected in {"uncertain", "likely_real", "ai_generated", "failed"}:
        return verdict == expected
    return not (verdict == "ai_generated" and risk_level == "high")


def row_strict_passes(row: Dict[str, str], report: Dict[str, Any]) -> bool:
    expected = row.get("expected_verdict", "")
    verdict = report.get("verdict")
    if expected in {"uncertain", "likely_real", "ai_generated", "failed"}:
        return verdict == expected
    return row_passes(row, report)


def evaluate_row(
    base_url: str,
    manifest_root: Path,
    row: Dict[str, str],
    timeout: int,
    prepare_large_images: bool,
    use_manifest_source_hints: bool,
) -> Dict[str, Any]:
    started_at = time.perf_counter()
    file_path = (manifest_root / row["file_path"]).resolve()
    expected = row.get("expected_verdict", "")
    source_hint = (row.get("source_hint") or "auto") if use_manifest_source_hints else "auto"
    if not file_path.exists():
        return {
            "file_path": row["file_path"],
            "expected_verdict": expected,
            "source_hint_used": source_hint,
            "actual_verdict": "missing_file",
            "risk_level": "",
            "confidence": "",
            "model_score": "",
            "auxiliary_model_score": "",
            "decision_reasons": "",
            "policy_version": "",
            "ai_evidence_strength": "",
            "real_evidence_strength": "",
            "provenance_strength": "",
            "source_ambiguity": "",
            "conflict_score": "",
            "conflict_level": "",
            "generator_metadata_detected": "",
            "generator_metadata_producers": "",
            "editing_software_detected": "",
            "content_credentials_status": "",
            "elapsed_ms": 0,
            "upload_path": "",
            "upload_name_used": "",
            "pass": False,
            "strict_pass": False,
            "summary": f"File not found: {file_path}",
        }

    try:
        upload_path = prepare_upload_file(file_path, manifest_root, prepare_large_images)
        upload_name = upload_path.name if use_manifest_source_hints else f"sample{upload_path.suffix.lower()}"
        task_id = upload(base_url, upload_path, source_hint, upload_name=upload_name)
        report = wait_for_report(base_url, task_id, timeout)
        model_score = extract_model_score(report)
        auxiliary_model_score = extract_auxiliary_model_score(report)
    except Exception as exc:
        return {
            "file_path": row["file_path"],
            "expected_verdict": expected,
            "source_hint_used": source_hint,
            "actual_verdict": "error",
            "risk_level": "",
            "confidence": "",
            "model_score": "",
            "auxiliary_model_score": "",
            "decision_reasons": "",
            "policy_version": "",
            "ai_evidence_strength": "",
            "real_evidence_strength": "",
            "provenance_strength": "",
            "source_ambiguity": "",
            "conflict_score": "",
            "conflict_level": "",
            "generator_metadata_detected": "",
            "generator_metadata_producers": "",
            "editing_software_detected": "",
            "content_credentials_status": "",
            "elapsed_ms": round((time.perf_counter() - started_at) * 1000),
            "upload_path": "",
            "upload_name_used": "",
            "pass": False,
            "strict_pass": False,
            "summary": str(exc),
        }

    decision = report.get("decision") or {}
    evidence_scores = decision.get("evidence_scores") or {}
    report_metadata = report.get("metadata") or {}
    return {
        "file_path": row["file_path"],
        "expected_verdict": expected,
        "source_hint_used": source_hint,
        "actual_verdict": report.get("verdict", ""),
        "risk_level": report.get("risk_level", ""),
        "confidence": report.get("confidence"),
        "model_score": "" if model_score is None else round(model_score, 4),
        "auxiliary_model_score": "" if auxiliary_model_score is None else round(auxiliary_model_score, 4),
        "decision_reasons": "|".join(decision.get("reasons") or []),
        "policy_version": decision.get("policy_version", ""),
        "ai_evidence_strength": evidence_scores.get("ai_evidence_strength", ""),
        "real_evidence_strength": evidence_scores.get("real_evidence_strength", ""),
        "provenance_strength": evidence_scores.get("provenance_strength", ""),
        "source_ambiguity": evidence_scores.get("source_ambiguity", ""),
        "conflict_score": evidence_scores.get("conflict_score", ""),
        "conflict_level": evidence_scores.get("conflict_level", ""),
        "generator_metadata_detected": report_metadata.get("generator_metadata_detected", ""),
        "generator_metadata_producers": "|".join(report_metadata.get("generator_metadata_producers") or []),
        "editing_software_detected": report_metadata.get("editing_software_detected", ""),
        "content_credentials_status": report_metadata.get("content_credentials_status", ""),
        "elapsed_ms": round((time.perf_counter() - started_at) * 1000),
        "upload_path": "" if upload_path == file_path else display_path(upload_path, manifest_root),
        "upload_name_used": upload_name,
        "pass": row_passes(row, report),
        "strict_pass": row_strict_passes(row, report),
        "summary": report.get("summary", ""),
    }


def write_results(rows: List[Dict[str, Any]], output: str) -> None:
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        handle: TextIO = output_path.open("w", encoding="utf-8", newline="")
    else:
        handle = sys.stdout

    try:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    finally:
        if output:
            handle.close()


def markdown_cell(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def is_true(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes"}


def calculate_coverage_metrics(
    rows: List[Dict[str, Any]],
    manifest_rows: List[Dict[str, str]],
) -> Dict[str, Any]:
    paired_rows = list(zip(manifest_rows, rows))
    ai_rows = [
        row for manifest_row, row in paired_rows
        if manifest_row.get("label") == "ai_generated"
    ]
    real_rows = [
        row for manifest_row, row in paired_rows
        if manifest_row.get("label") == "real"
    ]
    ai_non_metadata_rows = [
        row for row in ai_rows
        if not is_true(row.get("generator_metadata_detected"))
    ]

    def rate(count: int, denominator: int) -> Optional[float]:
        return count / denominator if denominator else None

    total_uncertain = sum(1 for row in rows if row["actual_verdict"] == "uncertain")
    ai_clear = sum(1 for row in ai_rows if row["actual_verdict"] == "ai_generated")
    ai_uncertain = sum(1 for row in ai_rows if row["actual_verdict"] == "uncertain")
    real_uncertain = sum(1 for row in real_rows if row["actual_verdict"] == "uncertain")
    ai_non_metadata_clear = sum(
        1 for row in ai_non_metadata_rows if row["actual_verdict"] == "ai_generated"
    )

    return {
        "total": len(rows),
        "total_uncertain": total_uncertain,
        "overall_uncertain_rate": rate(total_uncertain, len(rows)),
        "ai_total": len(ai_rows),
        "ai_clear": ai_clear,
        "ai_clear_detection_rate": rate(ai_clear, len(ai_rows)),
        "ai_uncertain": ai_uncertain,
        "ai_uncertain_rate": rate(ai_uncertain, len(ai_rows)),
        "ai_non_metadata_total": len(ai_non_metadata_rows),
        "ai_non_metadata_clear": ai_non_metadata_clear,
        "ai_non_metadata_clear_rate": rate(ai_non_metadata_clear, len(ai_non_metadata_rows)),
        "real_total": len(real_rows),
        "real_uncertain": real_uncertain,
        "real_uncertain_rate": rate(real_uncertain, len(real_rows)),
    }


def rate_gate(
    name: str,
    actual: Optional[float],
    threshold: float,
    minimum: bool,
) -> Dict[str, Any]:
    operator = ">=" if minimum else "<="
    return {
        "name": name,
        "actual": round(actual, 4) if actual is not None else "missing",
        "target": f"{operator}{threshold:.4f}",
        "passed": actual is not None and (
            actual >= threshold if minimum else actual <= threshold
        ),
    }


def calculate_release_gates(
    rows: List[Dict[str, Any]],
    manifest_rows: List[Dict[str, str]],
    args: argparse.Namespace,
) -> List[Dict[str, Any]]:
    total = len(rows)
    passed = sum(1 for row in rows if row["pass"] is True)
    real_as_ai = sum(
        1 for manifest_row, row in zip(manifest_rows, rows)
        if manifest_row.get("label") == "real" and row["actual_verdict"] == "ai_generated"
    )
    ai_as_real = sum(
        1 for manifest_row, row in zip(manifest_rows, rows)
        if manifest_row.get("label") == "ai_generated" and row["actual_verdict"] == "likely_real"
    )
    error_count = sum(
        1 for row in rows if row["actual_verdict"] in {"error", "failed", "missing_file"}
    )
    camera_rows = [
        row for manifest_row, row in zip(manifest_rows, rows)
        if manifest_row.get("domain") == "camera" and manifest_row.get("label") == "real"
    ]
    camera_likely_real = sum(1 for row in camera_rows if row["actual_verdict"] == "likely_real")
    latencies = sorted(
        int(row["elapsed_ms"])
        for row in rows
        if str(row.get("elapsed_ms") or "").isdigit() and int(row["elapsed_ms"]) > 0
    )
    p95_latency_ms = latencies[max(0, math.ceil(len(latencies) * 0.95) - 1)] if latencies else None
    safety_rate = passed / total if total else 0.0
    camera_likely_real_rate = camera_likely_real / len(camera_rows) if camera_rows else 0.0
    coverage = calculate_coverage_metrics(rows, manifest_rows)

    return [
        {
            "name": "product_safety_rate",
            "actual": round(safety_rate, 4),
            "target": f">={args.min_safety_rate:.4f}",
            "passed": safety_rate >= args.min_safety_rate,
        },
        {
            "name": "real_as_ai_count",
            "actual": real_as_ai,
            "target": f"<={args.max_real_as_ai}",
            "passed": real_as_ai <= args.max_real_as_ai,
        },
        {
            "name": "ai_as_real_count",
            "actual": ai_as_real,
            "target": f"<={args.max_ai_as_real}",
            "passed": ai_as_real <= args.max_ai_as_real,
        },
        {
            "name": "error_count",
            "actual": error_count,
            "target": f"<={args.max_errors}",
            "passed": error_count <= args.max_errors,
        },
        rate_gate(
            "ai_clear_detection_rate",
            coverage["ai_clear_detection_rate"],
            args.min_ai_clear_detection_rate,
            minimum=True,
        ),
        rate_gate(
            "ai_non_metadata_clear_rate",
            coverage["ai_non_metadata_clear_rate"],
            args.min_ai_non_metadata_clear_rate,
            minimum=True,
        ),
        rate_gate(
            "overall_uncertain_rate",
            coverage["overall_uncertain_rate"],
            args.max_overall_uncertain_rate,
            minimum=False,
        ),
        rate_gate(
            "ai_uncertain_rate",
            coverage["ai_uncertain_rate"],
            args.max_ai_uncertain_rate,
            minimum=False,
        ),
        rate_gate(
            "real_uncertain_rate",
            coverage["real_uncertain_rate"],
            args.max_real_uncertain_rate,
            minimum=False,
        ),
        {
            "name": "camera_likely_real_rate",
            "actual": round(camera_likely_real_rate, 4),
            "target": f">={args.min_camera_likely_real_rate:.4f}",
            "passed": camera_likely_real_rate >= args.min_camera_likely_real_rate,
        },
        {
            "name": "p95_latency_ms",
            "actual": p95_latency_ms if p95_latency_ms is not None else "missing",
            "target": f"<={args.max_p95_latency_ms}",
            "passed": p95_latency_ms is not None and p95_latency_ms <= args.max_p95_latency_ms,
        },
    ]


def write_markdown_summary(
    rows: List[Dict[str, Any]],
    manifest_rows: List[Dict[str, str]],
    output: str,
    release_gates: Optional[List[Dict[str, Any]]] = None,
) -> None:
    if not output:
        return

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = len(rows)
    passed = sum(1 for row in rows if row["pass"] is True)
    strict_passed = sum(1 for row in rows if row["strict_pass"] is True)
    uncertain = sum(1 for row in rows if row["actual_verdict"] == "uncertain")
    real_as_ai = sum(
        1 for manifest_row, row in zip(manifest_rows, rows)
        if manifest_row.get("label") == "real" and row["actual_verdict"] == "ai_generated"
    )
    ai_as_real = sum(
        1 for manifest_row, row in zip(manifest_rows, rows)
        if manifest_row.get("label") == "ai_generated" and row["actual_verdict"] == "likely_real"
    )
    generator_metadata_count = sum(
        1 for row in rows if str(row.get("generator_metadata_detected")).lower() == "true"
    )
    coverage = calculate_coverage_metrics(rows, manifest_rows)

    verdict_counts = Counter(row["actual_verdict"] for row in rows)
    by_domain: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0, "strict": 0})
    for manifest_row, result_row in zip(manifest_rows, rows):
        domain = manifest_row.get("domain") or "unknown"
        by_domain[domain]["total"] += 1
        by_domain[domain]["passed"] += int(result_row["pass"] is True)
        by_domain[domain]["strict"] += int(result_row["strict_pass"] is True)

    lines = [
        "# 烛龙图片检测回归报告",
        "",
        f"> 生成时间：{datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}",
        "",
        "## 核心结果",
        "",
        "| 指标 | 结果 |",
        "| --- | ---: |",
        f"| 产品安全通过 | {passed}/{total} |",
        f"| 严格结论匹配 | {strict_passed}/{total} |",
        f"| 真实图片误判为 AI | {real_as_ai} |",
        f"| AI 图片误判为真实 | {ai_as_real} |",
        f"| 检测到嵌入式生成来源线索 | {generator_metadata_count} |",
        f"| 无法确认 | {uncertain}/{total} |",
        f"| AI 明确检出 | {coverage['ai_clear']}/{coverage['ai_total']} |",
        f"| 无生成元数据 AI 明确检出 | "
        f"{coverage['ai_non_metadata_clear']}/{coverage['ai_non_metadata_total']} |",
        f"| AI 无法确认 | {coverage['ai_uncertain']}/{coverage['ai_total']} |",
        f"| 真实图片无法确认 | {coverage['real_uncertain']}/{coverage['real_total']} |",
        "",
        "## 结论分布",
        "",
        "| 结论 | 数量 |",
        "| --- | ---: |",
    ]
    for verdict in sorted(verdict_counts):
        lines.append(f"| {markdown_cell(verdict)} | {verdict_counts[verdict]} |")

    if release_gates is not None:
        lines.extend(["", "## 发布门槛", "", "| 门槛 | 实际 | 目标 | 结果 |", "| --- | ---: | ---: | --- |"])
        for gate in release_gates:
            lines.append(
                f"| {markdown_cell(gate['name'])} | {markdown_cell(gate['actual'])} | "
                f"{markdown_cell(gate['target'])} | {'通过' if gate['passed'] else '失败'} |"
            )

    lines.extend(["", "## 来源域表现", "", "| 来源域 | 产品安全 | 严格匹配 |", "| --- | ---: | ---: |"])
    for domain in sorted(by_domain):
        item = by_domain[domain]
        lines.append(
            f"| {markdown_cell(domain)} | {item['passed']}/{item['total']} | {item['strict']}/{item['total']} |"
        )

    mismatches = [row for row in rows if row["strict_pass"] is not True]
    lines.extend([
        "",
        "## 严格不匹配样本",
        "",
        "| 文件 | 期望 | 实际 | AI 证据 | 真实证据 | 冲突度 | 决策原因 |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ])
    if mismatches:
        for row in mismatches:
            lines.append(
                f"| {markdown_cell(row['file_path'])} | {markdown_cell(row['expected_verdict'])} | "
                f"{markdown_cell(row['actual_verdict'])} | {markdown_cell(row['ai_evidence_strength'])} | "
                f"{markdown_cell(row['real_evidence_strength'])} | {markdown_cell(row['conflict_score'])} | "
                f"{markdown_cell(row['decision_reasons'])} |"
            )
    else:
        lines.append("| - | - | - | - | - | - | 无 |")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_summary(rows: List[Dict[str, Any]], manifest_rows: List[Dict[str, str]], output: str) -> None:
    stream = sys.stdout if output else sys.stderr
    total = len(rows)
    passed = sum(1 for row in rows if row["pass"] is True)
    strict_passed = sum(1 for row in rows if row["strict_pass"] is True)
    failed = total - passed
    strict_failed = total - strict_passed
    print("", file=stream)
    print(f"Total: {total}", file=stream)
    print(f"Passed: {passed}", file=stream)
    print(f"Failed: {failed}", file=stream)
    print(f"Strict matched: {strict_passed}", file=stream)
    print(f"Strict mismatched: {strict_failed}", file=stream)

    by_domain: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0})
    for manifest_row, result_row in zip(manifest_rows, rows):
        domain = manifest_row.get("domain") or "unknown"
        by_domain[domain]["total"] += 1
        if result_row["pass"] is True:
            by_domain[domain]["passed"] += 1

    if by_domain:
        print("", file=stream)
        print("By domain:", file=stream)
        for domain in sorted(by_domain):
            item = by_domain[domain]
            print(f"- {domain}: {item['passed']}/{item['total']}", file=stream)

    failed_rows = [row for row in rows if row["pass"] is not True]
    if failed_rows:
        print("", file=stream)
        print("Failed samples:", file=stream)
        for row in failed_rows:
            print(
                f"- {row['file_path']}: actual={row['actual_verdict']} "
                f"risk={row['risk_level']} summary={row['summary']}",
                file=stream,
            )

    strict_failed_rows = [row for row in rows if row["strict_pass"] is not True]
    if strict_failed_rows:
        print("", file=stream)
        print("Strict mismatches:", file=stream)
        for row in strict_failed_rows:
            print(
                f"- {row['file_path']}: expected={row['expected_verdict']} "
                f"actual={row['actual_verdict']} reason={row['decision_reasons']}",
                file=stream,
            )


def print_release_gates(release_gates: List[Dict[str, Any]], output: str) -> None:
    stream = sys.stdout if output else sys.stderr
    print("", file=stream)
    print("Release gates:", file=stream)
    for gate in release_gates:
        status = "PASS" if gate["passed"] else "FAIL"
        print(
            f"- [{status}] {gate['name']}: actual={gate['actual']} target={gate['target']}",
            file=stream,
        )

def warn_if_images_dir_missing(manifest_path: Path) -> None:
    images_dir = manifest_path.parent / "images"
    if not images_dir.exists():
        print(
            f"Notice: {images_dir} does not exist. Add golden-set images there; missing samples are reported as missing_file.",
            file=sys.stderr,
        )


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest).resolve()
    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}", file=sys.stderr)
        return 2

    if requests is None:
        print("Missing dependency: requests. Please run with .\\.venv-modern\\Scripts\\python.exe.", file=sys.stderr)
        return 2

    warn_if_images_dir_missing(manifest_path)
    manifest_root = manifest_path.parent.parent if manifest_path.parent.name == "eval" else Path.cwd()
    manifest_rows = list(read_manifest(manifest_path))
    rows = [
        evaluate_row(
            args.base_url.rstrip("/"),
            manifest_root,
            row,
            args.timeout,
            args.prepare_large_images,
            args.use_manifest_source_hints,
        )
        for row in manifest_rows
    ]
    release_gates = calculate_release_gates(rows, manifest_rows, args) if args.release_gate else None
    write_results(rows, args.output)
    write_markdown_summary(rows, manifest_rows, args.summary_output, release_gates)
    print_summary(rows, manifest_rows, args.output)
    if release_gates is not None:
        print_release_gates(release_gates, args.output)

    rows_pass = all(row["strict_pass" if args.strict else "pass"] for row in rows)
    gates_pass = release_gates is None or all(gate["passed"] for gate in release_gates)
    return 0 if rows_pass and gates_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
