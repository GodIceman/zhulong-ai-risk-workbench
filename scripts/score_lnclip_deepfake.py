#!/usr/bin/env python3
"""Evaluate the official MIT-licensed LNCLIP-DF TorchScript checkpoint."""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from huggingface_hub import hf_hub_download
from transformers import CLIPProcessor

from score_frame_image_detector import calculate_metrics, load_manifest, read_uniform_frames


ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "yermandy/deepfake-detection"
MODEL_FILE = "model.torchscript"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score videos with the official LNCLIP-DF checkpoint")
    parser.add_argument("--manifest", type=Path, default=ROOT / "eval" / "video_manifest.csv")
    parser.add_argument("--frames", type=int, default=4)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output-csv", type=Path, default=ROOT / "logs" / "eval" / "lnclip-deepfake-scores.csv")
    parser.add_argument("--output-json", type=Path, default=ROOT / "logs" / "eval" / "lnclip-deepfake-summary.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_csv = args.output_csv.resolve()
    output_json = args.output_json.resolve()
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    checkpoint = hf_hub_download(repo_id=MODEL_ID, filename=MODEL_FILE)
    model = torch.jit.load(checkpoint, map_location=args.device).eval().to(args.device)
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14")
    rows = load_manifest(args.manifest)
    if args.limit:
        rows = rows[: args.limit]

    results: list[dict[str, object]] = []
    with torch.inference_mode():
        for index, row in enumerate(rows, 1):
            started = time.monotonic()
            result: dict[str, object] = {**row, "model_id": MODEL_ID}
            try:
                frames, face_ratio = read_uniform_frames(ROOT / row["file_path"], args.frames, crop_faces=True)
                pixel_values = processor(images=frames, return_tensors="pt")["pixel_values"].to(args.device)
                fake = torch.softmax(model(pixel_values), dim=1)[:, 1].float().cpu().numpy()
                result.update(
                    fake_probability_mean=float(np.mean(fake)),
                    fake_probability_median=float(np.median(fake)),
                    fake_probability_max=float(np.max(fake)),
                    face_detection_ratio=face_ratio,
                    error="",
                )
            except Exception as exc:
                result.update(
                    fake_probability_mean="", fake_probability_median="", fake_probability_max="",
                    face_detection_ratio="", error=str(exc),
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
        "model_id": MODEL_ID,
        "model_file": MODEL_FILE,
        "license": "mit",
        "frame_policy": f"{args.frames}_uniform_frames_haar_face_crop",
        "primary_score": "fake_probability_mean",
        "metrics": calculate_metrics(results, "fake_probability_mean"),
        "scores_csv": str(output_csv.relative_to(ROOT)),
    }
    output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["metrics"]["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
