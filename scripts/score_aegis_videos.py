#!/usr/bin/env python3
"""Evaluate the pinned AEGIS checkpoint on the local video manifest."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import average_precision_score, roc_auc_score


ROOT = Path(__file__).resolve().parents[1]
BRANCH_DIR = ROOT / "third_party" / "AEGIS" / "src" / "branches"
UTILS_DIR = ROOT / "third_party" / "AEGIS" / "src" / "utils"
sys.path.insert(0, str(BRANCH_DIR))
sys.path.insert(0, str(UTILS_DIR))

import pixel_branch  # noqa: E402
import timm  # noqa: E402


def _empty_dinov2_224():
    """The checkpoint contains the frozen backbone, so no second download is needed."""
    return timm.create_model(
        "vit_base_patch14_dinov2",
        pretrained=False,
        num_classes=0,
        global_pool="avg",
        img_size=224,
    )


pixel_branch._load_dinov2_224 = _empty_dinov2_224

from detector_model import VideoForensicsDetector  # noqa: E402
from video_io import load_video  # noqa: E402


AEGIS_MODEL_ID = "MusapYildiz/aegis-video-detector"
AEGIS_MODEL_REVISION = "95b71346cec650165e6ad3fb20ed9e80f4b6702a"
AEGIS_CODE_REVISION = "d86a774fd971954a023e1cd00ed7ff5b2575e0d1"
AEGIS_CHECKPOINT_SHA256 = "7df233979f9d3ef340e101d0d635a4d074577d43e6d1591d677cde31f80e44ba"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score videos with AEGIS")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "eval" / "video_manifest.csv",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=ROOT / "data" / "models" / "aegis" / "checkpoint_best.pt",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=ROOT / "logs" / "eval" / "aegis-scores.csv",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=ROOT / "logs" / "eval" / "aegis-summary.json",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--device", default="auto")
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

    device = torch.device(
        "cuda" if args.device == "auto" and torch.cuda.is_available()
        else "cpu" if args.device == "auto"
        else args.device
    )
    model = VideoForensicsDetector(freeze_dino=True).to(device)
    checkpoint = torch.load(args.checkpoint, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state"], strict=True)
    model.eval()

    results = []
    with torch.inference_mode():
        for index, item in enumerate(manifest, start=1):
            started = time.perf_counter()
            result = {**item}
            try:
                bundle = load_video(
                    str(ROOT / item["file_path"]),
                    n_frames=16,
                    n_semantic=8,
                    sampling="window",
                    target_dur=4.0,
                    random_start=False,
                )
                outputs = model(bundle.frames_all.unsqueeze(0).to(device))
                result.update(
                    score=float(outputs["ai_probability"].item()),
                    pixel_score=float(outputs["pixel_prob"].item()),
                    motion_score=float(outputs["motion_prob"].item()),
                    consistency_score=float(outputs["consistency_prob"].item()),
                    disagreement=float(outputs["disagreement"].item()),
                    smoothness=float(outputs["smoothness"].item()),
                    error="",
                )
            except Exception as exc:
                result.update(
                    score="",
                    pixel_score="",
                    motion_score="",
                    consistency_score="",
                    disagreement="",
                    smoothness="",
                    error=str(exc),
                )
            result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
            results.append(result)
            print(
                f"[{index:02d}/{len(manifest):02d}] {item['label']:<12} "
                f"{item['file_path']} score={result['score']} error={result['error']}",
                flush=True,
            )

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    usable = [row for row in results if not row["error"]]
    comparison = [
        row for row in usable if row["label"] in {"real", "ai_generated"}
    ]
    y_true = [1 if row["label"] == "ai_generated" else 0 for row in comparison]
    scores = [float(row["score"]) for row in comparison]
    thresholds = {}
    for threshold in (0.5, 0.8, 0.9, 0.95):
        thresholds[str(threshold)] = {
            label: sum(
                float(row["score"]) >= threshold
                for row in usable
                if row["label"] == label
            )
            for label in ("real", "deepfake", "ai_generated")
        }
    summary = {
        "generated_at": utc_now(),
        "model_id": AEGIS_MODEL_ID,
        "model_revision": AEGIS_MODEL_REVISION,
        "code_revision": AEGIS_CODE_REVISION,
        "checkpoint_sha256": AEGIS_CHECKPOINT_SHA256,
        "checkpoint_epoch": checkpoint.get("epoch"),
        "checkpoint_metrics": checkpoint.get("metrics"),
        "device": str(device),
        "frame_policy": "deterministic_center_16_frames_within_4_seconds",
        "sample_counts": Counter(row["label"] for row in usable),
        "ai_generated_vs_real_roc_auc": (
            float(roc_auc_score(y_true, scores)) if len(set(y_true)) == 2 else None
        ),
        "ai_generated_vs_real_average_precision": (
            float(average_precision_score(y_true, scores))
            if len(set(y_true)) == 2
            else None
        ),
        "positive_counts_by_threshold": thresholds,
        "errors": len(results) - len(usable),
        "average_latency_ms": (
            round(float(np.mean([row["elapsed_ms"] for row in usable])))
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
