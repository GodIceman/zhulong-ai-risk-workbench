#!/usr/bin/env python3
"""Evaluate an MIT-licensed VideoMAE deepfake checkpoint on local videos."""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
import torch
from sklearn.metrics import average_precision_score, roc_auc_score
from transformers import VideoMAEForVideoClassification, VideoMAEImageProcessor


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "SoraExplora/VideoMae"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    counters: defaultdict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        if row.get("split"):
            continue
        key = (row["label"], row["source"])
        counters[key] += 1
        row["split"] = "calibration" if counters[key] % 2 else "evaluation"
    return rows


def read_uniform_frames(video_path: Path, count: int = 16) -> list[np.ndarray]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"cannot open video: {video_path}")
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total < 2:
        capture.release()
        raise ValueError(f"video has too few frames: {total}")
    indices = np.linspace(0, total - 1, count).astype(int)
    frames: list[np.ndarray] = []
    try:
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if not ok:
                raise ValueError(f"cannot decode frame {index}")
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    finally:
        capture.release()
    return frames


def metrics(rows: list[dict[str, object]]) -> dict[str, object]:
    usable = [row for row in rows if not row.get("error")]
    result: dict[str, object] = {
        "sample_count": len(rows),
        "usable_count": len(usable),
        "errors": len(rows) - len(usable),
    }
    for positive in ("deepfake", "ai_generated"):
        relevant = [row for row in usable if row["label"] in {"real", positive}]
        for split in ("all", "calibration", "evaluation", "validation"):
            subset = relevant if split == "all" else [row for row in relevant if row["split"] == split]
            if len({row["label"] for row in subset}) < 2:
                continue
            truth = [1 if row["label"] == positive else 0 for row in subset]
            scores = [float(row["fake_probability"]) for row in subset]
            prefix = f"{positive}_{split}"
            result[f"{prefix}_roc_auc"] = round(float(roc_auc_score(truth, scores)), 6)
            result[f"{prefix}_average_precision"] = round(float(average_precision_score(truth, scores)), 6)
    return result


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score videos with a VideoMAE deepfake checkpoint")
    parser.add_argument("--manifest", type=Path, default=ROOT / "eval" / "video_manifest.csv")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output-csv", type=Path, default=ROOT / "logs" / "eval" / "videomae-deepfake-scores.csv")
    parser.add_argument("--output-json", type=Path, default=ROOT / "logs" / "eval" / "videomae-deepfake-summary.json")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    output_csv = args.output_csv.resolve()
    output_json = args.output_json.resolve()
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    processor = VideoMAEImageProcessor.from_pretrained(args.model)
    model = VideoMAEForVideoClassification.from_pretrained(args.model).to(args.device).eval()
    fake_id = int(model.config.label2id.get("fake", 1))
    rows = load_manifest(args.manifest)
    if args.limit:
        rows = rows[: args.limit]

    results: list[dict[str, object]] = []
    with torch.inference_mode():
        for index, row in enumerate(rows, start=1):
            started = time.monotonic()
            result: dict[str, object] = {**row, "model_id": args.model}
            try:
                frames = read_uniform_frames(ROOT / row["file_path"])
                inputs = processor(frames, return_tensors="pt")
                logits = model(pixel_values=inputs["pixel_values"].to(args.device)).logits
                probabilities = torch.softmax(logits, dim=-1)[0]
                result.update(
                    fake_probability=float(probabilities[fake_id].item()),
                    predicted_label=model.config.id2label[int(probabilities.argmax().item())],
                    error="",
                )
            except Exception as exc:
                result.update(fake_probability="", predicted_label="error", error=str(exc))
            result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
            results.append(result)
            print(
                f"[{index:02d}/{len(rows):02d}] {row['file_path']} "
                f"fake={result['fake_probability']} error={result['error']}",
                flush=True,
            )

    fields = list(results[0].keys()) if results else []
    with output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)
    summary = {
        "generated_at": utc_now(),
        "model_id": args.model,
        "model_revision": getattr(model.config, "_commit_hash", None),
        "license": "mit",
        "frame_policy": "16_uniform_frames",
        "metrics": metrics(results),
        "scores_csv": str(output_csv.relative_to(ROOT)),
    }
    output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["metrics"]["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
