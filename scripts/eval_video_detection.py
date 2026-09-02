#!/usr/bin/env python3
"""Evaluate video detectors against eval/video_manifest.csv.

The evaluator supports the legacy detector API and the unified product API. It
separates safety (avoiding confident cross-classification) from useful coverage
(forming enough correct, explicit conclusions).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import mimetypes
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

try:
    import requests
except ImportError as exc:  # pragma: no cover - actionable CLI failure
    raise SystemExit("缺少 requests，请使用项目 .venv-modern 环境运行。") from exc


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "eval" / "video_manifest.csv"
DEFAULT_CSV = ROOT / "logs" / "eval" / "video-latest.csv"
DEFAULT_MD = ROOT / "logs" / "eval" / "video-latest.md"

HIGH_RISK_VERDICTS = {
    "fake",
    "deepfake_suspected",
    "ai_generated",
    "manipulated_suspected",
    "ai_generated_video_suspected",
    "face_manipulation_suspected",
    "multiple_video_ai_signals",
}
REAL_VERDICTS = {"real", "likely_real"}
UNKNOWN_VERDICTS = {"uncertain", "failed", "error"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def percentile(values: Sequence[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    rank = max(0, math.ceil((percentile_value / 100) * len(ordered)) - 1)
    return ordered[rank]


def load_manifest(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"file_path", "label", "source"}
    missing = required.difference(rows[0].keys() if rows else set())
    if missing:
        raise ValueError(f"视频 manifest 缺少字段: {', '.join(sorted(missing))}")
    return rows


def normalize_legacy_response(data: Dict[str, Any]) -> Dict[str, Any]:
    if not data.get("success"):
        return {"verdict": "failed", "score": None, "error": data.get("error") or "legacy detector failed"}
    raw_verdict = str(data.get("verdict") or "").lower()
    verdict = "deepfake_suspected" if raw_verdict == "fake" else "likely_real" if raw_verdict == "real" else "uncertain"
    score = data.get("confidence")
    return {
        "verdict": verdict,
        "score": None if score is None else float(score) / 100,
        "error": None,
        "raw_fake_percentage": (data.get("statistics") or {}).get("fake_percentage"),
    }


def call_legacy(endpoint: str, path: Path, timeout: float) -> Dict[str, Any]:
    with path.open("rb") as handle:
        response = requests.post(
            endpoint,
            files={"video": (path.name, handle, mimetypes.guess_type(path.name)[0] or "video/mp4")},
            timeout=timeout,
        )
    data = response.json() if response.content else {}
    if not response.ok:
        return {"verdict": "failed", "score": None, "error": data.get("error") or f"HTTP {response.status_code}"}
    return normalize_legacy_response(data)


def call_standard(endpoint: str, path: Path, timeout: float) -> Dict[str, Any]:
    with path.open("rb") as handle:
        response = requests.post(
            endpoint,
            files={"video": (path.name, handle, mimetypes.guess_type(path.name)[0] or "video/mp4")},
            timeout=timeout,
        )
    data = response.json() if response.content else {}
    if not response.ok or data.get("success") is False:
        return {"verdict": "failed", "score": None, "error": data.get("error") or f"HTTP {response.status_code}"}
    score = data.get("score", data.get("confidence"))
    return {
        "verdict": str(data.get("verdict") or "uncertain"),
        "score": None if score is None else float(score),
        "error": data.get("error"),
    }


def call_unified(base_url: str, path: Path, timeout: float) -> Dict[str, Any]:
    with path.open("rb") as handle:
        response = requests.post(
            f"{base_url.rstrip('/')}/api/media/analyze",
            files={"file": (path.name, handle, mimetypes.guess_type(path.name)[0] or "video/mp4")},
            timeout=min(timeout, 30),
        )
    created = response.json() if response.content else {}
    if not response.ok or not created.get("task_id"):
        return {"verdict": "failed", "score": None, "error": created.get("error") or f"HTTP {response.status_code}"}

    task_id = created["task_id"]
    deadline = time.monotonic() + timeout
    status = "received"
    while time.monotonic() < deadline:
        status_response = requests.get(f"{base_url.rstrip('/')}/api/tasks/{task_id}", timeout=10)
        payload = status_response.json() if status_response.content else {}
        status = payload.get("status") or status
        if status in {"completed", "uncertain", "failed"}:
            break
        time.sleep(0.5)
    else:
        return {"verdict": "failed", "score": None, "error": "unified task timeout"}

    report_response = requests.get(f"{base_url.rstrip('/')}/api/tasks/{task_id}/report", timeout=10)
    payload = report_response.json() if report_response.content else {}
    report = payload.get("report") or {}
    models = report.get("models") or []
    score = models[0].get("score") if models else report.get("confidence")
    return {
        "verdict": report.get("verdict") or "failed",
        "score": score,
        "error": models[0].get("error") if models else None,
    }


def evaluate_safety(expected_label: str, verdict: str) -> bool:
    if expected_label == "real":
        return verdict not in HIGH_RISK_VERDICTS and verdict not in {"failed", "error"}
    return verdict not in REAL_VERDICTS and verdict not in {"failed", "error"}


def evaluate_strict(expected_label: str, verdict: str) -> bool:
    if expected_label == "real":
        return verdict == "likely_real"
    if expected_label == "deepfake":
        return verdict in {
            "deepfake_suspected",
            "face_manipulation_suspected",
            "multiple_video_ai_signals",
        }
    if expected_label == "ai_generated":
        return verdict in {
            "ai_generated",
            "ai_generated_video_suspected",
            "multiple_video_ai_signals",
        }
    return False


def calculate_video_release_gates(rows: Sequence[Dict[str, Any]], args: argparse.Namespace) -> List[Dict[str, Any]]:
    counts = Counter()
    totals = Counter()
    clear = Counter()
    latencies: List[float] = []

    for row in rows:
        label = row["label"]
        verdict = row["actual_verdict"]
        totals[label] += 1
        latencies.append(float(row.get("elapsed_ms") or 0))
        if verdict in {"failed", "error"}:
            counts["errors"] += 1
        if label == "real" and verdict in HIGH_RISK_VERDICTS:
            counts["real_high_risk"] += 1
        if label == "deepfake" and verdict in REAL_VERDICTS:
            counts["deepfake_as_real"] += 1
        if label == "ai_generated" and verdict in REAL_VERDICTS:
            counts["generated_as_real"] += 1
        if evaluate_strict(label, verdict):
            clear[label] += 1

    def rate(label: str) -> float:
        return clear[label] / totals[label] if totals[label] else 0.0

    gate_values = [
        ("real_high_risk_count", counts["real_high_risk"], args.max_real_high_risk, "max"),
        ("deepfake_as_real_count", counts["deepfake_as_real"], args.max_deepfake_as_real, "max"),
        ("generated_as_real_count", counts["generated_as_real"], args.max_generated_as_real, "max"),
        ("error_count", counts["errors"], args.max_errors, "max"),
        ("real_clear_rate", round(rate("real"), 4), args.min_real_clear_rate, "min"),
        ("deepfake_clear_rate", round(rate("deepfake"), 4), args.min_deepfake_clear_rate, "min"),
        ("generated_clear_rate", round(rate("ai_generated"), 4), args.min_generated_clear_rate, "min"),
        ("p95_latency_ms", round(percentile(latencies, 95)), args.max_p95_latency_ms, "max"),
    ]
    return [
        {
            "name": name,
            "actual": actual,
            "target": target,
            "passed": actual <= target if direction == "max" else actual >= target,
            "direction": direction,
        }
        for name, actual, target, direction in gate_values
    ]


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "file_path", "label", "attack_type", "source", "actual_verdict", "score",
        "elapsed_ms", "safety_pass", "strict_pass", "error",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, rows: Sequence[Dict[str, Any]], gates: Sequence[Dict[str, Any]], backend: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["label"]].append(row)

    lines = [
        "# 烛龙视频检测评测报告",
        "",
        f"> 生成时间：{utc_now()}",
        f"> 后端：{backend}",
        "",
        "## 类别结果",
        "",
        "| 类别 | 样本 | 安全通过 | 严格识别 | 无法确认 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for label in ("real", "deepfake", "ai_generated"):
        items = grouped.get(label, [])
        lines.append(
            f"| {label} | {len(items)} | {sum(bool(row['safety_pass']) for row in items)}/{len(items)} "
            f"| {sum(bool(row['strict_pass']) for row in items)}/{len(items)} "
            f"| {sum(row['actual_verdict'] == 'uncertain' for row in items)} |"
        )

    lines.extend(["", "## 发布门禁", "", "| 门禁 | 实际 | 目标 | 结果 |", "| --- | ---: | ---: | --- |"])
    for gate in gates:
        operator = "<=" if gate["direction"] == "max" else ">="
        lines.append(
            f"| {gate['name']} | {gate['actual']} | {operator}{gate['target']} | {'通过' if gate['passed'] else '失败'} |"
        )
    failed = [row for row in rows if not row["safety_pass"] or row["error"]]
    lines.extend(["", "## 安全失败样本", ""])
    if not failed:
        lines.append("无。")
    else:
        lines.extend(["| 文件 | 标签 | 实际 | 错误 |", "| --- | --- | --- | --- |"])
        for row in failed:
            lines.append(f"| {row['file_path']} | {row['label']} | {row['actual_verdict']} | {row['error'] or ''} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Zhulong video detectors")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--backend", choices=("legacy", "standard", "unified"), default="legacy")
    parser.add_argument("--endpoint", default="http://127.0.0.1:5003/api/deepfake/video")
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--max-real-high-risk", type=int, default=0)
    parser.add_argument("--max-deepfake-as-real", type=int, default=2)
    parser.add_argument("--max-generated-as-real", type=int, default=3)
    parser.add_argument("--max-errors", type=int, default=0)
    parser.add_argument("--min-real-clear-rate", type=float, default=0.5)
    parser.add_argument("--min-deepfake-clear-rate", type=float, default=0.7)
    parser.add_argument("--min-generated-clear-rate", type=float, default=0.5)
    parser.add_argument("--max-p95-latency-ms", type=float, default=30000)
    parser.add_argument("--no-fail-on-gates", action="store_true")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    manifest_path = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    rows: List[Dict[str, Any]] = []
    manifest = load_manifest(manifest_path)
    caller = {"legacy": call_legacy, "standard": call_standard, "unified": call_unified}[args.backend]

    for index, item in enumerate(manifest, start=1):
        path = ROOT / item["file_path"]
        print(f"[{index}/{len(manifest)}] {item['file_path']}", flush=True)
        start = time.perf_counter()
        if not path.exists():
            result = {"verdict": "error", "score": None, "error": "missing_file"}
        else:
            try:
                result = caller(args.endpoint, path, args.timeout)
            except Exception as exc:  # keep the full evaluation running
                result = {"verdict": "error", "score": None, "error": str(exc)}
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        verdict = str(result.get("verdict") or "error")
        rows.append({
            **item,
            "actual_verdict": verdict,
            "score": result.get("score"),
            "elapsed_ms": elapsed_ms,
            "safety_pass": evaluate_safety(item["label"], verdict),
            "strict_pass": evaluate_strict(item["label"], verdict),
            "error": result.get("error"),
        })

    gates = calculate_video_release_gates(rows, args)
    write_csv(args.output_csv, rows)
    write_markdown(args.output_md, rows, gates, args.backend)
    print(json.dumps({"gates": gates}, ensure_ascii=False, indent=2))
    passed = all(gate["passed"] for gate in gates)
    print(f"Release gates: {'PASS' if passed else 'FAIL'}")
    return 0 if passed or args.no_fail_on_gates else 1


if __name__ == "__main__":
    sys.exit(main())
