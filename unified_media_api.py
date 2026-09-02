#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Unified media analysis API for Zhulong phase-one refactor.

This service owns the product-facing API:
- POST /api/media/analyze
- POST /api/articles/verify
- GET /api/tasks/<task_id>
- GET /api/tasks/<task_id>/report

It delegates real model work to the existing model services when they are
available. If a model is unavailable, it returns an explicit failed report
instead of manufacturing a true/fake conclusion.
"""

from __future__ import annotations

import base64
import io
import json
import math
import mimetypes
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from PIL import ExifTags, Image
from werkzeug.utils import secure_filename

from article_verification import (
    ARTICLE_POLICY_VERSION,
    DEFAULT_MAX_MATERIAL_CLAIMS,
    MAX_ARTICLE_CHARS,
    ArticleContentError,
    analyze_article_text,
    normalize_article_text,
)

try:
    from defusedxml import ElementTree as SafeElementTree
except ImportError:  # pragma: no cover - requirements include defusedxml
    import xml.etree.ElementTree as SafeElementTree

try:
    import cv2
except Exception:  # pragma: no cover - video metadata degrades gracefully
    cv2 = None


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads" / "unified"
REPORT_DIR = BASE_DIR / "logs" / "reports"
AI_IMAGE_URL = os.environ.get("AI_DETECTOR_URL", "http://127.0.0.1:5004")
DEEPFAKE_URL = os.environ.get("DEEPFAKE_URL", "http://127.0.0.1:5003")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm"}
DEFAULT_MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_BYTES = int(os.environ.get("MAX_IMAGE_BYTES", DEFAULT_MAX_IMAGE_BYTES))
DEFAULT_MAX_IMAGE_PIXELS = 60_000_000
MAX_IMAGE_PIXELS = int(os.environ.get("MAX_IMAGE_PIXELS", DEFAULT_MAX_IMAGE_PIXELS))
if MAX_IMAGE_BYTES <= 0 or MAX_IMAGE_PIXELS <= 0:
    raise RuntimeError("MAX_IMAGE_BYTES and MAX_IMAGE_PIXELS must be positive integers")
MAX_VIDEO_BYTES = 100 * 1024 * 1024
RECOMMENDED_VIDEO_SECONDS = 3 * 60
IMAGE_DECISION_POLICY_VERSION = "image-provenance-policy-v10"
VIDEO_DECISION_POLICY_VERSION = "positive-only-video-ensemble-v1"
PERSIST_REPORTS = os.environ.get("PERSIST_REPORTS", "false").strip().lower() in {"1", "true", "yes", "on"}
TASK_ID_PATTERN = re.compile(r"^TASK-\d{8}-[A-F0-9]{32}$")
DEFAULT_ALLOWED_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS).split(",")
    if origin.strip()
]


def read_probability_setting(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number between 0 and 1") from exc
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise RuntimeError(f"{name} must be a number between 0 and 1")
    return value


IMAGE_DECISION_THRESHOLDS = {
    "primary_near_low": read_probability_setting("IMAGE_PRIMARY_NEAR_LOW", 0.35),
    "primary_near_high": read_probability_setting("IMAGE_PRIMARY_NEAR_HIGH", 0.74),
    "primary_strong_ai": read_probability_setting("IMAGE_PRIMARY_STRONG_AI", 0.74),
    "auxiliary_strong_ai": read_probability_setting("IMAGE_AUXILIARY_STRONG_AI", 0.75),
    "generator_metadata_floor": read_probability_setting("IMAGE_GENERATOR_METADATA_FLOOR", 0.9),
    "conflict_medium": read_probability_setting("IMAGE_CONFLICT_MEDIUM", 0.35),
    "conflict_high": read_probability_setting("IMAGE_CONFLICT_HIGH", 0.65),
}
if IMAGE_DECISION_THRESHOLDS["primary_near_low"] > IMAGE_DECISION_THRESHOLDS["primary_near_high"]:
    raise RuntimeError("IMAGE_PRIMARY_NEAR_LOW must be <= IMAGE_PRIMARY_NEAR_HIGH")
if IMAGE_DECISION_THRESHOLDS["conflict_medium"] > IMAGE_DECISION_THRESHOLDS["conflict_high"]:
    raise RuntimeError("IMAGE_CONFLICT_MEDIUM must be <= IMAGE_CONFLICT_HIGH")
PROTECTED_SOURCE_HINTS = {"screen_capture", "game_capture"}
VALID_SOURCE_HINTS = PROTECTED_SOURCE_HINTS | {"auto", "camera_export", "unknown"}
CAPTURE_KEYWORDS = (
    "screenshot", "screen", "capture", "steam", "obs", "nvidia", "xbox", "snip",
    "截图", "截屏", "屏幕", "录屏",
)
GENERATOR_METADATA_KEYWORDS = {
    "doubao": "Doubao",
    "midjourney": "Midjourney",
    "stable diffusion": "Stable Diffusion",
    "automatic1111": "AUTOMATIC1111",
    "comfyui": "ComfyUI",
    "invokeai": "InvokeAI",
    "novelai": "NovelAI",
    "dall-e": "DALL-E",
    "openai": "OpenAI",
    "firefly": "Adobe Firefly",
    "fooocus": "Fooocus",
    "ideogram": "Ideogram",
    "flux": "FLUX",
}
EDITOR_METADATA_KEYWORDS = {
    "photoshop": "Adobe Photoshop",
    "lightroom": "Adobe Lightroom",
    "snapseed": "Snapseed",
    "gimp": "GIMP",
    "canva": "Canva",
    "affinity photo": "Affinity Photo",
}
CONTENT_CREDENTIAL_MARKERS = (
    b"c2pa",
    b"contentcredentials.org",
    b"content credentials",
)
MAX_EMBEDDED_METADATA_CHARS = 32768

STATUS_META = {
    "received": ("已接收文件", 5),
    "validating": ("正在校验文件", 15),
    "routing": ("正在识别媒体类型", 25),
    "extracting": ("正在解析媒体信息", 40),
    "detecting": ("正在执行模型检测", 70),
    "aggregating": ("正在生成风险报告", 90),
    "completed": ("检测完成", 100),
    "failed": ("检测失败", 100),
    "uncertain": ("无法形成明确结论", 100),
}

app = Flask(__name__)
CORS(
    app,
    resources={r"/api/*": {"origins": ALLOWED_ORIGINS}},
    supports_credentials=False,
)

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

TASKS: Dict[str, Dict[str, Any]] = {}
TASK_LOCK = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def create_task_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d")
    return f"TASK-{stamp}-{uuid.uuid4().hex.upper()}"


def is_valid_task_id(task_id: str) -> bool:
    return bool(TASK_ID_PATTERN.fullmatch(str(task_id or "")))


def set_task(task_id: str, **updates: Any) -> None:
    with TASK_LOCK:
        task = TASKS.setdefault(task_id, {})
        task.update(updates)
        task["updated_at"] = now_iso()


def set_status(task_id: str, status: str, message: Optional[str] = None) -> None:
    default_message, progress = STATUS_META[status]
    set_task(
        task_id,
        status=status,
        progress=progress,
        message=message or default_message,
    )


def task_snapshot(task_id: str) -> Optional[Dict[str, Any]]:
    with TASK_LOCK:
        task = TASKS.get(task_id)
        return dict(task) if task else None


def report_path(task_id: str) -> Path:
    if not is_valid_task_id(task_id):
        raise ValueError("invalid task id")
    report_root = REPORT_DIR.resolve()
    candidate = (report_root / f"{task_id}.json").resolve()
    if candidate.parent != report_root:
        raise ValueError("report path escapes report directory")
    return candidate


def save_report(task_id: str, report: Dict[str, Any]) -> None:
    if PERSIST_REPORTS:
        destination = report_path(task_id)
        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(temporary), str(destination))
    set_task(task_id, report=report)


def error_response(code: str, message: str, status_code: int = 400):
    return jsonify({"success": False, "error": {"code": code, "message": message}}), status_code


def detect_media_type(filename: str, content_type: str = "") -> Optional[str]:
    extension = Path(filename).suffix.lower()
    if extension in IMAGE_EXTENSIONS or content_type.startswith("image/"):
        return "image"
    if extension in VIDEO_EXTENSIONS or content_type.startswith("video/"):
        return "video"
    return None


def validate_upload(file_storage) -> Dict[str, Any]:
    filename = secure_filename(file_storage.filename or "")
    if not filename:
        raise ValueError("文件名为空")

    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)

    media_type = detect_media_type(filename, file_storage.mimetype or "")
    if media_type is None:
        raise TypeError("暂不支持该文件类型，请上传图片或视频")

    limit = MAX_IMAGE_BYTES if media_type == "image" else MAX_VIDEO_BYTES
    if size > limit:
        if media_type == "image":
            raise OverflowError("图片超过 20MB，请压缩文件或缩小分辨率后重试")
        raise OverflowError("视频超过检测上限，请压缩后重试")

    return {"filename": filename, "size": size, "media_type": media_type}


def human_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{max(1, round(size / 1024))} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def decode_embedded_text(value: Any) -> str:
    if isinstance(value, str):
        return value[:MAX_EMBEDDED_METADATA_CHARS]
    if isinstance(value, bytes):
        return value[:MAX_EMBEDDED_METADATA_CHARS].decode("utf-8", errors="replace")
    return ""


def bounded_metadata_text(value: Any, limit: int = 512) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    return text.replace("\x00", "").strip()[:limit]


def parse_xmp_summary(xmp_texts: List[str]) -> Dict[str, Any]:
    field_names = set()
    content_producers = set()
    aigc_standard_detected = False

    for xmp_text in xmp_texts:
        sanitized = re.sub(r"<\?xpacket.*?\?>", "", xmp_text, flags=re.IGNORECASE | re.DOTALL).strip()
        if not sanitized:
            continue
        try:
            root = SafeElementTree.fromstring(sanitized)
        except Exception:
            continue

        for element in root.iter():
            field_name = str(element.tag).split("}")[-1]
            if field_name:
                field_names.add(field_name)
            namespace_and_name = str(element.tag).lower()
            value = (element.text or "").strip()
            if "aigc" in namespace_and_name or field_name.lower() == "aigc":
                aigc_standard_detected = True
            if not value:
                continue
            if field_name.lower() == "aigc":
                try:
                    payload = json.loads(value)
                except (TypeError, ValueError):
                    payload = {}
                producer = str(payload.get("ContentProducer") or "").strip()
                if producer:
                    content_producers.add(producer)
                if str(payload.get("Label") or "").strip() in {"1", "true", "True"}:
                    aigc_standard_detected = True
            if field_name.lower() in {"digitalSourceType".lower(), "credit", "creatorTool".lower()}:
                lower_value = value.lower()
                if "trainedalgorithmicmedia" in lower_value:
                    aigc_standard_detected = True

    return {
        "field_names": sorted(field_names),
        "content_producers": sorted(content_producers),
        "aigc_standard_detected": aigc_standard_detected,
    }


def file_contains_content_credential_marker(path: Path) -> bool:
    overlap = b""
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                return False
            haystack = (overlap + chunk).lower()
            if any(marker in haystack for marker in CONTENT_CREDENTIAL_MARKERS):
                return True
            overlap = haystack[-64:]


def extract_embedded_provenance(image: Image.Image, path: Path, exif_data: Dict[str, Any]) -> Dict[str, Any]:
    text_items: Dict[str, str] = {}
    for key, value in image.info.items():
        text = decode_embedded_text(value).strip()
        if text:
            text_items[str(key)] = text

    xmp_texts = [
        value for key, value in text_items.items()
        if "xmp" in key.lower() or "adobe" in key.lower() and value.lstrip().startswith("<")
    ]
    xmp_summary = parse_xmp_summary(xmp_texts)
    searchable_parts = [*text_items.keys(), *text_items.values(), str(exif_data.get("Software") or "")]
    searchable_text = "\n".join(searchable_parts).lower()

    generator_names = {
        display_name
        for keyword, display_name in GENERATOR_METADATA_KEYWORDS.items()
        if keyword in searchable_text
    }
    for producer in xmp_summary["content_producers"]:
        normalized_producer = next(
            (
                display_name
                for keyword, display_name in GENERATOR_METADATA_KEYWORDS.items()
                if keyword in producer.lower()
            ),
            producer,
        )
        generator_names.add(normalized_producer)
    editor_names = {
        display_name
        for keyword, display_name in EDITOR_METADATA_KEYWORDS.items()
        if keyword in searchable_text
    }
    generation_parameter_keys = {
        key for key in text_items
        if key.lower() in {"parameters", "prompt", "workflow", "generation_data", "aigc"}
    }
    generator_metadata_detected = bool(
        xmp_summary["aigc_standard_detected"]
        or generator_names
        or generation_parameter_keys
    )

    signals: List[str] = []
    if xmp_summary["aigc_standard_detected"]:
        signals.append("检测到标准化 AIGC 来源标记")
    if generator_names:
        signals.append("嵌入元数据包含生成工具或内容生产方")
    if generation_parameter_keys:
        signals.append("嵌入元数据包含生成参数字段")

    content_credential_marker_present = file_contains_content_credential_marker(path)
    return {
        "xmp_present": bool(xmp_texts),
        "xmp_field_names": xmp_summary["field_names"],
        "embedded_metadata_keys": sorted(text_items),
        "generator_metadata_detected": generator_metadata_detected,
        "generator_metadata_producers": sorted(generator_names),
        "generator_metadata_signals": signals,
        "editing_software_detected": bool(editor_names),
        "editing_software_names": sorted(editor_names),
        "content_credentials_marker_present": content_credential_marker_present,
        "content_credentials_status": (
            "marker_present_unverified" if content_credential_marker_present else "not_detected"
        ),
    }


def extract_image_metadata(path: Path, filename: str, size: int) -> Dict[str, Any]:
    with Image.open(path) as image:
        pixel_count = int(image.width) * int(image.height)
        if pixel_count <= 0:
            raise ValueError("图片尺寸无效")
        if pixel_count > MAX_IMAGE_PIXELS:
            raise OverflowError(f"图片像素总量超过上限（{MAX_IMAGE_PIXELS:,} 像素）")
        exif = image.getexif()
        exif_data: Dict[str, Any] = {}
        if exif:
            tag_map = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
            for key in ("Make", "Model", "DateTime", "Software", "Artist", "Copyright"):
                if key in tag_map:
                    exif_data[key] = bounded_metadata_text(tag_map[key])
        metadata = {
            "filename": filename,
            "file_size": size,
            "file_size_label": human_size(size),
            "format": (image.format or Path(filename).suffix.lstrip(".")).lower(),
            "width": image.width,
            "height": image.height,
            "pixel_count": pixel_count,
            "resolution": f"{image.width}x{image.height}",
            "color_mode": image.mode,
            "exif_present": bool(exif),
            "camera_make": exif_data.get("Make"),
            "camera_model": exif_data.get("Model"),
            "created_time": exif_data.get("DateTime"),
            "software": exif_data.get("Software"),
        }
        metadata.update(extract_embedded_provenance(image, path, exif_data))
        return metadata


def is_display_sized_image(width: int, height: int) -> bool:
    if width <= 0 or height <= 0:
        return False

    known_sizes = {
        (1280, 720), (1366, 768), (1600, 900), (1920, 1080),
        (2560, 1440), (2560, 1600), (3440, 1440), (3840, 2160),
        (1440, 900), (1680, 1050), (1920, 1200), (2560, 1080),
        (3840, 1600), (5120, 1440),
    }
    if (width, height) in known_sizes:
        return True

    aspect = width / height
    # A generic 4:3/16:9 aspect ratio is also common for camera photos and
    # generated images, so only portrait phone-display ratios receive a fuzzy
    # match. Landscape captures need an exact known size or a capture keyword.
    portrait_display = (
        height >= 1280
        and width >= 720
        and any(abs(aspect - target) < 0.03 for target in (9 / 16, 10 / 16))
    )
    return portrait_display


def enrich_image_source_context(metadata: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
    source_hint = str(options.get("source_hint") or "auto")
    if source_hint not in VALID_SOURCE_HINTS:
        source_hint = "auto"
    metadata["source_hint"] = source_hint

    signals: List[str] = []
    if source_hint in PROTECTED_SOURCE_HINTS:
        signals.append("用户声明该媒体为游戏/屏幕截图")

    image_format = str(metadata.get("format") or "").lower()
    if image_format in {"png", "webp"}:
        signals.append("文件格式常见于屏幕截图")

    if metadata.get("exif_present") is False:
        signals.append("未读取到相机 EXIF 信息")

    width = int(metadata.get("width") or 0)
    height = int(metadata.get("height") or 0)
    display_sized = is_display_sized_image(width, height)
    if display_sized:
        signals.append("分辨率符合常见显示器或游戏截图比例")

    software = str(metadata.get("software") or "").lower()
    filename = str(metadata.get("filename") or "").lower()
    software_has_capture_keyword = any(keyword in software for keyword in CAPTURE_KEYWORDS)
    filename_has_capture_keyword = any(keyword in filename for keyword in CAPTURE_KEYWORDS)
    camera_filename_likely = bool(
        re.match(r"^(img[_-]?\d|dji[_-]|mmexport\d|origin[a-f0-9])", filename)
    )
    if software_has_capture_keyword:
        signals.append("元数据中出现截图或录制软件线索")
    if filename_has_capture_keyword:
        signals.append("文件名包含截图或录制相关关键词")
    if camera_filename_likely:
        signals.append("文件名符合常见相机、手机或无人机导出命名")

    # Display-sized PNG/WebP files without EXIF are a known high-false-positive
    # domain. Treat them as protected/ambiguous: this can only force abstention,
    # never certify that the content is real.
    machine_capture_likely = (
        software_has_capture_keyword
        or filename_has_capture_keyword
        or (
            image_format in {"png", "webp"}
            and metadata.get("exif_present") is False
            and display_sized
        )
    )
    protected_domain = (
        source_hint in PROTECTED_SOURCE_HINTS
        or machine_capture_likely
    )

    metadata["protected_domain"] = protected_domain
    metadata["protected_domain_type"] = "game_or_screen_capture" if protected_domain else None
    metadata["protected_domain_signals"] = signals
    metadata["screen_capture_likely"] = protected_domain
    metadata["screen_capture_signals"] = signals
    metadata["camera_filename_likely"] = camera_filename_likely
    return metadata


def extract_video_metadata(path: Path, filename: str, size: int) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {
        "filename": filename,
        "file_size": size,
        "file_size_label": human_size(size),
        "format": Path(filename).suffix.lstrip(".").lower(),
    }
    if cv2 is None:
        metadata["parse_error"] = "OpenCV 不可用，无法读取视频元数据"
        return metadata

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        metadata["parse_error"] = "文件无法解析，请检查文件是否完整"
        return metadata

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    duration = frame_count / fps if fps > 0 else 0
    cap.release()

    metadata.update({
        "duration": round(duration, 2),
        "fps": round(fps, 2),
        "width": width,
        "height": height,
        "resolution": f"{width}x{height}" if width and height else None,
        "total_frames": frame_count,
        "audio_present": None,
        "duration_warning": duration > RECOMMENDED_VIDEO_SECONDS,
    })
    return metadata


def extract_key_frames(path: Path, task_id: str) -> List[Dict[str, Any]]:
    if cv2 is None:
        return []

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return []

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if fps > 0 else 0
    timestamps = {0.0}
    if duration > 0:
        timestamps.add(max(0.0, duration - 0.1))
        current = 5.0
        while current < duration and len(timestamps) < 24:
            timestamps.add(current)
            current += 5.0

    frames: List[Dict[str, Any]] = []
    for index, timestamp in enumerate(sorted(timestamps)):
        frame_index = int(timestamp * fps) if fps > 0 else 0
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = cap.read()
        if not ok:
            continue
        ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        if not ok:
            continue
        frames.append({
            "id": f"frame-{index + 1}",
            "timestamp": round(timestamp, 2),
            "frame_index": frame_index,
            "preview": "data:image/jpeg;base64," + base64.b64encode(buffer).decode("ascii"),
        })
    cap.release()
    return frames


def call_ai_image_detector(path: Path, filename: str) -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        with path.open("rb") as f:
            response = requests.post(
                f"{AI_IMAGE_URL}/api/ai/detect",
                files={"file": (filename, f, mimetypes.guess_type(filename)[0] or "application/octet-stream")},
                timeout=60,
            )
        latency_ms = int((time.perf_counter() - start) * 1000)
        data = response.json() if response.content else {}
        if response.status_code != 200 or not data.get("success"):
            return {
                "model_id": "ai-image-detector",
                "model_version": "external",
                "engine_type": "model",
                "score": None,
                "label": "failed",
                "latency_ms": latency_ms,
                "error": data.get("error") or f"HTTP {response.status_code}",
            }

        ai_score = float(data.get("ai_score") or 0) / 100
        real_score = float(data.get("real_score") or 0) / 100
        is_ai = data.get("is_ai") is True
        auxiliary_models = []
        for item in data.get("auxiliary_models") or []:
            aux_ai_score = item.get("ai_score")
            aux_real_score = item.get("real_score")
            aux_score = item.get("score")
            auxiliary_models.append({
                "model_id": item.get("model_id") or "aux-ai-image-detector",
                "model_version": item.get("model_version") or "external",
                "model_revision": item.get("model_revision"),
                "processor_revision": item.get("processor_revision"),
                "engine_type": item.get("engine_type") or "model",
                "score": None if aux_score is None else float(aux_score) / 100,
                "ai_score": None if aux_ai_score is None else float(aux_ai_score) / 100,
                "real_score": None if aux_real_score is None else float(aux_real_score) / 100,
                "label": item.get("label") or "failed",
                "latency_ms": item.get("latency_ms"),
                "error": item.get("error"),
            })
        return {
            "model_id": "ai-image-detector",
            "model_version": data.get("model") or "external",
            "model_revision": data.get("model_revision"),
            "processor_id": data.get("processor_id"),
            "processor_revision": data.get("processor_revision"),
            "engine_type": "model",
            "score": ai_score if is_ai else real_score,
            "ai_score": ai_score,
            "real_score": real_score,
            "label": "ai_generated" if is_ai else "likely_real",
            "latency_ms": latency_ms,
            "error": None,
            "auxiliary_models": auxiliary_models,
            "threshold": data.get("threshold"),
            "release_manifest_id": data.get("release_manifest_id"),
            "runtime_fingerprint": data.get("runtime_fingerprint"),
            "runtime_manifest_qualified": data.get("runtime_manifest_qualified") is True,
            "runtime_qualification_reason": data.get("runtime_qualification_reason"),
            "performance_qualified": data.get("performance_qualified") is True,
            "performance_qualification_reason": data.get("performance_qualification_reason"),
            "performance_evaluation_id": data.get("performance_evaluation_id"),
            "commercial_use_qualified": data.get("commercial_use_qualified") is True,
            "license_review": data.get("license_review") or {},
            "release_qualified": data.get("release_qualified") is True,
            "release_qualification_reason": data.get("release_qualification_reason"),
        }
    except Exception as exc:
        return {
            "model_id": "ai-image-detector",
            "model_version": "external",
            "engine_type": "model",
            "score": None,
            "label": "failed",
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "error": str(exc),
        }


def call_ai_text_detector(text: str) -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        response = requests.post(
            f"{AI_IMAGE_URL}/api/text/detect",
            json={"text": text},
            timeout=90,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        data = response.json() if response.content else {}
        if response.status_code != 200 or not data.get("success"):
            return {
                "model_id": "chinese-ai-text-detector",
                "model_version": data.get("model_id") or "external",
                "model_revision": data.get("model_revision"),
                "engine_type": "model",
                "label": "failed",
                "score": None,
                "latency_ms": latency_ms,
                "error": data.get("error") or f"HTTP {response.status_code}",
                "segments": [],
                "decision_reasons": ["text_model_call_failed"],
                "release_qualified": False,
            }

        ai_signal_score = data.get("ai_signal_score")
        return {
            "model_id": "chinese-ai-text-detector",
            "model_version": data.get("model_id") or "external",
            "model_revision": data.get("model_revision"),
            "engine_type": "model",
            "label": data.get("verdict") or "uncertain",
            "score": (
                None
                if ai_signal_score is None
                else float(ai_signal_score)
            ),
            "ai_signal_score": (
                None
                if ai_signal_score is None
                else float(ai_signal_score)
            ),
            "classification_confidence": data.get("classification_confidence"),
            "risk_level": data.get("risk_level") or "unknown",
            "latency_ms": latency_ms,
            "model_latency_ms": data.get("latency_ms"),
            "error": None,
            "segments": data.get("segments") or [],
            "segment_count": int(data.get("segment_count") or 0),
            "analyzed_character_count": int(
                data.get("analyzed_character_count") or 0
            ),
            "total_character_count": int(data.get("total_character_count") or 0),
            "analysis_coverage": float(data.get("analysis_coverage") or 0),
            "score_dispersion": data.get("score_dispersion"),
            "strong_ai_segment_ratio": float(
                data.get("strong_ai_segment_ratio") or 0
            ),
            "weak_ai_segment_ratio": float(
                data.get("weak_ai_segment_ratio") or 0
            ),
            "decision_reasons": data.get("decision_reasons") or [],
            "policy_version": data.get("policy_version"),
            "runtime_manifest_qualified": (
                data.get("runtime_manifest_qualified") is True
            ),
            "performance_qualified": data.get("performance_qualified") is True,
            "commercial_use_qualified": (
                data.get("commercial_use_qualified") is True
            ),
            "release_qualified": data.get("release_qualified") is True,
            "release_qualification_reason": data.get(
                "release_qualification_reason"
            ),
            "license_review": data.get("license_review") or {},
            "thresholds": data.get("thresholds") or {},
        }
    except Exception as exc:
        return {
            "model_id": "chinese-ai-text-detector",
            "model_version": "external",
            "engine_type": "model",
            "label": "failed",
            "score": None,
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "error": str(exc),
            "segments": [],
            "decision_reasons": ["text_model_call_failed"],
            "release_qualified": False,
        }


def call_deepfake_video_detector(path: Path, filename: str) -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        with path.open("rb") as f:
            response = requests.post(
                f"{DEEPFAKE_URL}/api/video/analyze",
                files={"video": (filename, f, mimetypes.guess_type(filename)[0] or "video/mp4")},
                timeout=240,
            )
        latency_ms = int((time.perf_counter() - start) * 1000)
        data = response.json() if response.content else {}
        if response.status_code != 200 or not data.get("success"):
            return {
                "model": {
                    "model_id": "deepfake-video-detector",
                    "model_version": "external",
                    "engine_type": "model",
                    "score": None,
                    "label": "failed",
                    "latency_ms": latency_ms,
                    "error": data.get("error") or f"HTTP {response.status_code}",
                },
                "raw": data,
            }

        raw_verdict = str(data.get("verdict", "")).lower()
        confidence = (
            float(data["score"])
            if data.get("score") is not None
            else float(data.get("confidence") or 0) / 100
        )
        if isinstance(data.get("branches"), dict):
            return {
                "model": {
                    "model_id": data.get("model_id") or "video-forensics-ensemble",
                    "model_version": data.get("model_version") or "external",
                    "engine_type": "ensemble",
                    "score": confidence if data.get("score") is not None else None,
                    "label": raw_verdict or "uncertain",
                    "latency_ms": latency_ms,
                    "error": None,
                    "release_qualified": False,
                    "commercial_use_qualified": False,
                    "decision_scope": data.get("decision_scope"),
                    "policy_version": data.get("policy_version"),
                },
                "raw": data,
            }
        runtime_fingerprint = str(data.get("runtime_fingerprint") or data.get("fingerprint") or "")
        release_manifest_fingerprint = str(data.get("release_manifest_fingerprint") or "")
        release_qualified = bool(
            data.get("release_qualified") is True
            and runtime_fingerprint
            and runtime_fingerprint == release_manifest_fingerprint
            and data.get("runtime_manifest_qualified") is True
            and data.get("performance_qualified") is True
            and data.get("commercial_use_qualified") is True
            and data.get("release_qualification_reason")
            == "runtime_performance_and_license_qualified"
        )
        label = (
            "deepfake_suspected" if raw_verdict in {"fake", "deepfake_suspected"}
            else "likely_real" if raw_verdict == "real"
            else "uncertain"
        )
        return {
            "model": {
                "model_id": data.get("model_id") or "deepfake-video-detector",
                "model_version": data.get("model_version") or "external",
                "engine_type": "model",
                "score": confidence,
                "label": label,
                "latency_ms": latency_ms,
                "error": None,
                "release_qualified": release_qualified,
                "release_qualification_reason": data.get("release_qualification_reason"),
                "runtime_manifest_qualified": data.get("runtime_manifest_qualified") is True,
                "runtime_qualification_reason": data.get("runtime_qualification_reason"),
                "performance_qualified": data.get("performance_qualified") is True,
                "performance_qualification_reason": data.get("performance_qualification_reason"),
                "performance_evaluation_id": data.get("performance_evaluation_id"),
                "performance_evaluation_summary": data.get("performance_evaluation_summary") or {},
                "commercial_use_qualified": data.get("commercial_use_qualified") is True,
                "license_review": data.get("license_review") or {},
                "release_manifest_id": data.get("release_manifest_id"),
                "runtime_fingerprint": runtime_fingerprint or None,
                "release_manifest_fingerprint": release_manifest_fingerprint or None,
                "threshold": data.get("threshold"),
                "model_revision": data.get("model_revision"),
                "processor_id": data.get("processor_id"),
                "processor_revision": data.get("processor_revision"),
                "decision_scope": data.get("decision_scope"),
            },
            "raw": data,
        }
    except Exception as exc:
        return {
            "model": {
                "model_id": "deepfake-video-detector",
                "model_version": "efficientnetb0-local",
                "engine_type": "model",
                "score": None,
                "label": "failed",
                "latency_ms": int((time.perf_counter() - start) * 1000),
                "error": str(exc),
            },
            "raw": {},
        }


def build_failed_report(task_id: str, media_type: str, metadata: Dict[str, Any], model: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "media_type": media_type,
        "verdict": "failed",
        "risk_level": "unknown",
        "confidence": None,
        "summary": "模型服务不可用，无法完成检测。本次不形成真伪判断。",
        "evidence": [],
        "visualization": {},
        "metadata": metadata,
        "models": [model],
        "limitations": [
            "本次检测未成功调用模型，因此不形成真伪判断。",
            "来源、元数据和人工复核仍然是必要补充。",
        ],
        "created_at": now_iso(),
    }


def clamp_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def probability_or_none(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(score) or not 0 <= score <= 1:
        return None
    return score


def validate_primary_image_model(model: Dict[str, Any]) -> Optional[str]:
    if model.get("error"):
        return str(model["error"])
    if model.get("label") not in {"ai_generated", "likely_real"}:
        return "主模型返回了无法识别的标签"
    ai_score = probability_or_none(model.get("ai_score"))
    real_score = probability_or_none(model.get("real_score"))
    if ai_score is None or real_score is None:
        return "主模型返回了无效概率"
    if not 0.95 <= ai_score + real_score <= 1.05:
        return "主模型概率未归一化"
    return None


def partition_auxiliary_models(model: Dict[str, Any]) -> tuple:
    valid_models: List[Dict[str, Any]] = []
    reported_models: List[Dict[str, Any]] = []
    for item in model.get("auxiliary_models") or []:
        reported = dict(item)
        error = str(reported.get("error") or "").strip()
        ai_score = probability_or_none(reported.get("ai_score"))
        real_score = probability_or_none(reported.get("real_score"))
        if not error and (ai_score is None or real_score is None):
            error = "辅助模型返回了无效概率"
        if not error and not 0.95 <= ai_score + real_score <= 1.05:
            error = "辅助模型概率未归一化"
        if error:
            reported.update({"label": "failed", "error": error})
        else:
            reported.update({"ai_score": ai_score, "real_score": real_score, "error": None})
            valid_models.append(reported)
        reported_models.append(reported)
    return valid_models, reported_models


def normalize_directional_score(value: float) -> float:
    """Map a binary-model score from [0.5, 1.0] to evidence strength [0, 1]."""
    return clamp_score((float(value) - 0.5) / 0.5)


def build_image_risk_inputs(
    metadata: Dict[str, Any],
    model: Dict[str, Any],
    auxiliary_models: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if auxiliary_models is None:
        auxiliary_models, _ = partition_auxiliary_models(model)
    auxiliary_ai_scores = [
        clamp_score(float(item.get("ai_score") or 0))
        for item in auxiliary_models
        if item.get("ai_score") is not None
    ]
    source_hint = str(metadata.get("source_hint") or "auto")
    image_format = str(metadata.get("format") or "").lower()
    exif_present = bool(metadata.get("exif_present"))
    protected_domain = bool(metadata.get("protected_domain") or metadata.get("screen_capture_likely"))
    low_provenance_raster = (
        image_format in {"png", "webp"}
        and not exif_present
    )
    camera_source_hint = source_hint == "camera_export"
    camera_metadata_present = bool(metadata.get("camera_make") or metadata.get("camera_model"))
    camera_filename_likely = bool(metadata.get("camera_filename_likely"))
    camera_provenance = (
        (exif_present and camera_metadata_present)
        or camera_filename_likely
    )

    return {
        "primary_ai_score": clamp_score(float(model.get("ai_score") or 0)),
        "primary_real_score": clamp_score(float(model.get("real_score") or 0)),
        "primary_label": str(model.get("label") or "unknown"),
        "auxiliary_model_count": len(auxiliary_ai_scores),
        "auxiliary_ai_scores": [round(score, 4) for score in auxiliary_ai_scores],
        "max_auxiliary_ai_score": round(max(auxiliary_ai_scores), 4) if auxiliary_ai_scores else 0.0,
        "source_hint": source_hint,
        "format": image_format,
        "exif_present": exif_present,
        "camera_metadata_present": camera_metadata_present,
        "camera_filename_likely": camera_filename_likely,
        "created_time_present": bool(metadata.get("created_time")),
        "protected_domain": protected_domain,
        "low_provenance_raster": low_provenance_raster,
        "camera_source_hint": camera_source_hint,
        "camera_provenance": camera_provenance,
        "source_hint_trust": "unverified_user_declaration",
        "generator_metadata_detected": bool(metadata.get("generator_metadata_detected")),
        "generator_metadata_producers": list(metadata.get("generator_metadata_producers") or []),
        "editing_software_detected": bool(metadata.get("editing_software_detected")),
        "content_credentials_marker_present": bool(metadata.get("content_credentials_marker_present")),
        "width": int(metadata.get("width") or 0),
        "height": int(metadata.get("height") or 0),
        "file_size": int(metadata.get("file_size") or 0),
    }


def score_image_evidence(risk_inputs: Dict[str, Any]) -> Dict[str, Any]:
    primary_ai_signal = normalize_directional_score(risk_inputs["primary_ai_score"])
    auxiliary_ai_signal = normalize_directional_score(risk_inputs["max_auxiliary_ai_score"])
    primary_real_signal = normalize_directional_score(risk_inputs["primary_real_score"])

    provenance_strength = 0.0
    if risk_inputs["exif_present"]:
        provenance_strength += 0.3
    if risk_inputs["camera_metadata_present"]:
        provenance_strength += 0.25
    if risk_inputs["created_time_present"]:
        provenance_strength += 0.1
    provenance_strength = clamp_score(provenance_strength)

    ai_evidence_strength = (
        0.7 * primary_ai_signal + 0.3 * auxiliary_ai_signal
        if risk_inputs["auxiliary_model_count"]
        else primary_ai_signal
    )
    if (
        risk_inputs["low_provenance_raster"]
        and risk_inputs["max_auxiliary_ai_score"] >= IMAGE_DECISION_THRESHOLDS["auxiliary_strong_ai"]
    ):
        ai_evidence_strength = max(ai_evidence_strength + 0.1, 0.65 * auxiliary_ai_signal)
    if risk_inputs["generator_metadata_detected"]:
        ai_evidence_strength = max(
            ai_evidence_strength,
            IMAGE_DECISION_THRESHOLDS["generator_metadata_floor"],
        )
    ai_evidence_strength = clamp_score(ai_evidence_strength)
    real_evidence_strength = clamp_score(0.75 * primary_real_signal + 0.25 * provenance_strength)

    source_ambiguity = 0.0
    if risk_inputs["protected_domain"]:
        source_ambiguity = max(source_ambiguity, 0.85)
    if risk_inputs["low_provenance_raster"]:
        source_ambiguity = max(source_ambiguity, 0.55)
    if risk_inputs["camera_source_hint"] and not risk_inputs["camera_provenance"]:
        source_ambiguity = max(source_ambiguity, 0.35)

    conflict_score = min(ai_evidence_strength, real_evidence_strength) * 1.25
    if risk_inputs["protected_domain"] and ai_evidence_strength >= 0.25:
        conflict_score += 0.35
    if risk_inputs["camera_provenance"] and risk_inputs["primary_label"] == "ai_generated":
        conflict_score += 0.25
    if risk_inputs["low_provenance_raster"] and risk_inputs["primary_label"] == "likely_real":
        conflict_score += 0.15
    conflict_score = clamp_score(conflict_score)
    conflict_level = (
        "high"
        if conflict_score >= IMAGE_DECISION_THRESHOLDS["conflict_high"]
        else "medium"
        if conflict_score >= IMAGE_DECISION_THRESHOLDS["conflict_medium"]
        else "low"
    )

    return {
        "ai_evidence_strength": round(ai_evidence_strength, 4),
        "real_evidence_strength": round(real_evidence_strength, 4),
        "provenance_strength": round(provenance_strength, 4),
        "source_ambiguity": round(source_ambiguity, 4),
        "conflict_score": round(conflict_score, 4),
        "conflict_level": conflict_level,
        "calibration_status": "local_portfolio_dual_consensus_v2",
    }


def decide_image_risk(
    risk_inputs: Dict[str, Any],
    evidence_scores: Dict[str, Any],
) -> Dict[str, Any]:
    ai_score = risk_inputs["primary_ai_score"]
    model_label = risk_inputs["primary_label"]
    auxiliary_strong_ai = (
        risk_inputs["max_auxiliary_ai_score"] >= IMAGE_DECISION_THRESHOLDS["auxiliary_strong_ai"]
    )
    strong_primary_ai = (
        model_label == "ai_generated"
        and ai_score >= IMAGE_DECISION_THRESHOLDS["primary_strong_ai"]
    )
    strong_model_consensus = (
        strong_primary_ai
        and (
            risk_inputs["auxiliary_model_count"] == 0
            or auxiliary_strong_ai
        )
    )
    reasons: List[str] = []

    if risk_inputs["generator_metadata_detected"]:
        verdict = "ai_generated"
        risk_level = "medium"
        summary = "图片嵌入元数据包含明确的 AIGC 或生成工具来源线索，系统判断存在 AI 生成风险。"
        reasons.append("embedded_generator_metadata_signal")
    elif risk_inputs["protected_domain"]:
        verdict = "uncertain"
        risk_level = "unknown"
        summary = "该媒体处于游戏/屏幕截图高误报域，当前证据不足以区分真实截图与 AI 生成图。"
        reasons.append("protected_domain_overrides_ai_model_signal")
    elif risk_inputs["camera_provenance"] and model_label == "ai_generated":
        verdict = "uncertain"
        risk_level = "unknown"
        summary = "模型给出较高 AI 生成分数，但图片具备相机来源线索；为避免把真实照片误报为 AI，本次保留为待复核。"
        reasons.append("camera_provenance_blocks_single_model_ai")
    elif strong_model_consensus:
        verdict = "ai_generated"
        risk_level = "high"
        summary = (
            "经本地测评校准的通用检测模型发现较高 AI 生成风险。"
            if risk_inputs["auxiliary_model_count"] == 0
            else "主模型与辅助模型均检测到较高 AI 生成风险。"
        )
        reasons.append(
            "calibrated_primary_ai_signal"
            if risk_inputs["auxiliary_model_count"] == 0
            else "strong_cross_model_ai_consensus"
        )
    elif risk_inputs["low_provenance_raster"] and auxiliary_strong_ai:
        verdict = "uncertain"
        risk_level = "unknown"
        summary = "图片来源证据较弱，且仅辅助模型给出强 AI 信号；单一模型不足以形成 AI 生成结论。"
        reasons.append("single_auxiliary_ai_signal_requires_abstention")
    elif IMAGE_DECISION_THRESHOLDS["primary_near_low"] <= ai_score <= IMAGE_DECISION_THRESHOLDS["primary_near_high"]:
        verdict = "uncertain"
        risk_level = "unknown"
        summary = "AI 生成风险信号接近模型阈值，无法形成明确结论。"
        reasons.append("primary_model_score_near_threshold")
    elif risk_inputs["camera_source_hint"] and model_label == "ai_generated" and not auxiliary_strong_ai:
        verdict = "uncertain"
        risk_level = "unknown"
        summary = "图片带有拍摄来源提示，但辅助模型未形成强支持，系统不作高风险 AI 强判定。"
        reasons.append("camera_source_hint_blocks_single_model_ai")
    elif model_label == "ai_generated" and not strong_model_consensus:
        verdict = "uncertain"
        risk_level = "unknown"
        summary = "主模型给出 AI 生成信号，但缺少独立强模型共识，无法形成明确结论。"
        reasons.append("primary_ai_signal_without_strong_consensus")
    elif auxiliary_strong_ai:
        verdict = "uncertain"
        risk_level = "unknown"
        summary = "主模型倾向真实，但辅助模型给出强 AI 生成信号，证据冲突，无法形成明确结论。"
        reasons.append("strong_auxiliary_ai_conflicts_with_primary_real")
    elif risk_inputs["low_provenance_raster"]:
        verdict = "uncertain"
        risk_level = "unknown"
        summary = "模型倾向真实，但该图片缺少相机 EXIF 且来源未知，当前证据不足以形成明确真实结论。"
        reasons.append("weak_provenance_blocks_likely_real")
    else:
        verdict = "likely_real"
        risk_level = "low"
        summary = "当前检测未发现明显 AI 生成痕迹。"
        reasons.append("primary_model_real_with_acceptable_provenance")

    if evidence_scores["conflict_level"] == "high":
        reasons.append("high_evidence_conflict")
    if evidence_scores["source_ambiguity"] >= 0.5:
        reasons.append("source_context_is_ambiguous")

    if verdict == "uncertain":
        confidence = None
        confidence_basis = "withheld_due_to_uncertainty"
    elif risk_inputs["generator_metadata_detected"]:
        confidence = None
        confidence_basis = "embedded_generator_metadata_unverified"
    elif verdict == "ai_generated":
        confidence = round(max(ai_score, risk_inputs["max_auxiliary_ai_score"]), 4)
        confidence_basis = "strongest_ai_model_signal"
    else:
        confidence = round(risk_inputs["primary_real_score"], 4)
        confidence_basis = "primary_real_model_signal"

    return {
        "verdict": verdict,
        "risk_level": risk_level,
        "summary": summary,
        "reasons": reasons,
        "confidence": confidence,
        "confidence_basis": confidence_basis,
    }


def build_image_report(task_id: str, metadata: Dict[str, Any], model: Dict[str, Any]) -> Dict[str, Any]:
    primary_model_error = validate_primary_image_model(model)
    if primary_model_error:
        failed_model = dict(model)
        failed_model["error"] = primary_model_error
        failed_model["label"] = "failed"
        return build_failed_report(task_id, "image", metadata, failed_model)

    auxiliary_models, reported_auxiliary_models = partition_auxiliary_models(model)
    auxiliary_failed_count = sum(1 for item in reported_auxiliary_models if item.get("error"))
    if auxiliary_failed_count:
        quality_status = "degraded"
    elif auxiliary_models:
        quality_status = "complete"
    else:
        quality_status = "primary_only"

    risk_inputs = build_image_risk_inputs(metadata, model, auxiliary_models)
    evidence_scores = score_image_evidence(risk_inputs)
    decision = decide_image_risk(risk_inputs, evidence_scores)
    release_gate_present = "release_qualified" in model
    release_qualified = model.get("release_qualified") is True
    if (
        release_gate_present
        and not release_qualified
        and not risk_inputs["generator_metadata_detected"]
    ):
        decision = {
            **decision,
            "verdict": "uncertain",
            "risk_level": "unknown",
            "summary": (
                "图片模型尚未通过完整性能与许可发布门禁，本次仅展示实验性信号，"
                "无法形成明确真伪结论。"
            ),
            "reasons": [
                *decision["reasons"],
                "image_model_not_release_qualified",
            ],
            "confidence": None,
            "confidence_basis": "withheld_due_to_unqualified_image_model",
        }
        quality_status = "experimental"
    elif release_gate_present and not release_qualified:
        decision = {
            **decision,
            "reasons": [
                *decision["reasons"],
                "image_model_not_release_qualified",
            ],
        }
        quality_status = "metadata_only"
    ai_score = risk_inputs["primary_ai_score"]
    real_score = risk_inputs["primary_real_score"]
    protected_domain = risk_inputs["protected_domain"]
    max_auxiliary_ai_score = risk_inputs["max_auxiliary_ai_score"]
    verdict = decision["verdict"]
    risk_level = decision["risk_level"]
    summary = decision["summary"]
    evidence = [{
        "id": "evidence-ai-image-score",
        "type": "model_score",
        "title": "AI 生图模型输出",
        "description": f"模型输出 AI 生成风险分数为 {ai_score:.2f}，真实倾向分数为 {real_score:.2f}。",
        "severity": "medium" if protected_domain or risk_level == "unknown" else risk_level,
        "confidence": None,
        "model_score": round(ai_score, 4),
        "real_score": round(real_score, 4),
    }]
    if risk_inputs["generator_metadata_detected"]:
        producers = "、".join(risk_inputs["generator_metadata_producers"]) or "未标明生产方"
        evidence.insert(0, {
            "id": "evidence-embedded-generator-metadata",
            "type": "generator_metadata",
            "title": "嵌入式生成来源线索",
            "description": f"检测到 AIGC 或生成工具元数据，生产方/工具：{producers}。元数据可能被移除或伪造，因此按中风险证据处理。",
            "severity": "medium",
            "confidence": None,
            "signals": metadata.get("generator_metadata_signals") or [],
        })
    evidence.append({
        "id": "evidence-fusion-scorecard",
        "type": "evidence_fusion",
        "title": "证据融合结果",
        "description": (
            f"AI 证据强度 {evidence_scores['ai_evidence_strength']:.2f}，"
            f"真实证据强度 {evidence_scores['real_evidence_strength']:.2f}，"
            f"证据冲突度 {evidence_scores['conflict_score']:.2f}（"
            f"{ {'high': '高', 'medium': '中', 'low': '低'}.get(evidence_scores['conflict_level'], '未知') }）。"
        ),
        "severity": "medium" if evidence_scores["conflict_level"] != "low" else "low",
        "confidence": None,
        "scores": evidence_scores,
    })
    if protected_domain:
        evidence.insert(0, {
            "id": "evidence-source-domain",
            "type": "source_context",
            "title": "游戏/截图域外提示",
            "description": "游戏引擎渲染、HUD/UI 叠层和截图压缩可能导致 AI 生图模型误报；该信号不代表图片真实。",
            "severity": "medium",
            "confidence": None,
            "signals": metadata.get("protected_domain_signals") or metadata.get("screen_capture_signals") or [],
        })
    if auxiliary_models:
        evidence.append({
            "id": "evidence-auxiliary-ai-image-score",
            "type": "auxiliary_model_score",
            "title": "辅助本地模型输出",
            "description": f"辅助模型最高 AI 生成分数为 {max_auxiliary_ai_score:.2f}，仅作为旁证参与决策。",
            "severity": "medium" if max_auxiliary_ai_score >= 0.8 else "low",
            "confidence": None,
            "model_score": round(max_auxiliary_ai_score, 4),
            "models": [
                {
                    "model_id": item.get("model_id"),
                    "model_version": item.get("model_version"),
                    "ai_score": item.get("ai_score"),
                    "real_score": item.get("real_score"),
                    "label": item.get("label"),
                }
                for item in auxiliary_models
            ],
        })
    if auxiliary_failed_count:
        evidence.append({
            "id": "evidence-auxiliary-model-degraded",
            "type": "model_availability",
            "title": "辅助模型降级",
            "description": f"有 {auxiliary_failed_count} 个辅助模型未能提供有效结果，本次结论基于主模型和其余来源证据。",
            "severity": "medium",
            "confidence": None,
        })
    if metadata.get("exif_present") is False:
        evidence.append({
            "id": "evidence-image-exif",
            "type": "metadata",
            "title": "EXIF 信息",
            "description": "未读取到 EXIF 信息。该信号只能作为辅助证据。",
            "severity": "low",
            "confidence": None,
        })
    if risk_inputs["editing_software_detected"]:
        editors = "、".join(metadata.get("editing_software_names") or [])
        evidence.append({
            "id": "evidence-editing-software",
            "type": "editing_metadata",
            "title": "编辑软件线索",
            "description": f"元数据包含编辑软件信息：{editors}。编辑行为不等于 AI 生成或内容伪造。",
            "severity": "low",
            "confidence": None,
        })
    if risk_inputs["content_credentials_marker_present"]:
        evidence.append({
            "id": "evidence-content-credentials-marker",
            "type": "content_credentials",
            "title": "内容凭证容器线索",
            "description": "文件中检测到 C2PA/Content Credentials 容器标记，但尚未进行密码学签名验证，不作为真实性证明。",
            "severity": "low",
            "confidence": None,
        })

    return {
        "task_id": task_id,
        "media_type": "image",
        "verdict": verdict,
        "risk_level": risk_level,
        "confidence": decision["confidence"],
        "summary": summary,
        "evidence": evidence,
        "visualization": {},
        "metadata": metadata,
        "models": [{k: v for k, v in model.items() if k != "auxiliary_models"}, *reported_auxiliary_models],
        "decision": {
            "policy_version": IMAGE_DECISION_POLICY_VERSION,
            "mode": "deterministic_evidence_scorecard",
            "reasons": decision["reasons"],
            "confidence_basis": decision["confidence_basis"],
            "risk_inputs": risk_inputs,
            "evidence_scores": evidence_scores,
            "thresholds": dict(IMAGE_DECISION_THRESHOLDS),
            "quality": {
                "status": quality_status,
                "primary_model_available": True,
                "auxiliary_models_available": len(auxiliary_models),
                "auxiliary_models_failed": auxiliary_failed_count,
                "release_gate_present": release_gate_present,
                "runtime_manifest_qualified": model.get("runtime_manifest_qualified"),
                "performance_qualified": model.get("performance_qualified"),
                "commercial_use_qualified": model.get("commercial_use_qualified"),
                "release_qualified": (
                    release_qualified if release_gate_present else None
                ),
                "release_qualification_reason": model.get(
                    "release_qualification_reason"
                ),
            },
        },
        "limitations": [
            *(
                [
                    "当前图片模型仅通过运行配置复现门禁，尚未通过完整性能与许可发布门禁；模型输出只作实验性信号。"
                ]
                if release_gate_present and not release_qualified
                else []
            ),
            *[
                str(item)
                for item in (model.get("license_review") or {}).get("warnings", [])
                if item
            ],
            "截图、二次压缩、平台转码可能降低检测可靠性。",
            "游戏/CG/界面截图属于当前模型高误报场景。",
            "当前阈值仅在 62 张本地小样本上校准，不能外推为公开或商用场景性能。",
            "C2PA/Content Credentials 缺失不能直接证明内容伪造。",
            "嵌入元数据可能被移除、修改或伪造，不能单独构成司法级来源证明。",
            "检测结果仅作为辅助判断，不构成司法鉴定结论。",
        ],
        "created_at": now_iso(),
    }


def normalize_video_timeline(raw_timeline: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_timeline, list):
        return []
    segments = []
    for index, item in enumerate(raw_timeline):
        status = (
            item.get("status")
            or item.get("prediction")
            or ("suspicious" if item.get("is_fake") else "normal")
        )
        timestamp = float(item.get("timestamp") or 0)
        segments.append({
            "id": f"segment-{index + 1}",
            "start": float(item.get("start") or timestamp),
            "end": float(item.get("end") or timestamp),
            "status": status,
            "description": item.get("description") or (
                "可疑采样帧" if status == "suspicious" else "该采样帧未形成阳性信号"
            ),
            "confidence": item.get("confidence"),
            "score": item.get("score"),
            "source": item.get("source"),
        })
    return segments


def build_combined_video_report(
    task_id: str,
    metadata: Dict[str, Any],
    key_frames: List[Dict[str, Any]],
    detector_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a transparent local-demo report from all three video branches."""
    raw = detector_result.get("raw") or {}
    verdict = str(raw.get("verdict") or "uncertain")
    allowed_verdicts = {
        "ai_generated_video_suspected",
        "face_manipulation_suspected",
        "multiple_video_ai_signals",
        "uncertain",
    }
    if verdict not in allowed_verdicts:
        verdict = "uncertain"
    positive = verdict != "uncertain"
    confidence = (
        round(float(raw["score"]), 4)
        if positive and raw.get("score") is not None
        else None
    )
    summaries = {
        "ai_generated_video_suspected": (
            "检测到跨采样帧一致的完整 AI 生成视频信号；结果属于本地实验性取证提示。"
        ),
        "face_manipulation_suspected": (
            "检测到人脸操纵或换脸信号；结果属于本地实验性取证提示。"
        ),
        "multiple_video_ai_signals": (
            "完整生成与人脸操纵两个主分支均检测到可疑信号，建议优先人工复核。"
        ),
        "uncertain": (
            "两个阳性专用主模型均未形成稳定警报；这是弃权，不代表视频真实。"
        ),
    }

    evidence = []
    for index, item in enumerate(raw.get("evidence") or []):
        item_confidence = item.get("confidence")
        if item_confidence is not None:
            item_confidence = float(item_confidence)
            if item_confidence > 1:
                item_confidence /= 100
        evidence.append(
            {
                "id": item.get("id") or f"video-evidence-{index + 1}",
                "type": (
                    "temporal_auxiliary"
                    if item.get("source") == "Zig-HS/D3"
                    else "model_signal"
                ),
                "title": item.get("title") or f"视频模型证据 {index + 1}",
                "description": item.get("description") or "视频模型检测到可疑特征。",
                "severity": item.get("severity") or ("high" if positive else "info"),
                "confidence": item_confidence,
                "model_score": item_confidence,
                "timestamp": item.get("timestamp"),
                "source": item.get("source"),
            }
        )
    if not evidence:
        evidence.append(
            {
                "id": "video-positive-only-abstention",
                "type": "model_abstention",
                "title": "阳性专用视频模型已弃权",
                "description": "未达到警报阈值不能解释为真实，仅表示当前证据不足。",
                "severity": "info",
                "confidence": None,
                "model_score": None,
            }
        )

    raw_models = raw.get("models") if isinstance(raw.get("models"), list) else []
    models = []
    for branch_model in raw_models:
        models.append(
            {
                **branch_model,
                "engine_type": (
                    "auxiliary_model"
                    if branch_model.get("role") == "temporal_auxiliary"
                    else "model"
                ),
            }
        )
    if not models:
        models = [detector_result["model"]]

    raw_decision = raw.get("decision") if isinstance(raw.get("decision"), dict) else {}
    quality = (
        raw_decision.get("quality")
        if isinstance(raw_decision.get("quality"), dict)
        else {}
    )
    timeline = normalize_video_timeline(
        raw.get("timeline") or raw.get("frame_predictions")
    )
    frame_predictions = (
        raw.get("frame_predictions")
        if isinstance(raw.get("frame_predictions"), list)
        else []
    )
    limitations = [
        str(item)
        for item in raw.get("limitations") or []
        if str(item).strip()
    ]
    if not limitations:
        limitations = [
            "视频阴性结果不代表真实。",
            "压缩、录屏、低分辨率和新型生成器均可能降低检出率。",
            "结果仅供本地演示与辅助复核，不构成司法鉴定。",
        ]

    return {
        "task_id": task_id,
        "media_type": "video",
        "verdict": verdict,
        "risk_level": "high" if positive else "unknown",
        "confidence": confidence,
        "summary": summaries[verdict],
        "evidence": evidence,
        "visualization": {
            "timeline": timeline[:100],
            "key_frames": key_frames,
            "frame_predictions": frame_predictions[:100],
            "branches": raw.get("branches") or {},
        },
        "metadata": {**metadata, **(raw.get("media") or {})},
        "models": models,
        "decision": {
            "policy_version": raw.get("policy_version") or VIDEO_DECISION_POLICY_VERSION,
            "mode": "positive_only_multi_branch_local_demo",
            "reasons": raw_decision.get("reasons") or ["video_models_abstained"],
            "confidence_basis": (
                "strongest_positive_primary_branch" if positive else "withheld_on_abstention"
            ),
            "quality": {
                **quality,
                "status": quality.get("status") or "experimental",
                "commercial_use_qualified": False,
                "release_qualified": False,
                "temporal_auxiliary_can_trigger": False,
                "never_certifies_real": True,
            },
        },
        "limitations": limitations,
        "created_at": now_iso(),
    }


