#!/usr/bin/env python3
"""Local positive-only video forensics service.

Three independent branches share one upload and one sampling pass:

* WaveRep G4 looks for fully AI-generated video frames.
* LNCLIP-DF looks for face manipulation on detected face crops.
* D3 measures temporal feature instability and is supporting evidence only.

The service never certifies a video as real. A negative result is an
abstention because compression, unseen generators, short clips, and
post-processing can all suppress forensic traces.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from flask import Flask, jsonify, request
from huggingface_hub import hf_hub_download
from transformers import CLIPProcessor


ROOT = Path(__file__).resolve().parent

# Existing face-manipulation branch. Keep these release constants stable:
# tests and the independent 20-real/20-swap evaluation bind to this manifest.
MODEL_ID = "yermandy/deepfake-detection"
MODEL_FILENAME = "model.torchscript"
MODEL_VERSION = "lnclip-df-torchscript-v1"
PROCESSOR_ID = "openai/clip-vit-large-patch14"
VERIFIED_MODEL_REVISION = "9a6857ec642deb57373c5437be803a199468b8c6"
VERIFIED_PROCESSOR_REVISION = "32bd64288804d66eefd0ccbe215aa642df71cc41"
MODEL_REVISION = os.environ.get("LNCLIP_MODEL_REVISION", VERIFIED_MODEL_REVISION).strip()
PROCESSOR_REVISION = os.environ.get(
    "LNCLIP_PROCESSOR_REVISION",
    VERIFIED_PROCESSOR_REVISION,
).strip()

DEFAULT_THRESHOLD = 0.50
FRAME_COUNT = 4
MIN_FACE_DETECTION_RATIO = 0.5
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
DECISION_SCOPE = "positive_only_face_manipulation"
RELEASE_MANIFEST_ID = "lnclip-df-positive-only-v1"
PERFORMANCE_EVALUATION_ID = "video-face-independent-20-real-20-swap-v1"
PERFORMANCE_QUALIFIED = True
PERFORMANCE_QUALIFICATION_REASON = "independent_positive_only_evaluation_passed"
PERFORMANCE_EVALUATION_SUMMARY = {
    "dataset": {
        "real_videos": 20,
        "face_swap_videos": 20,
        "independent_from_threshold_selection": True,
    },
    "roc_auc": 0.905,
    "threshold": DEFAULT_THRESHOLD,
    "real_videos_warned": 0,
    "face_swap_videos_warned": 9,
    "scope": DECISION_SCOPE,
}

DEPENDENCY_LICENSES = {
    MODEL_ID: {
        "role": "detector_model",
        "license_id": "mit",
        "commercial_use_allowed": True,
        "review_required": False,
        "notice": "The detector model repository declares the MIT license.",
    },
    PROCESSOR_ID: {
        "role": "processor",
        "license_id": "unknown",
        "commercial_use_allowed": None,
        "review_required": True,
        "notice": (
            "The processor repository has no unambiguous license metadata; "
            "commercial release requires a dependency license review."
        ),
    },
}

# Fully generated video branch.
WAVEREP_MODEL_ID = "grip-unina/WaveRep-SyntheticVideoDetection"
WAVEREP_MODEL_VERSION = "G4-dinov2"
WAVEREP_REPOSITORY_REVISION = "0fd6010759c14b572b7842a28fa9f85fe1ddd2fd"
WAVEREP_ARCHITECTURE = "vit_base_patch14_reg4_dinov2.lvd142m"
WAVEREP_CROP_SIZE = 504
WAVEREP_FRAME_COUNT = 12
WAVEREP_FRAME_LOGIT_THRESHOLD = 0.0
WAVEREP_MIN_POSITIVE_FRAME_RATIO = 0.75
WAVEREP_WEIGHT_PATH = Path(
    os.environ.get(
        "WAVEREP_WEIGHT_PATH",
        str(ROOT / "data" / "models" / "waverep" / "weights_dinov2_G4.ckpt"),
    )
)
WAVEREP_WEIGHT_MD5 = "8bf19e6f68a92bed600dd97fbed3f2cd"
# Filled after the official file has been fetched; MD5 remains the upstream
# checksum, SHA-256 is the local immutable artifact identity.
WAVEREP_WEIGHT_SHA256 = os.environ.get(
    "WAVEREP_WEIGHT_SHA256",
    "50d639049d928986ba7d69861a4fe4f3e7afbba1843e3e089cdf6b4748f53d5b",
).strip()
WAVEREP_LICENSE = {
    "license_id": "custom-nonprofit-only",
    "commercial_use_allowed": False,
    "review_required": False,
    "notice": (
        "WaveRep permits informational and nonprofit use only. This local "
        "portfolio demo must not be presented as commercially deployable."
    ),
}

# Fully generated video primary. AEGIS alone is not trusted because local
# domain-shift evaluation produced high false positives; it must be confirmed
# by the independently computed D3 temporal guard.
AEGIS_MODEL_ID = "MusapYildiz/aegis-video-detector"
AEGIS_MODEL_VERSION = "phase2-epoch7"
AEGIS_MODEL_REVISION = "95b71346cec650165e6ad3fb20ed9e80f4b6702a"
AEGIS_CODE_REVISION = "d86a774fd971954a023e1cd00ed7ff5b2575e0d1"
AEGIS_CHECKPOINT_PATH = Path(
    os.environ.get(
        "AEGIS_CHECKPOINT_PATH",
        str(ROOT / "data" / "models" / "aegis" / "checkpoint_best.pt"),
    )
)
AEGIS_CHECKPOINT_SHA256 = (
    "7df233979f9d3ef340e101d0d635a4d074577d43e6d1591d677cde31f80e44ba"
)
AEGIS_FRAME_COUNT = 16
AEGIS_TARGET_WINDOW_SECONDS = 4.0
AEGIS_STRONG_THRESHOLD = 0.90
AEGIS_LICENSE = {
    "license_id": "mit",
    "commercial_use_allowed": True,
    "review_required": True,
    "notice": (
        "AEGIS code and checkpoint declare MIT, but this very recent community "
        "model still requires dependency and provenance review before release."
    ),
}
FULL_GENERATION_EVALUATION_ID = "aegis-d3-consensus-30-real-30-swap-12-generated-v1"
FULL_GENERATION_EVALUATION_SUMMARY = {
    "real_videos": 30,
    "real_videos_warned": 0,
    "face_swap_videos": 30,
    "face_swap_videos_warned_as_fully_generated": 0,
    "ai_generated_videos": 12,
    "ai_generated_videos_warned": 1,
    "aegis_threshold": AEGIS_STRONG_THRESHOLD,
    "d3_threshold": 0.0162,
    "scope": "ultra_conservative_local_demo_positive_only",
}

# Temporal consensus guard. D3 alone is never allowed to form a verdict.
D3_MODEL_ID = "Zig-HS/D3"
D3_MODEL_VERSION = "resnet18-cos-c798fbc"
D3_REPOSITORY_REVISION = "c798fbc57fe0c4198d63a73732c2c0f9e4b4816c"
D3_FRAME_COUNT = 16
D3_SAMPLE_FPS = 8.0
D3_SUPPORT_THRESHOLD = 0.0162
D3_MIN_READABLE_FRAMES = 8

VIDEO_ENSEMBLE_ID = "zhulong-local-video-forensics"
VIDEO_ENSEMBLE_VERSION = "aegis-face-temporal-consensus-v1"
VIDEO_POLICY_VERSION = "positive-only-video-ensemble-v1"
VIDEO_DECISION_SCOPE = "ai_generated_video_and_face_manipulation_positive_only"

IMAGE_MEAN = np.asarray((0.485, 0.456, 0.406), dtype=np.float32)
IMAGE_STD = np.asarray((0.229, 0.224, 0.225), dtype=np.float32)


def _parse_threshold(raw_value: str) -> tuple[float | None, str | None]:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None, "LNCLIP_DEEPFAKE_THRESHOLD must be a number between 0 and 1"
    if not math.isfinite(value) or not 0 < value < 1:
        return None, "LNCLIP_DEEPFAKE_THRESHOLD must be finite and strictly between 0 and 1"
    return value, None


THRESHOLD, THRESHOLD_CONFIG_ERROR = _parse_threshold(
    os.environ.get("LNCLIP_DEEPFAKE_THRESHOLD", str(DEFAULT_THRESHOLD))
)


def _build_manifest(
    model_revision: str,
    processor_revision: str,
    threshold: float | None,
) -> dict:
    return {
        "schema": "video-face-release-manifest/v1",
        "manifest_id": RELEASE_MANIFEST_ID,
        "model": {
            "id": MODEL_ID,
            "filename": MODEL_FILENAME,
            "revision": model_revision,
            "version": MODEL_VERSION,
        },
        "processor": {
            "id": PROCESSOR_ID,
            "revision": processor_revision,
            "use_fast": False,
        },
        "decision": {
            "scope": DECISION_SCOPE,
            "threshold": threshold,
            "frame_count": FRAME_COUNT,
            "minimum_face_detection_ratio": MIN_FACE_DETECTION_RATIO,
            "pipeline_version": "uniform-haar-largest-face-v1",
        },
    }


def _fingerprint(manifest: dict) -> str:
    canonical = json.dumps(
        manifest,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


RELEASE_MANIFEST = _build_manifest(
    VERIFIED_MODEL_REVISION,
    VERIFIED_PROCESSOR_REVISION,
    DEFAULT_THRESHOLD,
)
RELEASE_MANIFEST_FINGERPRINT = (
    "sha256:8ce1c45bb506853e2fd9b23a7fd88e9fee3a033921ab882b2cc60baa84a60be0"
)


def get_release_metadata() -> dict:
    """Describe independent runtime, performance, and license gates for LNCLIP."""
    runtime_manifest = _build_manifest(MODEL_REVISION, PROCESSOR_REVISION, THRESHOLD)
    runtime_fingerprint = _fingerprint(runtime_manifest)
    computed_release_fingerprint = _fingerprint(RELEASE_MANIFEST)
    errors = []
    if THRESHOLD_CONFIG_ERROR:
        errors.append(THRESHOLD_CONFIG_ERROR)
    if not MODEL_REVISION:
        errors.append("LNCLIP_MODEL_REVISION must not be empty")
    if not PROCESSOR_REVISION:
        errors.append("LNCLIP_PROCESSOR_REVISION must not be empty")

    manifest_integrity_valid = hmac.compare_digest(
        computed_release_fingerprint,
        RELEASE_MANIFEST_FINGERPRINT,
    )
    runtime_manifest_qualified = (
        not errors
        and manifest_integrity_valid
        and runtime_manifest == RELEASE_MANIFEST
        and hmac.compare_digest(runtime_fingerprint, RELEASE_MANIFEST_FINGERPRINT)
    )
    if errors:
        runtime_qualification_reason = "invalid_runtime_configuration"
    elif not manifest_integrity_valid:
        runtime_qualification_reason = "release_manifest_fingerprint_invalid"
    elif runtime_manifest_qualified:
        runtime_qualification_reason = "runtime_matches_release_manifest"
    else:
        runtime_qualification_reason = "runtime_differs_from_release_manifest"

    license_models = [
        {"model_id": dependency_id, **license_metadata}
        for dependency_id, license_metadata in DEPENDENCY_LICENSES.items()
    ]
    commercial_use_qualified = all(
        item["commercial_use_allowed"] is True
        and item["review_required"] is False
        for item in license_models
    )
    license_warnings = [
        item["notice"]
        for item in license_models
        if item["commercial_use_allowed"] is not True or item["review_required"]
    ]

    release_qualified = (
        runtime_manifest_qualified
        and PERFORMANCE_QUALIFIED
        and commercial_use_qualified
    )
    if not runtime_manifest_qualified:
        release_qualification_reason = "runtime_not_qualified"
    elif not PERFORMANCE_QUALIFIED:
        release_qualification_reason = "performance_not_qualified"
    elif not commercial_use_qualified:
        release_qualification_reason = "license_not_qualified_for_commercial_release"
    else:
        release_qualification_reason = "runtime_performance_and_license_qualified"

    return {
        "release_qualified": release_qualified,
        "release_qualification_reason": release_qualification_reason,
        "runtime_manifest_qualified": runtime_manifest_qualified,
        "runtime_qualification_reason": runtime_qualification_reason,
        "release_manifest_id": RELEASE_MANIFEST_ID,
        "fingerprint": runtime_fingerprint,
        "runtime_fingerprint": runtime_fingerprint,
        "release_manifest_fingerprint": RELEASE_MANIFEST_FINGERPRINT,
        "model_revision": MODEL_REVISION,
        "processor_id": PROCESSOR_ID,
        "processor_revision": PROCESSOR_REVISION,
        "threshold": THRESHOLD,
        "configuration_errors": errors,
        "performance_qualified": PERFORMANCE_QUALIFIED,
        "performance_qualification_reason": PERFORMANCE_QUALIFICATION_REASON,
        "performance_evaluation_id": PERFORMANCE_EVALUATION_ID,
        "performance_evaluation_summary": PERFORMANCE_EVALUATION_SUMMARY,
        "commercial_use_qualified": commercial_use_qualified,
        "license_review": {
            "dependencies": license_models,
            "warnings": license_warnings,
        },
    }


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

# Keep the original names for backwards-compatible tests and tooling.
model = None
processor = None
model_error = None
model_lock = threading.Lock()

waverep_model = None
waverep_transform = None
waverep_device = torch.device("cpu")
waverep_error = None
waverep_lock = threading.Lock()

aegis_model = None
aegis_device = torch.device("cpu")
aegis_error = None
aegis_lock = threading.Lock()

d3_model = None
d3_error = None
d3_lock = threading.Lock()


def _file_digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_model() -> bool:
    """Load the legacy LNCLIP face-manipulation model."""
    global model, processor, model_error
    release_metadata = get_release_metadata()
    if release_metadata["configuration_errors"]:
        model = None
        processor = None
        model_error = "; ".join(release_metadata["configuration_errors"])
        return False
    try:
        checkpoint = hf_hub_download(
            repo_id=MODEL_ID,
            filename=MODEL_FILENAME,
            revision=MODEL_REVISION,
        )
        model = torch.jit.load(checkpoint, map_location="cpu").eval()
        processor = CLIPProcessor.from_pretrained(
            PROCESSOR_ID,
            revision=PROCESSOR_REVISION,
            use_fast=False,
        )
        model_error = None
        return True
    except Exception as exc:
        model = None
        processor = None
        model_error = str(exc)
        return False


def _resolve_waverep_device() -> torch.device:
    requested = os.environ.get("WAVEREP_DEVICE", "auto").strip().lower()
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if requested.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("WAVEREP_DEVICE requests CUDA but CUDA is unavailable")
    return torch.device(requested)


def load_waverep_model() -> bool:
    """Load the pinned WaveRep G4 checkpoint without a second network fetch."""
    global waverep_model, waverep_transform, waverep_device, waverep_error
    try:
        if not WAVEREP_WEIGHT_PATH.is_file():
            raise FileNotFoundError(
                f"WaveRep weights missing: {WAVEREP_WEIGHT_PATH}. "
                "Run scripts/setup_video_forensics.ps1."
            )
        actual_md5 = _file_digest(WAVEREP_WEIGHT_PATH, "md5")
        if not hmac.compare_digest(actual_md5, WAVEREP_WEIGHT_MD5):
            raise RuntimeError(
                f"WaveRep MD5 mismatch: expected {WAVEREP_WEIGHT_MD5}, got {actual_md5}"
            )
        if WAVEREP_WEIGHT_SHA256:
            actual_sha256 = _file_digest(WAVEREP_WEIGHT_PATH, "sha256")
            if not hmac.compare_digest(actual_sha256, WAVEREP_WEIGHT_SHA256):
                raise RuntimeError(
                    "WaveRep SHA-256 mismatch: "
                    f"expected {WAVEREP_WEIGHT_SHA256}, got {actual_sha256}"
                )

        import timm
        from torchvision import transforms

        waverep_device = _resolve_waverep_device()
        candidate = timm.create_model(
            WAVEREP_ARCHITECTURE,
            num_classes=1,
            pretrained=False,
            img_size=WAVEREP_CROP_SIZE,
        )
        checkpoint = torch.load(
            WAVEREP_WEIGHT_PATH,
            map_location=waverep_device,
            weights_only=False,
        )
        state_dict = checkpoint.get("state_dict", checkpoint)
        state_dict = {
            key.removeprefix("model."): value
            for key, value in state_dict.items()
        }
        candidate.load_state_dict(state_dict, strict=True)
        waverep_model = candidate.to(waverep_device).eval()
        waverep_transform = transforms.Compose(
            [
                transforms.ToPILImage(),
                transforms.CenterCrop((WAVEREP_CROP_SIZE, WAVEREP_CROP_SIZE)),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=tuple(float(value) for value in IMAGE_MEAN),
                    std=tuple(float(value) for value in IMAGE_STD),
                ),
            ]
        )
        waverep_error = None
        return True
    except Exception as exc:
        waverep_model = None
        waverep_transform = None
        waverep_error = str(exc)
        return False


def load_aegis_model() -> bool:
    """Load the pinned AEGIS checkpoint; its state contains the frozen DINO backbone."""
    global aegis_model, aegis_device, aegis_error
    try:
        if not AEGIS_CHECKPOINT_PATH.is_file():
            raise FileNotFoundError(
                f"AEGIS checkpoint missing: {AEGIS_CHECKPOINT_PATH}. "
                "Run scripts/setup_video_forensics.ps1."
            )
        actual_sha256 = _file_digest(AEGIS_CHECKPOINT_PATH, "sha256")
        if not hmac.compare_digest(actual_sha256, AEGIS_CHECKPOINT_SHA256):
            raise RuntimeError(
                "AEGIS SHA-256 mismatch: "
                f"expected {AEGIS_CHECKPOINT_SHA256}, got {actual_sha256}"
            )

        branch_directory = ROOT / "third_party" / "AEGIS" / "src" / "branches"
        utilities_directory = ROOT / "third_party" / "AEGIS" / "src" / "utils"
        for directory in (branch_directory, utilities_directory):
            if not directory.is_dir():
                raise FileNotFoundError(f"AEGIS source directory missing: {directory}")
            if str(directory) not in sys.path:
                sys.path.insert(0, str(directory))

        import timm
        import pixel_branch

        def empty_dinov2_224():
            return timm.create_model(
                "vit_base_patch14_dinov2",
                pretrained=False,
                num_classes=0,
                global_pool="avg",
                img_size=224,
            )

        # Avoid a second unpinned DINO download. The checkpoint's model_state
        # contains every frozen backbone tensor and strict loading verifies it.
        pixel_branch._load_dinov2_224 = empty_dinov2_224
        from detector_model import VideoForensicsDetector

        aegis_device = _resolve_waverep_device()
        candidate = VideoForensicsDetector(freeze_dino=True).to(aegis_device)
        checkpoint = torch.load(
            AEGIS_CHECKPOINT_PATH,
            map_location=aegis_device,
            weights_only=False,
        )
        candidate.load_state_dict(checkpoint["model_state"], strict=True)
        aegis_model = candidate.eval()
        aegis_error = None
        return True
    except Exception as exc:
        aegis_model = None
        aegis_error = str(exc)
        return False


def load_d3_model() -> bool:
    """Load D3's training-free ResNet18 temporal feature branch on CPU."""
    global d3_model, d3_error
    try:
        repository = ROOT / "third_party" / "D3"
        if not repository.is_dir():
            raise FileNotFoundError(f"D3 repository missing: {repository}")
        if str(repository) not in sys.path:
            sys.path.insert(0, str(repository))
        from models import D3_model

        d3_model = D3_model(encoder_type="ResNet-18", loss_type="cos").to("cpu").eval()
        d3_error = None
        return True
    except Exception as exc:
        d3_model = None
        d3_error = str(exc)
        return False


