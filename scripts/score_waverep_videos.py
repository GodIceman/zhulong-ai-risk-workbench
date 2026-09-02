#!/usr/bin/env python3
"""Evaluate the pinned WaveRep branch on the local video manifest."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import video_face_api as api  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def rank_auc(negative_scores: list[float], positive_scores: list[float]) -> float | None:
    """Return pairwise ROC-AUC without adding scikit-learn to the runtime."""
    if not negative_scores or not positive_scores:
        return None
    wins = 0.0
    for positive in positive_scores:
        for negative in negative_scores:
            wins += 1.0 if positive > negative else 0.5 if positive == negative else 0.0
    return wins / (len(negative_scores) * len(positive_scores))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score videos with WaveRep G4")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "eval" / "video_manifest.csv",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=ROOT / "logs" / "eval" / "waverep-g4-scores.csv",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=ROOT / "logs" / "eval" / "waverep-g4-summary.json",
    )
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_csv = args.output_csv.resolve()
    args.output_json = args.output_json.resolve()
    manifest_path = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        manifest = list(csv.DictReader(handle))
    if args.limit:
        manifest = manifest[: args.limit]

    if not api.load_waverep_model():
        raise SystemExit(f"WaveRep load failed: {api.waverep_error}")

    results = []
    for index, item in enumerate(manifest, start=1):
        started = time.perf_counter()
        result = {**item}
        try:
            sample = api.read_video_sample(ROOT / item["file_path"])
            branch = api.analyze_waverep(sample)
            result.update(
                status=branch["status"],
                verdict=branch["verdict"],
                score=branch["score"],
                median_logit=branch["raw_median_logit"],
                positive_frame_ratio=branch["positive_frame_ratio"],
                error="",
            )
        except Exception as exc:
            result.update(
                status="failed",
                verdict="failed",
                score="",
                median_logit="",
                positive_frame_ratio="",
                error=str(exc),
            )
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
        results.append(result)
        print(
            f"[{index:02d}/{len(manifest):02d}] {item['label']:<12} "
            f"{item['file_path']} score={result['score']} status={result['status']}",
            flush=True,
        )

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    usable = [row for row in results if not row["error"]]
    groups = {
        label: [float(row["score"]) for row in usable if row["label"] == label]
        for label in ("real", "deepfake", "ai_generated")
    }
    warnings = Counter(
        row["label"] for row in usable if row["status"] == "positive"
    )
    summary = {
        "generated_at": utc_now(),
        "model_id": api.WAVEREP_MODEL_ID,
        "model_version": api.WAVEREP_MODEL_VERSION,
        "repository_revision": api.WAVEREP_REPOSITORY_REVISION,
        "weight_md5": api.WAVEREP_WEIGHT_MD5,
        "weight_sha256": api.WAVEREP_WEIGHT_SHA256 or None,
        "device": str(api.waverep_device),
        "frame_policy": {
            "frames": api.WAVEREP_FRAME_COUNT,
            "frame_logit_threshold": api.WAVEREP_FRAME_LOGIT_THRESHOLD,
            "minimum_positive_frame_ratio": api.WAVEREP_MIN_POSITIVE_FRAME_RATIO,
        },
        "sample_counts": Counter(row["label"] for row in usable),
        "positive_counts": dict(warnings),
        "ai_generated_vs_real_roc_auc": rank_auc(
            groups["real"],
            groups["ai_generated"],
        ),
        "errors": len(results) - len(usable),
        "average_latency_ms": (
            round(sum(float(row["elapsed_ms"]) for row in usable) / len(usable))
            if usable
            else None
        ),
        "scores_csv": str(args.output_csv.relative_to(ROOT)),
    }
    args.output_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=dict) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=dict))
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
