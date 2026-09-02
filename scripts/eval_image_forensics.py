#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Evaluate the local Community Forensics checkpoint without starting APIs."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
import time
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from image_forensics import (  # noqa: E402
    CommunityForensicsDetector,
    DualDataAlignmentDetector,
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=ROOT / "eval" / "manifest.csv")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "logs" / "eval" / "community-forensics-224.csv",
    )
    parser.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    parser.add_argument(
        "--model",
        choices=["community", "dda"],
        default="community",
    )
    parser.add_argument("--variant", choices=["224", "384"], default="224")
    parser.add_argument("--batch-size", type=int, default=16)
    return parser.parse_args()


def confusion(rows, threshold):
    tp = sum(row["label"] == 1 and row["score"] >= threshold for row in rows)
    fn = sum(row["label"] == 1 and row["score"] < threshold for row in rows)
    tn = sum(row["label"] == 0 and row["score"] < threshold for row in rows)
    fp = sum(row["label"] == 0 and row["score"] >= threshold for row in rows)
    return tp, fn, tn, fp


def threshold_metrics(rows, threshold):
    tp, fn, tn, fp = confusion(rows, threshold)
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    accuracy = (tp + tn) / len(rows) if rows else 0.0
    balanced = (recall + specificity) / 2
    return {
        "threshold": threshold,
        "tp": tp,
        "fn": fn,
        "tn": tn,
        "fp": fp,
        "ai_recall": recall,
        "real_recall": specificity,
        "accuracy": accuracy,
        "balanced_accuracy": balanced,
    }


def roc_auc(rows):
    positives = [row["score"] for row in rows if row["label"] == 1]
    negatives = [row["score"] for row in rows if row["label"] == 0]
    if not positives or not negatives:
        return float("nan")
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            wins += 1.0 if positive > negative else 0.5 if positive == negative else 0.0
    return wins / (len(positives) * len(negatives))


def best_threshold(rows):
    candidates = {0.5}
    ordered = sorted({row["score"] for row in rows})
    candidates.update(ordered)
    candidates.update(
        (left + right) / 2 for left, right in zip(ordered, ordered[1:])
    )
    return max(
        (threshold_metrics(rows, threshold) for threshold in candidates),
        key=lambda item: (
            item["balanced_accuracy"],
            item["ai_recall"],
            -abs(item["threshold"] - 0.5),
        ),
    )


def main():
    args = parse_args()
    detector = (
        DualDataAlignmentDetector(args.device).load()
        if args.model == "dda"
        else CommunityForensicsDetector(
            args.device,
            input_size=int(args.variant),
        ).load()
    )
    samples = []
    with args.manifest.open("r", encoding="utf-8-sig", newline="") as handle:
        for item in csv.DictReader(handle):
            raw_label = item.get("label")
            if raw_label not in {"real", "ai_generated"}:
                continue
            samples.append(
                {
                    "file_path": item["file_path"],
                    "path": (ROOT / item["file_path"]).resolve(),
                    "label": 1 if raw_label == "ai_generated" else 0,
                    "domain": item.get("domain") or "",
                }
            )

    rows = []
    started = time.perf_counter()
    for offset in range(0, len(samples), max(1, args.batch_size)):
        batch_samples = samples[offset : offset + args.batch_size]
        opened = []
        valid = []
        for sample in batch_samples:
            try:
                image = Image.open(sample["path"])
                image.load()
                opened.append(image)
                valid.append(sample)
            except Exception as exc:
                rows.append({**sample, "score": None, "error": str(exc)})
        try:
            scores = detector.predict_images(opened, batch_size=args.batch_size)
            rows.extend(
                {**sample, "score": score, "error": ""}
                for sample, score in zip(valid, scores)
            )
        finally:
            for image in opened:
                image.close()

    elapsed = time.perf_counter() - started
    scored = [row for row in rows if row["score"] is not None]
    default = threshold_metrics(scored, 0.5)
    selected = best_threshold(scored)
    auc = roc_auc(scored)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "file_path",
                "label",
                "domain",
                "score",
                "prediction_at_0_5",
                "prediction_at_selected",
                "error",
            ],
        )
        writer.writeheader()
        for row in rows:
            score = row["score"]
            writer.writerow(
                {
                    "file_path": row["file_path"],
                    "label": "ai_generated" if row["label"] else "real",
                    "domain": row["domain"],
                    "score": "" if score is None else f"{score:.8f}",
                    "prediction_at_0_5": (
                        "" if score is None else "ai_generated" if score >= 0.5 else "real"
                    ),
                    "prediction_at_selected": (
                        ""
                        if score is None
                        else "ai_generated"
                        if score >= selected["threshold"]
                        else "real"
                    ),
                    "error": row["error"],
                }
            )

    ai_scores = [row["score"] for row in scored if row["label"] == 1]
    real_scores = [row["score"] for row in scored if row["label"] == 0]
    print(f"model={detector.model_id}@{detector.model_revision}")
    print(f"device={detector.device} images={len(scored)} errors={len(rows) - len(scored)}")
    print(f"latency={elapsed:.2f}s throughput={len(scored) / elapsed:.2f} images/s")
    print(f"auc={auc:.4f}")
    print(
        "score_means="
        f"ai:{statistics.fmean(ai_scores):.4f} "
        f"real:{statistics.fmean(real_scores):.4f}"
    )
    print(
        "threshold_0.5="
        f"acc:{default['accuracy']:.4f} bal_acc:{default['balanced_accuracy']:.4f} "
        f"ai_recall:{default['ai_recall']:.4f} real_recall:{default['real_recall']:.4f} "
        f"tp:{default['tp']} fn:{default['fn']} tn:{default['tn']} fp:{default['fp']}"
    )
    print(
        "selected="
        f"threshold:{selected['threshold']:.6f} "
        f"acc:{selected['accuracy']:.4f} bal_acc:{selected['balanced_accuracy']:.4f} "
        f"ai_recall:{selected['ai_recall']:.4f} real_recall:{selected['real_recall']:.4f} "
        f"tp:{selected['tp']} fn:{selected['fn']} "
        f"tn:{selected['tn']} fp:{selected['fp']}"
    )
    print(f"output={args.output}")
    return 0 if math.isfinite(auc) else 2


if __name__ == "__main__":
    raise SystemExit(main())