def build_video_report(
    task_id: str,
    metadata: Dict[str, Any],
    key_frames: List[Dict[str, Any]],
    detector_result: Dict[str, Any],
) -> Dict[str, Any]:
    model = detector_result["model"]
    raw = detector_result.get("raw") or {}
    if model.get("error"):
        return build_failed_report(task_id, "video", metadata, model)
    if isinstance(raw.get("branches"), dict):
        return build_combined_video_report(
            task_id,
            metadata,
            key_frames,
            detector_result,
        )

    confidence = float(model.get("score") or 0)
    suspicious = model.get("label") == "deepfake_suspected"
    release_qualified = model.get("release_qualified") is True
    if release_qualified and suspicious:
        verdict = "deepfake_suspected" if suspicious else "likely_real"
        risk_level = "high" if suspicious and confidence >= 0.8 else "medium" if suspicious else "low"
        final_confidence: Optional[float] = round(confidence, 4)
        summary = "系统检测到疑似 Deepfake 风险。" if suspicious else "当前检测未发现明显 AI 生成或深伪痕迹。"
        decision_reasons = ["release_qualified_video_model_signal"]
    elif release_qualified and model.get("label") == "likely_real":
        verdict = "likely_real"
        risk_level = "low"
        final_confidence = round(confidence, 4)
        summary = "The qualified video model found no clear face-manipulation signal."
        decision_reasons = ["release_qualified_video_model_signal"]
    elif release_qualified:
        verdict = "uncertain"
        risk_level = "unknown"
        final_confidence = None
        summary = "The positive-only face manipulation model abstained; this does not mean the video is real."
        decision_reasons = ["qualified_positive_only_model_abstained"]
    else:
        verdict = "uncertain"
        risk_level = "unknown"
        final_confidence = None
        summary = "当前视频模型尚未通过完整运行、性能与许可发布门禁，本次仅展示实验性模型信号，不形成真伪结论。"
        decision_reasons = ["video_model_not_release_qualified"]
    timeline = normalize_video_timeline(raw.get("timeline"))
    frame_predictions = raw.get("frame_predictions") if isinstance(raw.get("frame_predictions"), list) else []

    evidence = []
    for index, item in enumerate(raw.get("evidence") or []):
        evidence.append({
            "id": item.get("id") or f"video-evidence-{index + 1}",
            "type": "temporal_signal",
            "title": item.get("title") or f"可疑时间段 {index + 1}",
            "description": item.get("description") or "模型检测到可疑视频特征。",
            "severity": "medium" if not release_qualified else item.get("severity") or risk_level,
            "confidence": None if not release_qualified else (
                float(item.get("confidence", confidence * 100)) / 100 if item.get("confidence") else confidence
            ),
            "model_score": confidence,
            "timestamp": item.get("timestamp"),
        })
    if not evidence:
        evidence.append({
            "id": "video-model-score",
            "type": "model_score",
            "title": "视频 Deepfake 模型输出",
            "description": "模型完成关键帧级风险聚合。",
            "severity": "medium" if not release_qualified else risk_level,
            "confidence": final_confidence,
            "model_score": confidence,
        })

    return {
        "task_id": task_id,
        "media_type": "video",
        "verdict": verdict,
        "risk_level": risk_level,
        "confidence": final_confidence,
        "summary": summary,
        "evidence": evidence,
        "visualization": {
            "timeline": timeline,
            "key_frames": key_frames,
            "frame_predictions": frame_predictions[:100],
        },
        "metadata": metadata,
        "models": [model],
        "decision": {
            "policy_version": VIDEO_DECISION_POLICY_VERSION,
            "mode": "release_qualified_model_gate",
            "reasons": decision_reasons,
            "confidence_basis": "qualified_model_score" if release_qualified else "withheld_due_to_unqualified_model",
            "quality": {
                "status": (
                    "positive_only"
                    if release_qualified and model.get("decision_scope") == "positive_only_face_manipulation"
                    else "complete" if release_qualified else "experimental"
                ),
                "release_qualified_models": 1 if release_qualified else 0,
                "experimental_models": 0 if release_qualified else 1,
                "runtime_manifest_qualified": model.get("runtime_manifest_qualified"),
                "performance_qualified": model.get("performance_qualified"),
                "commercial_use_qualified": model.get("commercial_use_qualified"),
                "release_qualification_reason": model.get(
                    "release_qualification_reason"
                ),
            },
        },
        "limitations": [
            *(
                [
                    "当前视频配置通过独立性能评估，但依赖许可证仍需复核，因此完整发布资格为 false，模型输出仅作实验性信号。"
                ]
                if not release_qualified
                and model.get("performance_qualified") is True
                and model.get("commercial_use_qualified") is False
                else [
                    "当前接入的视频模型尚未通过完整发布门禁，仅提供实验性信号。"
                ]
                if not release_qualified
                else [
                    "视频模型已通过当前版本发布门禁，但仍可能在域外素材上失效。"
                ]
            ),
            *[
                str(item)
                for item in (model.get("license_review") or {}).get("warnings", [])
                if item
            ],
            "平台转码、压缩和低分辨率会影响关键帧检测可靠性。",
            "视频检测结果需要结合原始素材链路、来源和人工复核。",
            "检测结果仅作为辅助判断，不构成司法鉴定结论。",
        ],
        "created_at": now_iso(),
    }