def load_all_models() -> dict[str, bool]:
    return {
        "full_generation": load_aegis_model(),
        "face_manipulation": load_model(),
        "temporal_auxiliary": load_d3_model(),
    }


def crop_largest_face(
    rgb: np.ndarray,
    detector: cv2.CascadeClassifier,
) -> tuple[np.ndarray, bool]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    faces = detector.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=4,
        minSize=(40, 40),
    )
    if len(faces) == 0:
        height, width = rgb.shape[:2]
        side = min(height, width)
        top, left = (height - side) // 2, (width - side) // 2
        return rgb[top : top + side, left : left + side], False
    x, y, width, height = max(
        faces,
        key=lambda face: int(face[2]) * int(face[3]),
    )
    margin = int(max(width, height) * 0.2)
    left, top = max(0, x - margin), max(0, y - margin)
    right = min(rgb.shape[1], x + width + margin)
    bottom = min(rgb.shape[0], y + height + margin)
    return rgb[top:bottom, left:right], True


def read_frames(path: Path) -> tuple[list[np.ndarray], list[float], float]:
    """Legacy four-face sampler retained for direct LNCLIP evaluation."""
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError("无法打开视频文件")
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
    if total < 2:
        capture.release()
        raise ValueError("视频帧数不足")
    indices = np.linspace(0, total - 1, FRAME_COUNT).astype(int)
    detector = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    frames, timestamps = [], []
    face_hits = 0
    try:
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, bgr = capture.read()
            if not ok:
                raise ValueError(f"无法解码第 {index} 帧")
            crop, found = crop_largest_face(
                cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB),
                detector,
            )
            frames.append(crop)
            timestamps.append(round(float(index) / fps, 3) if fps > 0 else 0.0)
            face_hits += int(found)
    finally:
        capture.release()
    return frames, timestamps, face_hits / len(frames)


