#!/usr/bin/env python3
"""Fetch the pinned AEGIS checkpoint and print its immutable digest."""

from __future__ import annotations

import hashlib
from pathlib import Path

from huggingface_hub import hf_hub_download


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "MusapYildiz/aegis-video-detector"
REVISION = "95b71346cec650165e6ad3fb20ed9e80f4b6702a"
FILENAME = "checkpoint_best.pt"
EXPECTED_SHA256 = "7df233979f9d3ef340e101d0d635a4d074577d43e6d1591d677cde31f80e44ba"


def digest(path: Path) -> str:
    sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


path = Path(
    hf_hub_download(
        repo_id=REPOSITORY,
        filename=FILENAME,
        revision=REVISION,
        local_dir=ROOT / "data" / "models" / "aegis",
    )
)
actual_sha256 = digest(path)
if actual_sha256 != EXPECTED_SHA256:
    raise RuntimeError(
        f"AEGIS checkpoint SHA-256 mismatch: expected {EXPECTED_SHA256}, "
        f"got {actual_sha256}"
    )
print(path)
print(f"sha256:{actual_sha256}")