def build_article_report(
    task_id: str,
    analysis: Dict[str, Any],
    text_detection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    claims = analysis.get("claims") or []
    sources = analysis.get("sources") or []
    candidate_count = int(analysis.get("candidate_claim_count") or 0)
    material_count = int(analysis.get("material_claim_count") or 0)
    out_of_scope_count = int(analysis.get("out_of_scope_claim_count") or 0)
    explicit_source_count = int(analysis.get("explicit_source_count") or 0)
    declared_origin = analysis.get("declared_origin") or {}
    text_detection = text_detection or {
        "model_id": "chinese-ai-text-detector",
        "model_version": "unavailable",
        "label": "failed",
        "score": None,
        "error": "text detection result was not provided",
        "segments": [],
        "decision_reasons": ["text_model_result_missing"],
        "release_qualified": False,
    }
    text_verdict = str(text_detection.get("label") or "failed")
    ai_signal_score = text_detection.get("ai_signal_score")
    if ai_signal_score is None:
        ai_signal_score = text_detection.get("score")
    ai_signal_percent = (
        None
        if ai_signal_score is None
        else round(float(ai_signal_score) * 100)
    )
    if text_verdict == "ai_style_suspected":
        verdict = "ai_style_suspected"
        risk_level = "high"
        summary = (
            f"多个段落呈现较强 AI 写作风格信号（综合信号 {ai_signal_percent}%）；"
            "该结果仅用于风险分流，不能证明作者身份。"
        )
    elif text_verdict == "no_strong_ai_signal":
        verdict = "no_strong_ai_signal"
        risk_level = "low"
        summary = (
            f"当前未发现一致的强 AI 写作风格信号（综合信号 {ai_signal_percent}%）；"
            "这不等于证明文章由人类撰写。"
        )
    elif text_verdict == "insufficient_text":
        verdict = "insufficient_text"
        risk_level = "unknown"
        summary = "正文过短，无法形成稳定的 AI 写作风格判断。"
    elif text_verdict == "uncertain":
        verdict = "uncertain"
        risk_level = "unknown"
        summary = (
            f"不同段落的模型信号不一致或位于灰区"
            f"{f'（综合信号 {ai_signal_percent}%）' if ai_signal_percent is not None else ''}；"
            "当前无法确认。"
        )
    else:
        verdict = "text_detection_unavailable"
        risk_level = "unknown"
        summary = "文字模型未完成调用；声明与来源清单仍已生成，但不形成 AI 写作判断。"
    missing_evidence = [
        {
            "claim_id": claim.get("claim_id"),
            "items": claim.get("missing_evidence") or [],
        }
        for claim in claims
        if claim.get("checkability") == "checkable"
        and claim.get("missing_evidence")
    ]

    text_segments = text_detection.get("segments") or []
    text_evidence = {
        "id": "article-ai-writing-style-signal",
        "type": "ai_writing_style_signal",
        "title": (
            "中文 BERT 写作风格信号"
            if not text_detection.get("error")
            else "文字模型未完成调用"
        ),
        "description": (
            (
                f"已分析 {len(text_segments)} 个代表性段落，综合 AI 风格信号为 "
                f"{ai_signal_percent}%；分类器输出不是作者身份概率。"
            )
            if ai_signal_percent is not None
            else (
                "正文长度不足，未调用文字模型。"
                if text_verdict == "insufficient_text"
                else f"模型错误：{text_detection.get('error') or '未知错误'}"
            )
        ),
        "severity": risk_level,
        "confidence": text_detection.get("classification_confidence"),
        "model_score": ai_signal_score,
        "signals": [
            f"分析段落：{len(text_segments)}",
            f"高信号段落占比：{round(float(text_detection.get('strong_ai_segment_ratio') or 0) * 100)}%",
            f"采样覆盖：{round(float(text_detection.get('analysis_coverage') or 0) * 100)}%",
        ],
    }

    evidence = [
        text_evidence,
        {
            "id": "article-content-fingerprint",
            "type": "content_integrity",
            "title": "正文内容指纹",
            "description": "已计算规范化正文的 SHA-256，可用于确认后续核查针对同一版本；它不证明来源或真实性。",
            "severity": "unknown",
            "confidence": None,
            "signals": [analysis.get("content_sha256")],
        },
        {
            "id": "article-source-inventory",
            "type": "provenance_inventory",
            "title": "来源与链接清单",
            "description": (
                f"正文中识别到 {explicit_source_count} 个去重链接；"
                "离线模式没有访问链接，也没有验证用户声明的文章来源。"
            ),
            "severity": risk_level,
            "confidence": None,
            "signals": [
                *[item.get("domain") for item in sources[:5] if item.get("domain")],
                *(
                    ["用户提供了文章来源声明，但尚未验证"]
                    if declared_origin
                    else ["未提供声明的文章来源"]
                ),
            ],
        },
        {
            "id": "article-claim-inventory",
            "type": "claim_inventory",
            "title": "候选事实声明",
            "description": (
                f"共列出 {candidate_count} 条候选内容：{material_count} 条待核验事实声明，"
                f"{out_of_scope_count} 条观点、预测或其他核查范围外内容。"
            ),
            "severity": risk_level,
            "confidence": None,
            "signals": [
                f"待外部核验：{material_count}",
                "已核验：0",
                f"核查范围外：{out_of_scope_count}",
            ],
        },
    ]

    metadata = {
        "title": analysis.get("title"),
        "character_count": analysis.get("character_count"),
        "language_token_estimate": analysis.get("language_token_estimate"),
        "paragraph_count": analysis.get("paragraph_count"),
        "sentence_count": analysis.get("sentence_count"),
        "source_url_count": explicit_source_count,
        "source_domains": [
            item.get("domain") for item in sources if item.get("domain")
        ],
        "candidate_claim_count": candidate_count,
        "material_claim_count": material_count,
        "out_of_scope_claim_count": out_of_scope_count,
        "declared_origin": declared_origin,
        "content_sha256": analysis.get("content_sha256"),
        "text_segment_count": len(text_segments),
        "text_analysis_coverage": text_detection.get("analysis_coverage"),
        "ai_style_signal_score": ai_signal_score,
    }

    return {
        "task_id": task_id,
        "media_type": "article",
        "verdict": verdict,
        "risk_level": risk_level,
        "confidence": None,
        "summary": summary,
        "evidence": evidence,
        "visualization": {
            "kind": "text_style_and_claim_matrix",
            "text_segments": text_segments,
            "claims": claims,
            "sources": sources,
        },
        "metadata": metadata,
        "models": [{
            key: value
            for key, value in text_detection.items()
            if key not in {"segments"}
        }],
        "decision": {
            "policy_version": (
                text_detection.get("policy_version")
                or ARTICLE_POLICY_VERSION
            ),
            "inventory_policy_version": ARTICLE_POLICY_VERSION,
            "mode": "local_ai_style_and_offline_inventory",
            "reasons": [
                *(text_detection.get("decision_reasons") or []),
                "classifier_score_is_not_authorship_probability",
                "external_sources_not_fetched",
                (
                    "material_claims_not_checked"
                    if material_count
                    else "no_checkable_claims_extracted"
                ),
            ],
            "confidence_basis": "experimental_text_style_classifier",
            "quality": {
                "status": (
                    "experimental"
                    if not text_detection.get("error")
                    else "degraded"
                ),
                "network_requested": False,
                "network_used": False,
                "retrieval_failures": 0,
                "model_completed": not bool(text_detection.get("error")),
                "release_qualified": (
                    text_detection.get("release_qualified") is True
                ),
            },
            "coverage": {
                "text_segments": len(text_segments),
                "text_analysis_coverage": text_detection.get(
                    "analysis_coverage"
                ),
                "candidate_claims": candidate_count,
                "material_claims": material_count,
                "checked_claims": 0,
                "supported_claims": 0,
                "conflicted_claims": 0,
                "insufficient_claims": material_count,
                "explicit_sources": explicit_source_count,
                "verified_sources": 0,
            },
        },
        "article": {
            "text_detection": {
                key: value
                for key, value in text_detection.items()
                if key not in {"license_review"}
            },
            "sources": sources,
            "claims": claims,
            "missing_evidence": missing_evidence,
            "internal_consistency_issues": [],
        },
        "limitations": [
            "文字模型只识别训练数据中学到的写作风格，不证明真实作者身份。",
            "短文本、人工改写、人机混写和训练分布外文体可能误判或漏判。",
            "当前文字模型未通过本项目独立性能与发布门禁，仅作为本地实验性信号。",
            "声明与来源清单为离线模式，没有访问外部来源。",
            "声明抽取可能遗漏上下文，需要对重要内容人工复核。",
            "该报告不构成文章整体真假证明或学术处分依据。",
        ],
        "created_at": now_iso(),
    }


def build_article_failed_report(
    task_id: str,
    title: str,
    error: str,
) -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "media_type": "article",
        "verdict": "failed",
        "risk_level": "unknown",
        "confidence": None,
        "summary": "文字检测流程未能生成可用报告，本次不形成 AI 写作或作者归因结论。",
        "evidence": [],
        "visualization": {"kind": "claim_matrix", "claims": [], "sources": []},
        "metadata": {"title": title, "error": error},
        "models": [],
        "decision": {
            "policy_version": ARTICLE_POLICY_VERSION,
            "mode": "local_ai_style_and_offline_inventory",
            "reasons": ["article_text_analysis_failed"],
            "quality": {
                "status": "failed",
                "network_requested": False,
                "network_used": False,
            },
        },
        "article": {
            "text_detection": {
                "label": "failed",
                "score": None,
                "segments": [],
                "error": error,
            },
            "sources": [],
            "claims": [],
            "missing_evidence": [],
            "internal_consistency_issues": [],
        },
        "limitations": [
            "本次没有成功调用文字模型或生成声明与来源清单。",
            "失败结果不能用于判断文章作者身份或整体真假。",
        ],
        "created_at": now_iso(),
    }