def _face_branch(
    frames: list[np.ndarray],
    timestamps: list[float],
    face_ratio: float,
) -> dict:
    release_metadata = get_release_metadata()
    if release_metadata["configuration_errors"]:
        raise RuntimeError("; ".join(release_metadata["configuration_errors"]))
    if model is None or processor is None:
        raise RuntimeError(model_error or "LNCLIP 模型未加载")
    pixel_values = processor(images=frames, return_tensors="pt")["pixel_values"]
    with model_lock, torch.inference_mode():
        probabilities = torch.softmax(model(pixel_values), dim=1)[:, 1].float().cpu().numpy()
    score = float(np.mean(probabilities))
    positive = score >= THRESHOLD and face_ratio >= MIN_FACE_DETECTION_RATIO
    frame_predictions = [
        {
            "timestamp": timestamp,
            "fake_probability": round(float(probability), 4),
            "score": round(float(probability), 4),
            "prediction": "suspicious" if probability >= THRESHOLD else "uncertain",
        }
        for timestamp, probability in zip(timestamps, probabilities)
    ]
    return {
        "status": "positive" if positive else "abstained",
        "verdict": "face_manipulation_suspected" if positive else "uncertain",
        "score": round(score, 6),
        "confidence": round(score * 100, 2),
        **release_metadata,
        "decision_scope": DECISION_SCOPE,
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "face_detection_ratio": round(float(face_ratio), 4),
        "frame_predictions": frame_predictions,
        "error": None,
    }


