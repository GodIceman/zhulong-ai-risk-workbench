#!/usr/bin/env python3
"""Score uniformly sampled video frames with an image forgery detector."""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import torch
from sklearn.metrics import average_precision_score, roc_auc_score
from transformers import AutoImageProcessor, AutoModelForImageClassification


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "king1oo1/deepfake-model"


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


def crop_largest_face(rgb: np.ndarray, detector: cv2.CascadeClassifier) -> tuple[np.ndarray, bool]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 40))
    if len(faces) == 0:
        height, width = rgb.shape[:2]
        side = min(height, width)
        top = (height - side) // 2
        left = (width - side) // 2
        return rgb[top : top + side, left : left + side], False
    x, y, width, height = max(faces, key=lambda face: int(face[2]) * int(face[3]))
    margin = int(max(width, height) * 0.2)
    left, top = max(0, x - margin), max(0, y - margin)
    right, bottom = min(rgb.shape[1], x + width + margin), min(rgb.shape[0], y + height + margin)
    return rgb[top:bottom, left:right], True


def read_uniform_frames(path: Path, count: int, crop_faces: bool) -> tuple[list[np.ndarray], float]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"cannot open video: {path}")
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total < 2:
        capture.release()
        raise ValueError(f"video has too few frames: {total}")
    frames = []
    face_hits = 0
    detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    try:
        for index in np.linspace(0, total - 1, count).astype(int):
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if not ok:
                raise ValueError(f"cannot decode frame {index}")
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            if crop_faces:
                rgb, found = crop_largest_face(rgb, detector)
                face_hits += int(found)
            frames.append(rgb)
    finally:
        capture.release()
    return frames, face_hits / len(frames) if crop_faces else 0.0


def calculate_metrics(rows: list[dict[str, object]], score_field: str) -> dict[str, object]:
    usable = [row for row in rows if not row.get("error")]
    result: dict[str, object] = {"sample_count": len(rows), "usable_count": len(usable), "errors": len(rows) - len(usable)}
    for positive in ("deepfake", "ai_generated"):
        relevant = [row for row in usable if row["label"] in {"real", positive}]
        for split in ("all", "calibration", "evaluation", "validation"):
            subset = relevant if split == "all" else [row for row in relevant if row["split"] == split]
            if len({row["label"] for row in subset}) < 2:
                continue
            truth = [int(row["label"] == positive) for row in subset]
            scores = [float(row[score_field]) for row in subset]
            prefix = f"{positive}_{split}"
            result[f"{prefix}_roc_auc"] = round(float(roc_auc_score(truth, scores)), 6)
            result[f"{prefix}_average_precision"] = round(float(average_precision_score(truth, scores)), 6)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a frame-level synthetic media detector on videos")
    parser.add_argument("--manifest", type=Path, default=ROOT / "eval" / "video_manifest.csv")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--frames", type=int, default=8)
    parser.add_argument("--no-face-crop", action="store_true")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output-csv", type=Path, default=ROOT / "logs" / "eval" / "frame-detector-scores.csv")
    parser.add_argument("--output-json", type=Path, default=ROOT / "logs" / "eval" / "frame-detector-summary.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_csv = args.output_csv.resolve()
    output_json = args.output_json.resolve()
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    processor = AutoImageProcessor.from_pretrained(args.model)
    model = AutoModelForImageClassification.from_pretrained(args.model).to(args.device).eval()
    fake_id = next(int(key) for key, value in model.config.id2label.items() if str(value).lower() == "fake")
    rows = load_manifest(args.manifest)
    if args.limit:
        rows = rows[: args.limit]

    results: list[dict[str, object]] = []
    with torch.inference_mode():
        for index, row in enumerate(rows, 1):
            started = time.monotonic()
            result: dict[str, object] = {**row, "model_id": args.model}
            try:
                frames, face_ratio = read_uniform_frames(
                    ROOT / row["file_path"], args.frames, crop_faces=not args.no_face_crop
                )
                inputs = processor(images=frames, return_tensors="pt")
                probabilities = torch.softmax(model(**{k: v.to(args.device) for k, v in inputs.items()}).logits, dim=-1)
                fake = probabilities[:, fake_id].cpu().numpy()
                result.update(
                    fake_probability_mean=float(np.mean(fake)),
                    fake_probability_median=float(np.median(fake)),
                    fake_probability_p75=float(np.percentile(fake, 75)),
                    fake_probability_max=float(np.max(fake)),
                    face_detection_ratio=face_ratio,
                    error="",
                )
            except Exception as exc:
                result.update(
                    fake_probability_mean="", fake_probability_median="", fake_probability_p75="",
                    fake_probability_max="", face_detection_ratio="", error=str(exc),
                )
            result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
            results.append(result)
            print(f"[{index:02d}/{len(rows):02d}] {row['file_path']} mean={result['fake_probability_mean']} error={result['error']}", flush=True)

    fields = list(results[0].keys()) if results else []
    with output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "model_id": args.model,
        "model_revision": getattr(model.config, "_commit_hash", None),
        "license": "apache-2.0",
        "frame_policy": f"{args.frames}_uniform_frames_haar_face_crop" if not args.no_face_crop else f"{args.frames}_uniform_frames",
        "primary_score": "fake_probability_mean",
        "metrics": calculate_metrics(results, "fake_probability_mean"),
        "scores_csv": str(output_csv.relative_to(ROOT)),
    }
    output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["metrics"]["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
