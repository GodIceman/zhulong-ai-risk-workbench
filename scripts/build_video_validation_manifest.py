#!/usr/bin/env python3
"""Build the reproducible manifest for independently held-out SDFVD videos."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIDEO_ROOT = ROOT / "eval" / "videos_validation"
OUTPUT = ROOT / "eval" / "video_validation_manifest.csv"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    rows = []
    for folder, label, attack in (
        ("real", "real", "none"),
        ("deepfake", "deepfake", "face_swap"),
    ):
        for path in sorted((VIDEO_ROOT / folder).glob("*.mp4")):
            rows.append(
                {
                    "file_path": path.relative_to(ROOT).as_posix(),
                    "label": label,
                    "attack_type": attack,
                    "source": "SDFVD",
                    "expected_verdict": "likely_real_or_uncertain" if label == "real" else "deepfake_or_uncertain",
                    "split": "validation",
                    "sha256": sha256(path),
                }
            )
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