def analyze(path: Path) -> dict:
    """Backwards-compatible direct face-manipulation analysis."""
    started = time.perf_counter()
    frames, timestamps, face_ratio = read_frames(path)
    branch = _face_branch(frames, timestamps, face_ratio)
    positive = branch["status"] == "positive"
    return {
        "success": True,
        **branch,
        "verdict": "deepfake_suspected" if positive else "uncertain",
        "evidence": (
            [
                {
                    "title": "检测到人脸伪造特征",
                    "description": "多个采样人脸帧呈现跨数据集深度伪造模型信号。",
                    "severity": "high",
                    "confidence": branch["confidence"],
                }
            ]
            if positive
            else []
        ),
        "limitations": [
            "仅检测含清晰人脸的换脸或人脸操纵，不覆盖所有完整 AI 生成视频。",
            "低于阈值表示模型弃权，不代表视频真实。",
        ],
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }


@dataclass
class VideoSample:
    frames: dict[int, np.ndarray]
    full_indices: list[int]
    wave_indices: list[int]
    face_indices: list[int]
    d3_indices: list[int]
    timestamps: dict[int, float]
    fps: float
    total_frames: int
    duration_seconds: float
    width: int
    height: int


def _uniform_indices(total_frames: int, count: int) -> list[int]:
    return sorted(
        {
            int(index)
            for index in np.linspace(0, total_frames - 1, min(count, total_frames))
        }
    )