def validate_article_request(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ArticleContentError("请求体必须是 JSON 对象")
    article_input = payload.get("input")
    options = payload.get("options") or {}
    if not isinstance(article_input, dict):
        raise ArticleContentError("input 必须是对象")
    if not isinstance(options, dict):
        raise ArticleContentError("options 必须是对象")
    if article_input.get("kind") != "text":
        raise ArticleContentError("input.kind 第一版仅支持 text")

    string_fields = (
        "text",
        "title",
        "declared_url",
        "declared_author",
        "declared_published_at",
    )
    for key in string_fields:
        if key in article_input and not isinstance(article_input.get(key), str):
            raise ArticleContentError(f"input.{key} 必须是字符串")

    text = normalize_article_text(article_input.get("text"))
    title = str(article_input.get("title") or "").strip()
    if len(title) > 500:
        raise ArticleContentError("文章标题超过 500 个字符")

    mode = options.get("mode", "local_ai_style")
    if mode not in {"local_ai_style", "offline_inventory", "online_verify"}:
        raise ArticleContentError(
            "options.mode 必须是 local_ai_style、offline_inventory 或 online_verify"
        )
    allow_network = options.get("allow_network", False)
    if not isinstance(allow_network, bool):
        raise ArticleContentError("options.allow_network 必须是布尔值")
    if mode == "online_verify" and not allow_network:
        raise PermissionError("online_verify 需要显式设置 allow_network=true")
    if mode == "online_verify":
        raise ConnectionError("服务端尚未配置受控联网检索器")
    if allow_network:
        raise ArticleContentError("本地文字分析不接受 allow_network=true")

    max_material_claims = options.get(
        "max_material_claims",
        DEFAULT_MAX_MATERIAL_CLAIMS,
    )
    if (
        isinstance(max_material_claims, bool)
        or not isinstance(max_material_claims, int)
        or not 1 <= max_material_claims <= DEFAULT_MAX_MATERIAL_CLAIMS
    ):
        raise ArticleContentError(
            f"options.max_material_claims 必须是 1 到 {DEFAULT_MAX_MATERIAL_CLAIMS} 的整数"
        )

    return {
        "input": {
            "text": text,
            "title": title,
            "declared_url": str(article_input.get("declared_url") or "").strip(),
            "declared_author": str(article_input.get("declared_author") or "").strip(),
            "declared_published_at": str(
                article_input.get("declared_published_at") or ""
            ).strip(),
        },
        "options": {
            "mode": mode,
            "allow_network": False,
            "max_material_claims": max_material_claims,
        },
    }


def process_article_task(
    task_id: str,
    article_input: Dict[str, Any],
    options: Dict[str, Any],
) -> None:
    title = article_input.get("title") or "未命名文章"
    try:
        set_status(task_id, "validating", "正在校验文章正文与核查选项")
        set_status(task_id, "routing", "已进入本地 AI 写作风格检测流程")
        set_status(task_id, "extracting", "正在解析文章结构并准备代表性段落")
        analysis = analyze_article_text(
            article_input["text"],
            title=article_input.get("title") or "",
            declared_url=article_input.get("declared_url") or "",
            declared_author=article_input.get("declared_author") or "",
            declared_published_at=article_input.get("declared_published_at") or "",
            max_material_claims=options["max_material_claims"],
        )
        set_status(task_id, "detecting", "正在调用中文 BERT 分析段落写作风格")
        text_detection = call_ai_text_detector(analysis["normalized_text"])
        set_status(task_id, "aggregating", "正在汇总文字信号与离线核查线索")
        report = build_article_report(task_id, analysis, text_detection)
        save_report(task_id, report)
        set_status(
            task_id,
            "completed",
            "文字风险报告已生成；模型信号不等于作者身份结论",
        )
    except Exception as exc:
        report = build_article_failed_report(task_id, title, str(exc))
        save_report(task_id, report)
        set_status(task_id, "failed", report["summary"])


def process_task(task_id: str, file_path: Path, filename: str, size: int, media_type: str, options: Optional[Dict[str, Any]] = None) -> None:
    try:
        set_status(task_id, "validating")
        time.sleep(0.05)
        media_type_label = {"image": "图片", "video": "视频"}[media_type]
        set_status(task_id, "routing", f"已识别为{media_type_label}内容")
        time.sleep(0.05)
        set_status(task_id, "extracting")

        if media_type == "image":
            metadata = extract_image_metadata(file_path, filename, size)
            metadata = enrich_image_source_context(metadata, options or {})
            set_status(task_id, "detecting", "正在调用 AI 生图检测模型")
            model = call_ai_image_detector(file_path, filename)
            set_status(task_id, "aggregating")
            report = build_image_report(task_id, metadata, model)
        else:
            metadata = extract_video_metadata(file_path, filename, size)
            key_frames = extract_key_frames(file_path, task_id)
            set_status(
                task_id,
                "detecting",
                "正在联合检测完整 AI 生视频、人脸换脸与时序异常",
            )
            detector_result = call_deepfake_video_detector(file_path, filename)
            set_status(task_id, "aggregating")
            report = build_video_report(task_id, metadata, key_frames, detector_result)

        save_report(task_id, report)
        final_status = "completed" if report["verdict"] not in {"failed", "uncertain"} else report["verdict"]
        set_status(task_id, final_status, report["summary"])
    except Exception as exc:
        metadata = {"filename": filename, "file_size": size, "error": str(exc)}
        model = {
            "model_id": f"{media_type}-detector",
            "model_version": "unknown",
            "engine_type": "model",
            "score": None,
            "label": "failed",
            "latency_ms": 0,
            "error": str(exc),
        }
        report = build_failed_report(task_id, media_type, metadata, model)
        save_report(task_id, report)
        set_status(task_id, "failed", report["summary"])
    finally:
        try:
            if file_path.exists():
                file_path.unlink()
        except Exception:
            pass


def parse_options() -> Dict[str, Any]:
    raw_options = request.form.get("options") or "{}"
    try:
        parsed = json.loads(raw_options)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


@app.route("/api/articles/verify", methods=["POST"])
def verify_article():
    payload = request.get_json(silent=True)
    try:
        validated = validate_article_request(payload)
    except PermissionError as exc:
        return error_response("NETWORK_NOT_ALLOWED", str(exc))
    except ConnectionError as exc:
        return error_response("NETWORK_VERIFIER_UNAVAILABLE", str(exc), 503)
    except ArticleContentError as exc:
        message = str(exc)
        if f"{MAX_ARTICLE_CHARS}" in message and "超过" in message:
            code = "ARTICLE_TOO_LARGE"
        elif message.startswith("options."):
            code = "INVALID_OPTIONS"
        else:
            code = "INVALID_ARTICLE_INPUT"
        return error_response(code, message)

    task_id = create_task_id()
    article_input = validated["input"]
    options = validated["options"]
    set_task(
        task_id,
        id=task_id,
        status="received",
        progress=STATUS_META["received"][1],
        message=STATUS_META["received"][0],
        media_type="article",
        title=article_input.get("title") or "未命名文章",
        options=options,
        created_at=now_iso(),
    )
    worker = threading.Thread(
        target=process_article_task,
        args=(task_id, article_input, options),
        daemon=True,
    )
    worker.start()
    return jsonify({"success": True, "task_id": task_id, "status": "received"})


@app.route("/api/media/analyze", methods=["POST"])
def analyze_media():
    if "file" not in request.files:
        return error_response("MISSING_FILE", "请上传图片或视频文件")

    file_storage = request.files["file"]
    try:
        info = validate_upload(file_storage)
    except TypeError as exc:
        return error_response("UNSUPPORTED_FILE_TYPE", str(exc))
    except OverflowError as exc:
        return error_response("FILE_TOO_LARGE", str(exc))
    except ValueError as exc:
        return error_response("INVALID_FILE", str(exc))
    options = parse_options()
    task_id = create_task_id()
    extension = Path(info["filename"]).suffix.lower()
    target_path = UPLOAD_DIR / f"{task_id}{extension}"
    file_storage.save(target_path)

    set_task(
        task_id,
        id=task_id,
        status="received",
        progress=STATUS_META["received"][1],
        message=STATUS_META["received"][0],
        media_type=info["media_type"],
        filename=info["filename"],
        options=options,
        created_at=now_iso(),
    )

    worker = threading.Thread(
        target=process_task,
        args=(task_id, target_path, info["filename"], info["size"], info["media_type"], options),
        daemon=True,
    )
    worker.start()

    return jsonify({"success": True, "task_id": task_id, "status": "received"})


@app.route("/api/tasks/<task_id>", methods=["GET"])
def get_task(task_id: str):
    if not is_valid_task_id(task_id):
        return error_response("INVALID_TASK_ID", "任务编号格式无效")
    task = task_snapshot(task_id)
    if not task:
        return error_response("TASK_NOT_FOUND", "任务不存在", 404)
    return jsonify({
        "success": True,
        "task_id": task_id,
        "status": task.get("status", "received"),
        "progress": task.get("progress", 0),
        "message": task.get("message", ""),
        "media_type": task.get("media_type"),
    })


@app.route("/api/tasks/<task_id>/report", methods=["GET"])
def get_report(task_id: str):
    if not is_valid_task_id(task_id):
        return error_response("INVALID_TASK_ID", "任务编号格式无效")
    task = task_snapshot(task_id)
    report = task.get("report") if task else None
    task_report_path = report_path(task_id)
    if not report and task_report_path.exists():
        report = json.loads(task_report_path.read_text(encoding="utf-8"))
    if not report:
        return error_response("REPORT_NOT_READY", "报告尚未生成", 404)
    return jsonify({"success": True, "report": report})


@app.route("/api/health", methods=["GET"])
def health():
    try:
        response = requests.get(f"{AI_IMAGE_URL}/api/ai/health", timeout=2)
        detector_payload = response.json() if response.content else {}
        image_detector_ready = bool(response.ok and detector_payload.get("model_loaded"))
        image_detector_release_ready = bool(
            image_detector_ready and detector_payload.get("release_qualified") is True
        )
        image_detector_status = {
            "ready": image_detector_ready,
            "release_ready": image_detector_release_ready,
            "http_status": response.status_code,
            "model": detector_payload.get("model"),
            "auxiliary_models": detector_payload.get("auxiliary_models") or [],
            "auxiliary_model_load_errors": detector_payload.get("auxiliary_model_load_errors") or [],
            "runtime_manifest_qualified": detector_payload.get("runtime_manifest_qualified") is True,
            "performance_qualified": detector_payload.get("performance_qualified") is True,
            "commercial_use_qualified": detector_payload.get("commercial_use_qualified") is True,
            "release_qualified": detector_payload.get("release_qualified") is True,
            "release_qualification_reason": detector_payload.get("release_qualification_reason"),
            "runtime_fingerprint": detector_payload.get("runtime_fingerprint"),
            "license_review": detector_payload.get("license_review") or {},
        }
    except Exception as exc:
        image_detector_ready = False
        image_detector_release_ready = False
        image_detector_status = {"ready": False, "error": str(exc)}

    try:
        response = requests.get(f"{AI_IMAGE_URL}/api/text/health", timeout=2)
        detector_payload = response.json() if response.content else {}
        text_detector_ready = bool(
            response.ok and detector_payload.get("model_loaded")
        )
        text_detector_status = {
            "ready": text_detector_ready,
            "release_ready": (
                text_detector_ready
                and detector_payload.get("release_qualified") is True
            ),
            "http_status": response.status_code,
            "model_id": detector_payload.get("model_id"),
            "model_revision": detector_payload.get("model_revision"),
            "policy_version": detector_payload.get("policy_version"),
            "runtime_manifest_qualified": (
                detector_payload.get("runtime_manifest_qualified") is True
            ),
            "performance_qualified": (
                detector_payload.get("performance_qualified") is True
            ),
            "commercial_use_qualified": (
                detector_payload.get("commercial_use_qualified") is True
            ),
            "release_qualified": (
                detector_payload.get("release_qualified") is True
            ),
            "release_qualification_reason": detector_payload.get(
                "release_qualification_reason"
            ),
            "license_review": detector_payload.get("license_review") or {},
        }
    except Exception as exc:
        text_detector_ready = False
        text_detector_status = {"ready": False, "error": str(exc)}

    try:
        response = requests.get(f"{DEEPFAKE_URL}/api/video/health", timeout=4)
        detector_payload = response.json() if response.content else {}
        video_detector_ready = bool(
            response.ok and detector_payload.get("ready") is True
        )
        video_detector_status = {
            "ready": video_detector_ready,
            "http_status": response.status_code,
            "status": detector_payload.get("status"),
            "model_id": detector_payload.get("model_id"),
            "model_version": detector_payload.get("model_version"),
            "policy_version": detector_payload.get("policy_version"),
            "scope": detector_payload.get("scope"),
            "never_certifies_real": detector_payload.get("never_certifies_real") is True,
            "commercial_use_qualified": (
                detector_payload.get("commercial_use_qualified") is True
            ),
            "release_qualified": detector_payload.get("release_qualified") is True,
            "branches": detector_payload.get("branches") or {},
        }
    except Exception as exc:
        video_detector_ready = False
        video_detector_status = {"ready": False, "error": str(exc)}

    return jsonify({
        "status": (
            "healthy"
            if image_detector_ready and text_detector_ready and video_detector_ready
            else "degraded"
        ),
        "release_status": (
            "experimental"
            if image_detector_ready or text_detector_ready or video_detector_ready
            else "unavailable"
        ),
        "service": "zhulong-unified-media-api",
        "ai_image_detector": AI_IMAGE_URL,
        "image_detector": image_detector_status,
        "text_detector": text_detector_status,
        "video_detector": video_detector_status,
        "article_analyzer": {
            "ready": text_detector_ready,
            "mode": "local_ai_style_and_offline_inventory",
            "policy_version": ARTICLE_POLICY_VERSION,
            "network_retrieval": False,
            "claim_verification": False,
            "ai_style_detection": True,
            "authorship_certification": False,
        },
        "image_policy_version": IMAGE_DECISION_POLICY_VERSION,
        "article_policy_version": ARTICLE_POLICY_VERSION,
        "video_policy_version": VIDEO_DECISION_POLICY_VERSION,
        "image_policy_thresholds": IMAGE_DECISION_THRESHOLDS,
        "max_image_bytes": MAX_IMAGE_BYTES,
        "max_image_pixels": MAX_IMAGE_PIXELS,
        "max_article_characters": MAX_ARTICLE_CHARS,
        "persist_reports": PERSIST_REPORTS,
    })


@app.route("/api/info", methods=["GET"])
def info():
    return jsonify({
        "name": "烛龙图片、视频与文字风险分析统一 API",
        "version": "image-video-text-module-v10",
        "supported_media": ["image", "video", "article"],
        "report_persistence": "enabled" if PERSIST_REPORTS else "memory_only",
        "entrypoints": [
            "/api/media/analyze",
            "/api/articles/verify",
            "/api/tasks/<task_id>",
            "/api/tasks/<task_id>/report",
        ],
        "article_scope": (
            "experimental Chinese AI-writing-style signal plus offline claim "
            "inventory; no authorship or truth certification"
        ),
        "video_scope": (
            "local positive-only ensemble for fully generated video and face "
            "manipulation; D3 is auxiliary and negative results never certify real"
        ),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"启动统一媒体检测 API: http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
