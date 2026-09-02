#!/usr/bin/env python3
"""Score the local video evaluation set with the training-free D3 detector.

This is a candidate-model harness, not a production decision API.  It reads
MP4 files directly, reproduces D3's 16-frame/ImageNet preprocessing, and
writes raw second-order temporal feature scores for later calibration.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
import torch
from sklearn.metrics import average_precision_score, roc_auc_score


ROOT = Path(__file__).resolve().parents[1]
THIRD_PARTY_D3 = ROOT / "third_party" / "D3"
sys.path.insert(0, str(THIRD_PARTY_D3))

from models import D3_model  # noqa: E402


MEAN = np.asarray((0.485, 0.456, 0.406), dtype=np.float32)
STD = np.asarray((0.229, 0.224, 0.225), dtype=np.float32)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def center_crop_10_percent(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    if width > height:
        margin = int(width * 0.1)
        return frame[:, margin : width - margin]
    margin = int(height * 0.1)
    return frame[margin : height - margin, :]


def read_d3_frames(video_path: Path, frame_count: int = 16, sample_fps: float = 8.0) -> torch.Tensor:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"cannot open video: {video_path}")

    source_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
    source_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = source_count / source_fps if source_fps > 0 else 0
    window_seconds = frame_count / sample_fps
    # Upstream extracts a 3-second segment at 8 FPS and consumes its first
    # 16 frames.  Use a deterministic centered segment for long videos so
    # repeated product requests return exactly the same score.
    start_seconds = max(0.0, (duration - window_seconds) / 2.0) if duration else 0.0
    frames: list[np.ndarray] = []
    try:
        for index in range(frame_count):
            capture.set(cv2.CAP_PROP_POS_MSEC, (start_seconds + index / sample_fps) * 1000.0)
            ok, bgr = capture.read()
            if not ok:
                break
            rgb = cv2.cvtColor(center_crop_10_percent(bgr), cv2.COLOR_BGR2RGB)
            rgb = cv2.resize(rgb, (224, 224), interpolation=cv2.INTER_LINEAR)
            normalized = (rgb.astype(np.float32) / 255.0 - MEAN) / STD
            frames.append(np.transpose(normalized, (2, 0, 1)))
    finally:
        capture.release()

    if len(frames) < 8:
        raise ValueError(f"D3 requires at least 8 readable frames, got {len(frames)}")
    return torch.from_numpy(np.stack(frames)).unsqueeze(0)


def load_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    counters: defaultdict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        if row.get("split"):
            continue
        key = (row["label"], row["source"])
        counters[key] += 1
        # Alternating within every label/source group keeps generator families
        # represented in both calibration and held-out evaluation.
        row["split"] = "calibration" if counters[key] % 2 else "evaluation"
    return rows


def calculate_metrics(rows: list[dict[str, object]]) -> dict[str, object]:
    usable = [row for row in rows if not row.get("error")]
    comparison = [row for row in usable if row["label"] in {"real", "ai_generated"}]
    result: dict[str, object] = {
        "sample_count": len(rows),
        "usable_count": len(usable),
        "errors": len(rows) - len(usable),
    }
    for split in ("all", "calibration", "evaluation"):
        subset = comparison if split == "all" else [row for row in comparison if row["split"] == split]
        if len({row["label"] for row in subset}) < 2:
            continue
        y_true = [1 if row["label"] == "ai_generated" else 0 for row in subset]
        scores = [float(row["score"]) for row in subset]
        result[f"{split}_roc_auc"] = round(float(roc_auc_score(y_true, scores)), 6)
        result[f"{split}_average_precision"] = round(float(average_precision_score(y_true, scores)), 6)
    return result


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score videos with the D3 candidate detector")
    parser.add_argument("--manifest", type=Path, default=ROOT / "eval" / "video_manifest.csv")
    parser.add_argument("--encoder", default="ResNet-18")
    parser.add_argument("--loss", choices=("l2", "cos"), default="l2")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output-csv", type=Path)
    parser.add_argument("--output-json", type=Path)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    output_stem = f"d3-{args.encoder.lower()}-{args.loss}".replace("_", "-")
    output_csv = (args.output_csv or ROOT / "logs" / "eval" / f"{output_stem}-scores.csv").resolve()
    output_json = (args.output_json or ROOT / "logs" / "eval" / f"{output_stem}-summary.json").resolve()
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    model = D3_model(encoder_type=args.encoder, loss_type=args.loss).to(args.device).eval()
    rows = load_manifest(args.manifest)
    if args.limit:
        rows = rows[: args.limit]

    results: list[dict[str, object]] = []
    with torch.inference_mode():
        for index, row in enumerate(rows, start=1):
            started = time.monotonic()
            result: dict[str, object] = {**row, "encoder": args.encoder, "loss": args.loss}
            try:
                video_path = ROOT / row["file_path"]
                frames = read_d3_frames(video_path).to(args.device)
                _, mean, std = model(frames)
                result.update(score=float(std.item()), second_order_mean=float(mean.item()), error="")
            except Exception as exc:  # keep the batch auditable
                result.update(score="", second_order_mean="", error=str(exc))
            result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
            results.append(result)
            print(f"[{index:02d}/{len(rows):02d}] {row['file_path']} score={result['score']} error={result['error']}", flush=True)

    fields = list(results[0].keys()) if results else []
    with output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    summary = {
        "generated_at": utc_now(),
        "model": "D3",
        "upstream": "https://github.com/Zig-HS/D3",
        "encoder": args.encoder,
        "loss": args.loss,
        "frame_policy": "deterministic_center_16_frames_at_8fps_minimum_8",
        "metrics": calculate_metrics(results),
        "scores_csv": str(output_csv.relative_to(ROOT)),
    }
    output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["metrics"]["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