def _d3_indices(total_frames: int, fps: float) -> list[int]:
    del fps
    return list(range(min(total_frames, D3_FRAME_COUNT)))


def _aegis_indices(total_frames: int, fps: float) -> list[int]:
    if fps <= 0:
        return _uniform_indices(total_frames, AEGIS_FRAME_COUNT)
    window_size = min(
        total_frames,
        max(AEGIS_FRAME_COUNT, int(AEGIS_TARGET_WINDOW_SECONDS * fps)),
    )
    start = max(0, (total_frames - window_size) // 2)
    end = start + window_size - 1
    return [
        int(index)
        for index in np.linspace(start, end, min(AEGIS_FRAME_COUNT, total_frames))
    ]


def read_video_sample(path: Path) -> VideoSample:
    """Decode the union of frame indices needed by all three branches once."""
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError("无法打开视频文件")
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if total < 2:
        capture.release()
        raise ValueError("视频帧数不足")

    full_indices = _aegis_indices(total, fps)
    wave_indices = _uniform_indices(total, WAVEREP_FRAME_COUNT)
    face_indices = _uniform_indices(total, FRAME_COUNT)
    d3_indices = _d3_indices(total, fps)
    requested = sorted(set(full_indices + wave_indices + face_indices + d3_indices))
    frames: dict[int, np.ndarray] = {}
    try:
        for index in requested:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, bgr = capture.read()
            if ok:
                frames[index] = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    finally:
        capture.release()

    missing_primary = [index for index in full_indices if index not in frames]
    if missing_primary:
        raise ValueError(f"视频解码不完整，缺少 {len(missing_primary)} 个主要采样帧")
    timestamps = {
        index: round(index / fps, 3) if fps > 0 else 0.0
        for index in frames
    }
    duration = total / fps if fps > 0 else 0.0
    return VideoSample(
        frames=frames,
        full_indices=[index for index in full_indices if index in frames],
        wave_indices=wave_indices,
        face_indices=[index for index in face_indices if index in frames],
        d3_indices=[index for index in d3_indices if index in frames],
        timestamps=timestamps,
        fps=fps,
        total_frames=total,
        duration_seconds=duration,
        width=width,
        height=height,
    )


def analyze_waverep(sample: VideoSample) -> dict:
    if waverep_model is None or waverep_transform is None:
        raise RuntimeError(waverep_error or "WaveRep 模型未加载")
    tensors = [
        waverep_transform(sample.frames[index])
        for index in sample.wave_indices
    ]
    logits: list[float] = []
    batch_size = max(1, int(os.environ.get("WAVEREP_BATCH_SIZE", "2")))
    with waverep_lock, torch.inference_mode():
        for offset in range(0, len(tensors), batch_size):
            batch = torch.stack(tensors[offset : offset + batch_size]).to(waverep_device)
            output = waverep_model(batch).reshape(-1).float().cpu()
            logits.extend(float(value) for value in output)
    probabilities = [1.0 / (1.0 + math.exp(-max(-80.0, min(80.0, logit)))) for logit in logits]
    positive_count = sum(logit > WAVEREP_FRAME_LOGIT_THRESHOLD for logit in logits)
    positive_ratio = positive_count / len(logits)
    median_logit = float(np.median(logits))
    positive = (
        positive_ratio >= WAVEREP_MIN_POSITIVE_FRAME_RATIO
        and median_logit > WAVEREP_FRAME_LOGIT_THRESHOLD
    )
    frame_predictions = [
        {
            "timestamp": sample.timestamps[index],
            "score": round(probability, 4),
            "logit": round(logit, 5),
            "prediction": "suspicious" if logit > WAVEREP_FRAME_LOGIT_THRESHOLD else "uncertain",
        }
        for index, logit, probability in zip(sample.wave_indices, logits, probabilities)
    ]
    return {
        "status": "positive" if positive else "abstained",
        "verdict": "ai_generated_video_suspected" if positive else "uncertain",
        "score": round(float(np.mean(probabilities)), 6),
        "confidence": round(float(np.mean(probabilities)) * 100, 2),
        "raw_median_logit": round(median_logit, 6),
        "positive_frame_ratio": round(positive_ratio, 4),
        "threshold": {
            "frame_logit": WAVEREP_FRAME_LOGIT_THRESHOLD,
            "minimum_positive_frame_ratio": WAVEREP_MIN_POSITIVE_FRAME_RATIO,
        },
        "model_id": WAVEREP_MODEL_ID,
        "model_version": WAVEREP_MODEL_VERSION,
        "model_revision": WAVEREP_REPOSITORY_REVISION,
        "weight_md5": WAVEREP_WEIGHT_MD5,
        "weight_sha256": WAVEREP_WEIGHT_SHA256 or None,
        "runtime_manifest_qualified": bool(WAVEREP_WEIGHT_SHA256),
        "performance_qualified": False,
        "performance_qualification_reason": "local_joint_evaluation_pending",
        "commercial_use_qualified": False,
        "release_qualified": False,
        "release_qualification_reason": "nonprofit_license_and_local_evaluation_only",
        "license_review": {"dependencies": [{"model_id": WAVEREP_MODEL_ID, **WAVEREP_LICENSE}]},
        "frame_predictions": frame_predictions,
        "error": None,
    }


def analyze_aegis(sample: VideoSample) -> dict:
    if aegis_model is None:
        raise RuntimeError(aegis_error or "AEGIS 模型未加载")
    if len(sample.full_indices) != AEGIS_FRAME_COUNT:
        return {
            "status": "abstained",
            "verdict": "uncertain",
            "score": None,
            "confidence": None,
            "threshold": AEGIS_STRONG_THRESHOLD,
            "model_id": AEGIS_MODEL_ID,
            "model_version": AEGIS_MODEL_VERSION,
            "model_revision": AEGIS_MODEL_REVISION,
            "code_revision": AEGIS_CODE_REVISION,
            "checkpoint_sha256": AEGIS_CHECKPOINT_SHA256,
            "runtime_manifest_qualified": True,
            "performance_qualified": False,
            "performance_qualification_reason": "insufficient_unique_frames",
            "commercial_use_qualified": False,
            "release_qualified": False,
            "release_qualification_reason": "recent_community_model_local_demo_only",
            "frame_count": len(sample.full_indices),
            "required_frame_count": AEGIS_FRAME_COUNT,
            "frame_predictions": [],
            "error": None,
        }
    tensors = []
    for index in sample.full_indices:
        rgb = cv2.resize(sample.frames[index], (224, 224), interpolation=cv2.INTER_LINEAR)
        normalized = (rgb.astype(np.float32) / 255.0 - IMAGE_MEAN) / IMAGE_STD
        tensors.append(np.transpose(normalized, (2, 0, 1)))
    video_tensor = torch.from_numpy(np.stack(tensors)).unsqueeze(0).to(aegis_device)
    with aegis_lock, torch.inference_mode():
        outputs = aegis_model(video_tensor)
    score = float(outputs["ai_probability"].item())
    candidate_positive = score >= AEGIS_STRONG_THRESHOLD
    frame_scores = outputs["frame_scores"].reshape(-1).float().cpu().tolist()
    frame_predictions = [
        {
            "timestamp": sample.timestamps[index],
            "score": round(float(frame_score), 4),
            "prediction": (
                "candidate_suspicious"
                if frame_score >= AEGIS_STRONG_THRESHOLD
                else "uncertain"
            ),
        }
        for index, frame_score in zip(sample.full_indices, frame_scores)
    ]
    return {
        "status": "candidate_positive" if candidate_positive else "abstained",
        "verdict": "requires_temporal_consensus" if candidate_positive else "uncertain",
        "score": round(score, 6),
        "confidence": round(score * 100, 2),
        "threshold": AEGIS_STRONG_THRESHOLD,
        "pixel_score": round(float(outputs["pixel_prob"].item()), 6),
        "motion_score": round(float(outputs["motion_prob"].item()), 6),
        "consistency_score": round(float(outputs["consistency_prob"].item()), 6),
        "branch_disagreement": round(float(outputs["disagreement"].item()), 6),
        "model_id": AEGIS_MODEL_ID,
        "model_version": AEGIS_MODEL_VERSION,
        "model_revision": AEGIS_MODEL_REVISION,
        "code_revision": AEGIS_CODE_REVISION,
        "checkpoint_sha256": AEGIS_CHECKPOINT_SHA256,
        "runtime_manifest_qualified": True,
        "performance_qualified": False,
        "performance_qualification_reason": "standalone_domain_shift_requires_d3_consensus",
        "commercial_use_qualified": False,
        "release_qualified": False,
        "release_qualification_reason": "recent_community_model_local_demo_only",
        "license_review": {
            "dependencies": [{"model_id": AEGIS_MODEL_ID, **AEGIS_LICENSE}]
        },
        "frame_predictions": frame_predictions,
        "error": None,
    }


def _prepare_face_sample(sample: VideoSample) -> tuple[list[np.ndarray], list[float], float]:
    detector = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    frames: list[np.ndarray] = []
    timestamps: list[float] = []
    face_hits = 0
    for index in sample.face_indices:
        crop, found = crop_largest_face(sample.frames[index], detector)
        frames.append(crop)
        timestamps.append(sample.timestamps[index])
        face_hits += int(found)
    if not frames:
        raise ValueError("没有可用的人脸采样帧")
    return frames, timestamps, face_hits / len(frames)


def _center_crop_10_percent(rgb: np.ndarray) -> np.ndarray:
    height, width = rgb.shape[:2]
    if width > height:
        margin = int(width * 0.1)
        return rgb[:, margin : width - margin]
    margin = int(height * 0.1)
    return rgb[margin : height - margin, :]


def analyze_d3(sample: VideoSample) -> dict:
    if d3_model is None:
        raise RuntimeError(d3_error or "D3 模型未加载")
    if len(sample.d3_indices) < D3_MIN_READABLE_FRAMES:
        raise ValueError(
            f"D3 至少需要 {D3_MIN_READABLE_FRAMES} 个不重复时序帧，"
            f"当前只有 {len(sample.d3_indices)} 个"
        )
    tensors = []
    for index in sample.d3_indices:
        rgb = _center_crop_10_percent(sample.frames[index])
        rgb = cv2.resize(rgb, (224, 224), interpolation=cv2.INTER_LINEAR)
        normalized = (rgb.astype(np.float32) / 255.0 - IMAGE_MEAN) / IMAGE_STD
        tensors.append(np.transpose(normalized, (2, 0, 1)))
    video_tensor = torch.from_numpy(np.stack(tensors)).unsqueeze(0)
    with d3_lock, torch.inference_mode():
        _, second_order_mean, second_order_std = d3_model(video_tensor)
    score = float(second_order_std.item())
    supporting = score >= D3_SUPPORT_THRESHOLD
    return {
        "status": "supporting" if supporting else "not_supporting",
        "verdict": "temporal_ai_signal" if supporting else "uncertain",
        "score": round(score, 8),
        "threshold": D3_SUPPORT_THRESHOLD,
        "model_id": D3_MODEL_ID,
        "model_version": D3_MODEL_VERSION,
        "model_revision": D3_REPOSITORY_REVISION,
        "second_order_mean": round(float(second_order_mean.item()), 8),
        "frame_count": len(tensors),
        "decision_role": "consensus_guard_never_triggers_alone",
        "release_qualified": False,
        "performance_qualified": False,
        "performance_qualification_reason": "sampling_bias_risk_auxiliary_only",
        "commercial_use_qualified": True,
        "error": None,
    }


def _failed_branch(model_id: str, model_version: str, error: Exception | str) -> dict:
    return {
        "status": "unavailable",
        "verdict": "failed",
        "score": None,
        "model_id": model_id,
        "model_version": model_version,
        "release_qualified": False,
        "error": str(error),
    }


def _branch_model_summary(branch: dict, role: str) -> dict:
    return {
        "model_id": branch.get("model_id"),
        "model_version": branch.get("model_version"),
        "role": role,
        "score": branch.get("score"),
        "label": branch.get("verdict"),
        "status": branch.get("status"),
        "error": branch.get("error"),
        "runtime_manifest_qualified": branch.get("runtime_manifest_qualified", False),
        "performance_qualified": branch.get("performance_qualified", False),
        "commercial_use_qualified": branch.get("commercial_use_qualified", False),
        "release_qualified": branch.get("release_qualified", False),
    }


def analyze_video(path: Path) -> dict:
    started = time.perf_counter()
    sample = read_video_sample(path)
    branch_started = time.perf_counter()
    try:
        full_generation = analyze_aegis(sample)
    except Exception as exc:
        full_generation = _failed_branch(AEGIS_MODEL_ID, AEGIS_MODEL_VERSION, exc)
    full_generation["latency_ms"] = round((time.perf_counter() - branch_started) * 1000)

    branch_started = time.perf_counter()
    try:
        face_frames, face_timestamps, face_ratio = _prepare_face_sample(sample)
        face_manipulation = _face_branch(face_frames, face_timestamps, face_ratio)
    except Exception as exc:
        face_manipulation = _failed_branch(MODEL_ID, MODEL_VERSION, exc)
    face_manipulation["latency_ms"] = round((time.perf_counter() - branch_started) * 1000)

    branch_started = time.perf_counter()
    try:
        temporal_auxiliary = analyze_d3(sample)
    except Exception as exc:
        temporal_auxiliary = _failed_branch(D3_MODEL_ID, D3_MODEL_VERSION, exc)
    temporal_auxiliary["latency_ms"] = round((time.perf_counter() - branch_started) * 1000)

    generated_candidate = full_generation["status"] == "candidate_positive"
    face_positive = face_manipulation["status"] == "positive"
    temporal_support = temporal_auxiliary["status"] == "supporting"
    generated_positive = generated_candidate and temporal_support
    if generated_positive:
        full_generation["status"] = "positive"
        full_generation["verdict"] = "ai_generated_video_suspected"
        full_generation["performance_qualified"] = True
        full_generation["performance_qualification_reason"] = (
            "aegis_d3_ultra_conservative_local_evaluation_passed"
        )
        full_generation["performance_evaluation_id"] = FULL_GENERATION_EVALUATION_ID
        full_generation["performance_evaluation_summary"] = (
            FULL_GENERATION_EVALUATION_SUMMARY
        )
    elif generated_candidate:
        full_generation["status"] = "abstained"
        full_generation["verdict"] = "uncertain"
        full_generation["consensus_reason"] = "d3_temporal_guard_not_met"

    if generated_positive and face_positive:
        verdict = "multiple_video_ai_signals"
        reasons = ["aegis_d3_generated_consensus", "lnclip_face_manipulation_signal"]
        risk_level = "high"
    elif generated_positive:
        verdict = "ai_generated_video_suspected"
        reasons = ["aegis_d3_generated_consensus"]
        risk_level = "high"
    elif face_positive:
        verdict = "face_manipulation_suspected"
        reasons = ["lnclip_face_manipulation_signal"]
        risk_level = "high"
    else:
        verdict = "uncertain"
        reasons = ["positive_only_models_abstained"]
        risk_level = "unknown"
    if temporal_support:
        reasons.append("d3_temporal_support")
    if generated_candidate and not temporal_support:
        reasons.append("aegis_signal_rejected_without_d3_consensus")

    primary_scores = []
    if generated_positive and full_generation.get("score") is not None:
        primary_scores.append(float(full_generation["score"]))
    if face_positive and face_manipulation.get("score") is not None:
        primary_scores.append(float(face_manipulation["score"]))
    confidence = max(primary_scores) if verdict != "uncertain" and primary_scores else None
    evidence = []
    if generated_positive:
        evidence.append(
            {
                "title": "检测到完整 AI 生成视频信号",
                "description": (
                    f"AEGIS 强信号为 {full_generation['confidence']:.1f}%，"
                    "并同时通过 D3 超保守时序阈值；任一模型单独均不会触发警报。"
                ),
                "severity": "high",
                "confidence": full_generation["confidence"],
                "source": AEGIS_MODEL_ID,
            }
        )
    if face_positive:
        evidence.append(
            {
                "title": "检测到人脸操纵信号",
                "description": (
                    "LNCLIP 在清晰人脸采样帧中检测到跨数据集换脸特征，"
                    f"人脸覆盖率 {face_manipulation['face_detection_ratio'] * 100:.0f}%。"
                ),
                "severity": "high",
                "confidence": face_manipulation["confidence"],
                "source": MODEL_ID,
            }
        )
    if temporal_support and not generated_positive:
        evidence.append(
            {
                "title": "时序异常辅助证据",
                "description": "D3 时序特征超过本地门槛，但没有主模型共识，因此不触发结论。",
                "severity": "medium",
                "confidence": None,
                "source": D3_MODEL_ID,
            }
        )

    timeline = [
        {
            **prediction,
            "source": "full_generation",
        }
        for prediction in full_generation.get("frame_predictions", [])
    ]
    timeline.extend(
        {
            **prediction,
            "source": "face_manipulation",
        }
        for prediction in face_manipulation.get("frame_predictions", [])
    )
    if generated_positive:
        timeline.append(
            {
                "start": 0.0,
                "end": round(sample.duration_seconds, 3),
                "status": "suspicious",
                "prediction": "suspicious",
                "score": full_generation.get("score"),
                "description": "整段视频同时满足 AEGIS 强信号与 D3 时序共识门槛。",
                "source": "full_generation_consensus",
            }
        )
    timeline.sort(key=lambda item: (item.get("timestamp", 0), item["source"]))

    branches = {
        "full_generation": full_generation,
        "face_manipulation": face_manipulation,
        "temporal_auxiliary": temporal_auxiliary,
    }
    unavailable_primary = [
        name
        for name in ("full_generation", "face_manipulation")
        if branches[name]["status"] == "unavailable"
    ]
    quality_status = "experimental" if unavailable_primary else "local_demo"
    if unavailable_primary:
        reasons.append("primary_branch_unavailable")

    return {
        "success": True,
        "verdict": verdict,
        "risk_level": risk_level,
        "score": round(confidence, 6) if confidence is not None else None,
        "confidence": round(confidence * 100, 2) if confidence is not None else None,
        "model_id": VIDEO_ENSEMBLE_ID,
        "model_version": VIDEO_ENSEMBLE_VERSION,
        "policy_version": VIDEO_POLICY_VERSION,
        "decision_scope": VIDEO_DECISION_SCOPE,
        "release_qualified": False,
        "release_qualification_reason": "local_noncommercial_experimental_ensemble",
        "commercial_use_qualified": False,
        "branches": branches,
        "models": [
            _branch_model_summary(full_generation, "full_generation_primary"),
            _branch_model_summary(face_manipulation, "face_manipulation_primary"),
            _branch_model_summary(temporal_auxiliary, "temporal_auxiliary"),
        ],
        "decision": {
            "policy_version": VIDEO_POLICY_VERSION,
            "reasons": reasons,
            "quality": {
                "status": quality_status,
                "unavailable_primary_branches": unavailable_primary,
                "never_certifies_real": True,
            },
        },
        "media": {
            "duration_seconds": round(sample.duration_seconds, 3),
            "fps": round(sample.fps, 3),
            "total_frames": sample.total_frames,
            "width": sample.width,
            "height": sample.height,
            "sampled_unique_frames": len(sample.frames),
        },
        "frame_predictions": timeline,
        "timeline": timeline,
        "evidence": evidence,
        "limitations": [
            "这是本地作品集演示，不是司法鉴定或商业发布结论。",
            "AEGIS 与 D3 都存在域偏移风险，因此完整生成警报必须两者同时满足超保守阈值。",
            "D3 可能受采样与运动偏差影响，绝不允许单独触发高风险结论。",
            "WaveRep G4 在本地集出现 8/10 真人误报，已从运行时决策链排除。",
            "所有阴性结果均为模型弃权，不代表视频真实。",
            "极短、低分辨率、强压缩、录屏和新型生成器都可能降低检出率。",
        ],
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }


def _save_upload() -> tuple[Path | None, Any]:
    upload = request.files.get("video")
    if upload is None or not upload.filename:
        return None, (jsonify({"success": False, "error": "请上传视频文件"}), 400)
    suffix = Path(upload.filename).suffix.lower() or ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        upload.save(handle.name)
        return Path(handle.name), None


@app.post("/api/deepfake/video")
@app.post("/api/video/analyze")
def detect_video():
    if aegis_model is None and model is None:
        return jsonify(
            {
                "success": False,
                "error": "主要视频模型均未加载",
                "details": {
                    "full_generation": aegis_error,
                    "face_manipulation": model_error,
                },
            }
        ), 503
    temp_path = None
    try:
        temp_path, error_response = _save_upload()
        if error_response:
            return error_response
        return jsonify(analyze_video(temp_path))
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


@app.get("/api/deepfake/health")
def face_health():
    """Legacy face-only health endpoint retained for compatibility."""
    release_metadata = get_release_metadata()
    return jsonify(
        {
            "status": "ok" if model is not None else "unavailable",
            "model_loaded": model is not None,
            "model_id": MODEL_ID,
            "model_version": MODEL_VERSION,
            **release_metadata,
            "scope": DECISION_SCOPE,
            "error": model_error,
        }
    ), 200 if model is not None else 503


@app.get("/api/video/health")
def video_health():
    branches = {
        "full_generation": {
            "ready": aegis_model is not None,
            "model_id": AEGIS_MODEL_ID,
            "model_version": AEGIS_MODEL_VERSION,
            "device": str(aegis_device),
            "checkpoint_sha256": AEGIS_CHECKPOINT_SHA256,
            "strong_threshold": AEGIS_STRONG_THRESHOLD,
            "requires_d3_consensus": True,
            "performance_evaluation_id": FULL_GENERATION_EVALUATION_ID,
            "performance_evaluation_summary": FULL_GENERATION_EVALUATION_SUMMARY,
            "license": AEGIS_LICENSE,
            "error": aegis_error,
        },
        "face_manipulation": {
            "ready": model is not None and processor is not None,
            "model_id": MODEL_ID,
            "model_version": MODEL_VERSION,
            **get_release_metadata(),
            "error": model_error,
        },
        "temporal_auxiliary": {
            "ready": d3_model is not None,
            "model_id": D3_MODEL_ID,
            "model_version": D3_MODEL_VERSION,
            "decision_role": "consensus_guard_never_triggers_alone",
            "error": d3_error,
        },
    }
    primary_ready = (
        branches["full_generation"]["ready"]
        and branches["face_manipulation"]["ready"]
    )
    status = "ok" if primary_ready else (
        "degraded"
        if branches["full_generation"]["ready"] or branches["face_manipulation"]["ready"]
        else "unavailable"
    )
    return jsonify(
        {
            "status": status,
            "ready": primary_ready,
            "model_id": VIDEO_ENSEMBLE_ID,
            "model_version": VIDEO_ENSEMBLE_VERSION,
            "policy_version": VIDEO_POLICY_VERSION,
            "scope": VIDEO_DECISION_SCOPE,
            "never_certifies_real": True,
            "commercial_use_qualified": False,
            "release_qualified": False,
            "branches": branches,
            "excluded_candidates": [
                {
                    "model_id": WAVEREP_MODEL_ID,
                    "model_version": WAVEREP_MODEL_VERSION,
                    "reason": "local_evaluation_failed_8_of_10_real_videos_warned",
                    "ai_generated_vs_real_roc_auc": 0.425,
                }
            ],
        }
    ), 200 if primary_ready else 503


if __name__ == "__main__":
    load_all_models()
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=int(os.environ.get("PORT", "5003")), debug=False)
