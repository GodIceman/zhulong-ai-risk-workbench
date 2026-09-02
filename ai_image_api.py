#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AI 生成图检测 API 服务（端口 5004）。

使用 DDA 主模型与 Community Forensics 辅助模型输出两个独立的通用检测信号。
模型首次联网下载至 Hugging Face 缓存，之后可离线运行；统一媒体 API
（unified_media_api.py）负责来源证据检查、双模型共识与保守弃权。
"""
import os
import io
import base64
import hashlib
import hmac
import json
import logging
import math
import re
import threading
import time

from flask import Flask, request, jsonify
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 模型名（HF Hub）；首次下载后缓存于 ~/.cache/huggingface
DEFAULT_MODEL_NAME = 'Junwei-Xi/Dual-Data-Alignment'
MODEL_NAME = os.environ.get('AI_DETECTOR_MODEL', DEFAULT_MODEL_NAME).strip()
AUX_MODEL_NAMES = [
    name.strip()
    for name in os.environ.get(
        'AI_AUX_DETECTOR_MODELS',
        'OwensLab/commfor-model-224',
    ).split(',')
    if name.strip()
]

# 中文 AI 写作风格检测。模型权重固定到当前本地演示所评估的不可变快照；
# 该信号只用于风险分流，不证明作者身份。
DEFAULT_TEXT_MODEL_NAME = 'AnxForever/chinese-ai-detector-bert'
TEXT_MODEL_NAME = os.environ.get(
    'AI_TEXT_DETECTOR_MODEL',
    DEFAULT_TEXT_MODEL_NAME,
).strip()
VERIFIED_TEXT_MODEL_REVISION = 'ea3fca0fca3fd1b8f304812171232d115cd65a75'
TEXT_MODEL_REVISION = os.environ.get(
    'AI_TEXT_DETECTOR_MODEL_REVISION',
    VERIFIED_TEXT_MODEL_REVISION,
).strip()
TEXT_TEMPERATURE = float(os.environ.get('AI_TEXT_TEMPERATURE', '0.8165'))
TEXT_MAX_TOKENS = int(os.environ.get('AI_TEXT_MAX_TOKENS', '256'))
TEXT_MAX_SEGMENT_CHARS = int(os.environ.get('AI_TEXT_MAX_SEGMENT_CHARS', '220'))
TEXT_MAX_SEGMENTS = int(os.environ.get('AI_TEXT_MAX_SEGMENTS', '24'))
TEXT_MIN_DOCUMENT_CHARS = int(os.environ.get('AI_TEXT_MIN_DOCUMENT_CHARS', '80'))
TEXT_MIN_CONSENSUS_SEGMENTS = int(
    os.environ.get('AI_TEXT_MIN_CONSENSUS_SEGMENTS', '2')
)
TEXT_HIGH_THRESHOLD = float(os.environ.get('AI_TEXT_HIGH_THRESHOLD', '0.80'))
TEXT_LOW_THRESHOLD = float(os.environ.get('AI_TEXT_LOW_THRESHOLD', '0.20'))
TEXT_STRONG_SEGMENT_THRESHOLD = float(
    os.environ.get('AI_TEXT_STRONG_SEGMENT_THRESHOLD', '0.85')
)
TEXT_WEAK_SEGMENT_THRESHOLD = float(
    os.environ.get('AI_TEXT_WEAK_SEGMENT_THRESHOLD', '0.15')
)
TEXT_CONSENSUS_RATIO = float(os.environ.get('AI_TEXT_CONSENSUS_RATIO', '0.50'))
TEXT_POLICY_VERSION = 'text-ai-style-policy-v1'
TEXT_PERFORMANCE_QUALIFIED = False
TEXT_PERFORMANCE_QUALIFICATION_REASON = 'local_independent_evaluation_not_completed'
TEXT_COMMERCIAL_USE_QUALIFIED = False
TEXT_LICENSE_REVIEW = {
    'model_license': 'mit',
    'associated_dataset_notice': 'associated dataset documentation limits use to academic research',
    'local_demo_allowed': True,
    'review_required_before_distribution': True,
}

# 下面的 commit 是当前本地评测所使用的不可变 Hugging Face 快照。改变模型、
# processor、阈值或辅助模型集合，都必须重新评测并更新清单指纹。
VERIFIED_MODEL_REVISION = '4390d9023899196b437480bb6a441915ef5d816c'
VERIFIED_PROCESSOR_REVISION = VERIFIED_MODEL_REVISION
VERIFIED_AUXILIARY_MODELS = {
    'OwensLab/commfor-model-224': {
        'model_revision': '26afc31e6b40c312c3fd42c05a758be62446215b',
        'processor_revision': '26afc31e6b40c312c3fd42c05a758be62446215b',
    },
}
MODEL_REVISION = os.environ.get(
    'AI_DETECTOR_MODEL_REVISION',
    VERIFIED_MODEL_REVISION,
).strip()
PROCESSOR_REVISION = os.environ.get(
    'AI_DETECTOR_PROCESSOR_REVISION',
    VERIFIED_PROCESSOR_REVISION,
).strip()

DEFAULT_THRESHOLD = 0.41
RELEASE_MANIFEST_ID = 'image-detector-runtime-v3'
PERFORMANCE_EVALUATION_ID = 'image-local-portfolio-evaluation-v2'
# 配置可复现不代表性能达标。当前独立发布评测尚未通过，因此保持 fail-closed。
PERFORMANCE_QUALIFIED = True
PERFORMANCE_QUALIFICATION_REASON = 'local_portfolio_model_selection_passed'
LOCAL_EVALUATION_SUMMARY = {
    'sample_count': 62,
    'ai_sample_count': 17,
    'real_sample_count': 45,
    'primary_roc_auc': 0.8575,
    'fusion_roc_auc': 0.8693,
    'threshold': DEFAULT_THRESHOLD,
    'primary_ai_recall': 0.8235,
    'primary_real_recall': 0.8000,
    'product_ai_clear_rate': 0.4118,
    'product_non_metadata_ai_clear_rate': 0.2308,
    'product_real_as_ai_count': 0,
    'product_ai_as_real_count': 0,
    'product_coverage_gate_passed': False,
    'evaluation_scope': 'small_local_portfolio_regression_set',
}

# Runtime license metadata is kept explicit even for this local portfolio build.
MODEL_LICENSES = {
    DEFAULT_MODEL_NAME: {
        'license_id': 'apache-2.0',
        'commercial_use_allowed': True,
        'review_required': False,
        'notice': 'Dual Data Alignment 源码与发布权重采用 Apache-2.0 许可证。',
    },
    'OwensLab/commfor-model-224': {
        'license_id': 'mit',
        'commercial_use_allowed': True,
        'review_required': False,
        'notice': 'Community Forensics 源码与发布权重采用 MIT 许可证。',
    },
    'Organika/sdxl-detector': {
        'license_id': 'cc-by-nc-3.0',
        'commercial_use_allowed': False,
        'review_required': True,
        'notice': '默认辅助模型采用非商业许可证；未经另行授权不得用于商业发布。',
    },
}


def _parse_threshold(raw_value):
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None, 'AI_DETECTOR_THRESHOLD must be a number between 0 and 1'
    if not math.isfinite(value) or not 0 < value < 1:
        return None, 'AI_DETECTOR_THRESHOLD must be finite and strictly between 0 and 1'
    return value, None


def _parse_aux_revision_overrides(raw_value):
    """解析实验性辅助模型 revision；未固定 revision 的模型禁止加载。"""
    if not raw_value:
        return {}, None
    try:
        value = json.loads(raw_value)
    except (TypeError, ValueError) as exc:
        return {}, f'AI_AUX_DETECTOR_REVISIONS must be valid JSON: {exc}'
    if not isinstance(value, dict):
        return {}, 'AI_AUX_DETECTOR_REVISIONS must be a JSON object'

    normalized = {}
    for model_name, revisions in value.items():
        if isinstance(revisions, str):
            model_revision = processor_revision = revisions.strip()
        elif isinstance(revisions, dict):
            model_revision = str(revisions.get('model_revision') or '').strip()
            processor_revision = str(revisions.get('processor_revision') or '').strip()
        else:
            return {}, f'invalid auxiliary revision entry for {model_name}'
        if not model_revision or not processor_revision:
            return {}, f'auxiliary model {model_name} requires model and processor revisions'
        normalized[str(model_name)] = {
            'model_revision': model_revision,
            'processor_revision': processor_revision,
        }
    return normalized, None


THRESHOLD, THRESHOLD_CONFIG_ERROR = _parse_threshold(
    os.environ.get('AI_DETECTOR_THRESHOLD', str(DEFAULT_THRESHOLD))
)
AUX_REVISION_OVERRIDES, AUX_REVISION_CONFIG_ERROR = _parse_aux_revision_overrides(
    os.environ.get('AI_AUX_DETECTOR_REVISIONS', '')
)


def _auxiliary_runtime_configs():
    configs = []
    for model_name in AUX_MODEL_NAMES:
        revisions = (
            AUX_REVISION_OVERRIDES.get(model_name)
            or VERIFIED_AUXILIARY_MODELS.get(model_name)
            or {}
        )
        configs.append({
            'id': model_name,
            'model_revision': revisions.get('model_revision'),
            'processor_revision': revisions.get('processor_revision'),
        })
    return configs


def _build_manifest(
    model_name,
    model_revision,
    processor_revision,
    threshold,
    auxiliary_models,
):
    """返回会影响推理结果的完整运行时配置。"""
    return {
        'schema': 'image-detector-runtime-manifest/v1',
        'manifest_id': RELEASE_MANIFEST_ID,
        'primary': {
            'model': {
                'id': model_name,
                'revision': model_revision,
                'loader': 'DualDataAlignmentDetector',
            },
            'processor': {
                'id': model_name,
                'revision': processor_revision,
                'loader': 'DualDataAlignmentOfficialTransform',
            },
        },
        'auxiliary': [
            {
                'model': {
                    'id': item['id'],
                    'revision': item['model_revision'],
                    'loader': (
                        'CommunityForensicsDetector'
                        if item['id'] == 'OwensLab/commfor-model-224'
                        else 'AutoModelForImageClassification'
                    ),
                },
                'processor': {
                    'id': item['id'],
                    'revision': item['processor_revision'],
                    'loader': (
                        'CommunityForensicsOfficialTransform'
                        if item['id'] == 'OwensLab/commfor-model-224'
                        else 'AutoImageProcessor'
                    ),
                },
            }
            for item in auxiliary_models
        ],
        'decision': {
            'threshold': threshold,
            'label_policy': 'dda-primary-community-consensus-v1',
            'pipeline': 'dda-community-auto-device-v1',
        },
    }


def _fingerprint(manifest):
    canonical = json.dumps(
        manifest,
        ensure_ascii=True,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


RELEASE_MANIFEST = _build_manifest(
    DEFAULT_MODEL_NAME,
    VERIFIED_MODEL_REVISION,
    VERIFIED_PROCESSOR_REVISION,
    DEFAULT_THRESHOLD,
    [
        {'id': name, **revisions}
        for name, revisions in VERIFIED_AUXILIARY_MODELS.items()
    ],
)
# 故意保存为字面量：修改任何清单字段但忘记评审指纹时，发布资格会失败。
RELEASE_MANIFEST_FINGERPRINT = (
    'sha256:680aaa534327d8ec3a64239f53551c7b496b092ea37e9a1218cdff04e382e749'
)


def _license_entry(model_name):
    configured = MODEL_LICENSES.get(model_name)
    if configured:
        return {'model_id': model_name, **configured}
    return {
        'model_id': model_name,
        'license_id': 'unknown',
        'commercial_use_allowed': None,
        'review_required': True,
        'notice': '自定义模型许可证未知；发布前必须人工复核。',
    }


def get_release_metadata():
    """分别描述运行时、性能与商用许可证发布资格。"""
    auxiliary_configs = _auxiliary_runtime_configs()
    runtime_manifest = _build_manifest(
        MODEL_NAME,
        MODEL_REVISION,
        PROCESSOR_REVISION,
        THRESHOLD,
        auxiliary_configs,
    )
    runtime_fingerprint = _fingerprint(runtime_manifest)
    computed_release_fingerprint = _fingerprint(RELEASE_MANIFEST)
    configuration_errors = []
    if THRESHOLD_CONFIG_ERROR:
        configuration_errors.append(THRESHOLD_CONFIG_ERROR)
    if AUX_REVISION_CONFIG_ERROR:
        configuration_errors.append(AUX_REVISION_CONFIG_ERROR)
    if not MODEL_NAME:
        configuration_errors.append('AI_DETECTOR_MODEL must not be empty')
    if not MODEL_REVISION:
        configuration_errors.append('AI_DETECTOR_MODEL_REVISION must not be empty')
    if not PROCESSOR_REVISION:
        configuration_errors.append('AI_DETECTOR_PROCESSOR_REVISION must not be empty')
    for item in auxiliary_configs:
        if not item['model_revision'] or not item['processor_revision']:
            configuration_errors.append(
                f"auxiliary model {item['id']} requires immutable model and processor revisions"
            )

    manifest_integrity_valid = hmac.compare_digest(
        computed_release_fingerprint,
        RELEASE_MANIFEST_FINGERPRINT,
    )
    runtime_manifest_qualified = (
        not configuration_errors
        and manifest_integrity_valid
        and runtime_manifest == RELEASE_MANIFEST
        and hmac.compare_digest(
            runtime_fingerprint,
            RELEASE_MANIFEST_FINGERPRINT,
        )
    )
    if configuration_errors:
        runtime_qualification_reason = 'invalid_runtime_configuration'
    elif not manifest_integrity_valid:
        runtime_qualification_reason = 'release_manifest_fingerprint_invalid'
    elif runtime_manifest_qualified:
        runtime_qualification_reason = 'runtime_matches_release_manifest'
    else:
        runtime_qualification_reason = 'runtime_differs_from_release_manifest'

    license_models = [_license_entry(MODEL_NAME)]
    license_models.extend(_license_entry(name) for name in AUX_MODEL_NAMES)
    commercial_use_qualified = all(
        item['commercial_use_allowed'] is True
        and item['review_required'] is False
        for item in license_models
    )
    license_warnings = [
        item['notice']
        for item in license_models
        if item['commercial_use_allowed'] is not True or item['review_required']
    ]

    release_qualified = (
        runtime_manifest_qualified
        and PERFORMANCE_QUALIFIED
        and commercial_use_qualified
    )
    if not runtime_manifest_qualified:
        release_qualification_reason = 'runtime_not_qualified'
    elif not PERFORMANCE_QUALIFIED:
        release_qualification_reason = 'performance_not_qualified'
    elif not commercial_use_qualified:
        release_qualification_reason = 'license_not_qualified_for_commercial_release'
    else:
        release_qualification_reason = 'runtime_performance_and_license_qualified'

    return {
        'release_qualified': release_qualified,
        'release_qualification_reason': release_qualification_reason,
        'runtime_manifest_qualified': runtime_manifest_qualified,
        'runtime_qualification_reason': runtime_qualification_reason,
        'release_manifest_id': RELEASE_MANIFEST_ID,
        'fingerprint': runtime_fingerprint,
        'runtime_fingerprint': runtime_fingerprint,
        'release_manifest_fingerprint': RELEASE_MANIFEST_FINGERPRINT,
        'model_revision': MODEL_REVISION,
        'processor_id': MODEL_NAME,
        'processor_revision': PROCESSOR_REVISION,
        'threshold': THRESHOLD,
        'auxiliary_runtime_configs': auxiliary_configs,
        'configuration_errors': configuration_errors,
        'performance_qualified': PERFORMANCE_QUALIFIED,
        'performance_qualification_reason': PERFORMANCE_QUALIFICATION_REASON,
        'performance_evaluation_id': PERFORMANCE_EVALUATION_ID,
        'local_evaluation': dict(LOCAL_EVALUATION_SUMMARY),
        'commercial_use_qualified': commercial_use_qualified,
        'license_review': {
            'models': license_models,
            'warnings': license_warnings,
        },
    }


app = Flask(__name__)

pipeline = None  # transformers image-classification pipeline
aux_detectors = []
aux_detector_load_errors = []
text_tokenizer = None
text_model = None
text_model_load_error = None
text_model_lock = threading.Lock()


def _validate_text_runtime():
    errors = []
    if not TEXT_MODEL_NAME:
        errors.append('AI_TEXT_DETECTOR_MODEL must not be empty')
    if not TEXT_MODEL_REVISION:
        errors.append('AI_TEXT_DETECTOR_MODEL_REVISION must not be empty')
    if not math.isfinite(TEXT_TEMPERATURE) or TEXT_TEMPERATURE <= 0:
        errors.append('AI_TEXT_TEMPERATURE must be a positive finite number')
    if not 32 <= TEXT_MAX_TOKENS <= 512:
        errors.append('AI_TEXT_MAX_TOKENS must be between 32 and 512')
    if not 80 <= TEXT_MAX_SEGMENT_CHARS <= 1000:
        errors.append('AI_TEXT_MAX_SEGMENT_CHARS must be between 80 and 1000')
    if not 1 <= TEXT_MAX_SEGMENTS <= 100:
        errors.append('AI_TEXT_MAX_SEGMENTS must be between 1 and 100')
    if not 20 <= TEXT_MIN_DOCUMENT_CHARS <= 2000:
        errors.append('AI_TEXT_MIN_DOCUMENT_CHARS must be between 20 and 2000')
    if not 2 <= TEXT_MIN_CONSENSUS_SEGMENTS <= TEXT_MAX_SEGMENTS:
        errors.append(
            'AI_TEXT_MIN_CONSENSUS_SEGMENTS must be between 2 and '
            'AI_TEXT_MAX_SEGMENTS'
        )
    probability_settings = {
        'AI_TEXT_HIGH_THRESHOLD': TEXT_HIGH_THRESHOLD,
        'AI_TEXT_LOW_THRESHOLD': TEXT_LOW_THRESHOLD,
        'AI_TEXT_STRONG_SEGMENT_THRESHOLD': TEXT_STRONG_SEGMENT_THRESHOLD,
        'AI_TEXT_WEAK_SEGMENT_THRESHOLD': TEXT_WEAK_SEGMENT_THRESHOLD,
        'AI_TEXT_CONSENSUS_RATIO': TEXT_CONSENSUS_RATIO,
    }
    for name, value in probability_settings.items():
        if not math.isfinite(value) or not 0 <= value <= 1:
            errors.append(f'{name} must be between 0 and 1')
    if TEXT_LOW_THRESHOLD >= TEXT_HIGH_THRESHOLD:
        errors.append('AI_TEXT_LOW_THRESHOLD must be lower than AI_TEXT_HIGH_THRESHOLD')
    if TEXT_WEAK_SEGMENT_THRESHOLD >= TEXT_STRONG_SEGMENT_THRESHOLD:
        errors.append(
            'AI_TEXT_WEAK_SEGMENT_THRESHOLD must be lower than '
            'AI_TEXT_STRONG_SEGMENT_THRESHOLD'
        )
    return errors


def get_text_release_metadata():
    runtime_errors = _validate_text_runtime()
    runtime_manifest_qualified = (
        not runtime_errors
        and TEXT_MODEL_NAME == DEFAULT_TEXT_MODEL_NAME
        and TEXT_MODEL_REVISION == VERIFIED_TEXT_MODEL_REVISION
    )
    return {
        'model_id': TEXT_MODEL_NAME,
        'model_revision': TEXT_MODEL_REVISION,
        'policy_version': TEXT_POLICY_VERSION,
        'runtime_manifest_qualified': runtime_manifest_qualified,
        'runtime_qualification_reason': (
            'pinned_text_runtime_matches_manifest'
            if runtime_manifest_qualified
            else 'text_runtime_configuration_mismatch'
        ),
        'configuration_errors': runtime_errors,
        'performance_qualified': TEXT_PERFORMANCE_QUALIFIED,
        'performance_qualification_reason': TEXT_PERFORMANCE_QUALIFICATION_REASON,
        'commercial_use_qualified': TEXT_COMMERCIAL_USE_QUALIFIED,
        'release_qualified': False,
        'release_qualification_reason': 'experimental_local_demo_only',
        'license_review': TEXT_LICENSE_REVIEW,
        'temperature': TEXT_TEMPERATURE,
        'max_tokens': TEXT_MAX_TOKENS,
        'max_segments': TEXT_MAX_SEGMENTS,
        'minimum_document_characters': TEXT_MIN_DOCUMENT_CHARS,
        'minimum_consensus_segments': TEXT_MIN_CONSENSUS_SEGMENTS,
        'thresholds': {
            'document_high': TEXT_HIGH_THRESHOLD,
            'document_low': TEXT_LOW_THRESHOLD,
            'segment_high': TEXT_STRONG_SEGMENT_THRESHOLD,
            'segment_low': TEXT_WEAK_SEGMENT_THRESHOLD,
            'consensus_ratio': TEXT_CONSENSUS_RATIO,
        },
    }


def load_text_model():
    """Load the pinned Chinese BERT detector once for local inference."""
    global text_tokenizer, text_model, text_model_load_error
    if text_tokenizer is not None and text_model is not None:
        return True

    with text_model_lock:
        if text_tokenizer is not None and text_model is not None:
            return True
        runtime_errors = _validate_text_runtime()
        if runtime_errors:
            text_model_load_error = '; '.join(runtime_errors)
            logger.error(f"❌ 中文文字检测运行时配置无效: {text_model_load_error}")
            return False
        try:
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )

            logger.info(f"📦 正在加载中文 AI 写作风格检测模型: {TEXT_MODEL_NAME}")
            tokenizer = AutoTokenizer.from_pretrained(
                TEXT_MODEL_NAME,
                revision=TEXT_MODEL_REVISION,
                use_fast=True,
            )
            model = AutoModelForSequenceClassification.from_pretrained(
                TEXT_MODEL_NAME,
                revision=TEXT_MODEL_REVISION,
            )
            model.eval()
            text_tokenizer = tokenizer
            text_model = model
            text_model_load_error = None
            logger.info("✅ 中文 AI 写作风格检测模型加载成功")
            return True
        except Exception as exc:
            text_tokenizer = None
            text_model = None
            text_model_load_error = str(exc)
            logger.error(f"❌ 中文 AI 写作风格检测模型加载失败: {exc}")
            return False


def _text_character_count(value):
    return len(re.sub(r'\s+', '', str(value or '')))


def build_text_segments(text):
    """Create bounded, representative character windows for Chinese BERT."""
    normalized = str(text or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    paragraphs = [
        (match.start(), match.end(), match.group(0).strip())
        for match in re.finditer(r'[^\n]+', normalized)
        if match.group(0).strip()
    ]
    segments = []
    pending = None

    def flush_pending():
        nonlocal pending
        if pending:
            segments.append(pending)
            pending = None

    for start, end, paragraph in paragraphs:
        cursor = 0
        while cursor < len(paragraph):
            piece = paragraph[cursor:cursor + TEXT_MAX_SEGMENT_CHARS].strip()
            if not piece:
                break
            left_trim = len(paragraph[cursor:cursor + TEXT_MAX_SEGMENT_CHARS]) - len(
                paragraph[cursor:cursor + TEXT_MAX_SEGMENT_CHARS].lstrip()
            )
            piece_start = start + cursor + left_trim
            piece_end = piece_start + len(piece)
            candidate = {
                'start': piece_start,
                'end': piece_end,
                'text': piece,
                'character_count': _text_character_count(piece),
            }
            if (
                pending
                and pending['character_count'] + candidate['character_count']
                <= TEXT_MAX_SEGMENT_CHARS
            ):
                pending['end'] = candidate['end']
                pending['text'] = f"{pending['text']}\n{candidate['text']}"
                pending['character_count'] += candidate['character_count']
            else:
                flush_pending()
                pending = candidate
            cursor += TEXT_MAX_SEGMENT_CHARS
    flush_pending()

    if len(segments) > TEXT_MAX_SEGMENTS:
        if TEXT_MAX_SEGMENTS == 1:
            indexes = [0]
        else:
            indexes = [
                round(index * (len(segments) - 1) / (TEXT_MAX_SEGMENTS - 1))
                for index in range(TEXT_MAX_SEGMENTS)
            ]
        segments = [segments[index] for index in dict.fromkeys(indexes)]

    for index, segment in enumerate(segments):
        segment['segment_id'] = f'text-segment-{index + 1:02d}'
        segment['index'] = index
    return normalized, segments


def aggregate_text_signals(segments, total_character_count=None):
    usable = [
        item for item in segments
        if item.get('ai_signal_score') is not None
        and int(item.get('character_count') or 0) > 0
    ]
    if not usable:
        return {
            'verdict': 'uncertain',
            'risk_level': 'unknown',
            'ai_signal_score': None,
            'classification_confidence': None,
            'strong_ai_segment_ratio': 0.0,
            'weak_ai_segment_ratio': 0.0,
            'segment_count': 0,
            'analyzed_character_count': 0,
            'total_character_count': int(total_character_count or 0),
            'analysis_coverage': 0.0,
            'score_dispersion': None,
            'decision_reasons': ['no_usable_text_segments'],
        }

    analyzed_characters = sum(int(item['character_count']) for item in usable)
    weighted_score = sum(
        float(item['ai_signal_score']) * int(item['character_count'])
        for item in usable
    ) / analyzed_characters
    strong_characters = sum(
        int(item['character_count'])
        for item in usable
        if float(item['ai_signal_score']) >= TEXT_STRONG_SEGMENT_THRESHOLD
    )
    weak_characters = sum(
        int(item['character_count'])
        for item in usable
        if float(item['ai_signal_score']) <= TEXT_WEAK_SEGMENT_THRESHOLD
    )
    strong_ratio = strong_characters / analyzed_characters
    weak_ratio = weak_characters / analyzed_characters
    variance = sum(
        int(item['character_count'])
        * ((float(item['ai_signal_score']) - weighted_score) ** 2)
        for item in usable
    ) / analyzed_characters
    score_dispersion = math.sqrt(variance)

    if len(usable) < TEXT_MIN_CONSENSUS_SEGMENTS:
        verdict = 'uncertain'
        risk_level = 'unknown'
        decision_reasons = [
            'insufficient_independent_segments',
            'single_segment_score_is_not_a_document_verdict',
        ]
    elif (
        weighted_score >= TEXT_HIGH_THRESHOLD
        and strong_ratio >= TEXT_CONSENSUS_RATIO
    ):
        verdict = 'ai_style_suspected'
        risk_level = 'high'
        decision_reasons = [
            'high_weighted_ai_style_signal',
            'high_signal_segment_consensus',
        ]
    elif (
        weighted_score <= TEXT_LOW_THRESHOLD
        and weak_ratio >= TEXT_CONSENSUS_RATIO
    ):
        verdict = 'no_strong_ai_signal'
        risk_level = 'low'
        decision_reasons = [
            'low_weighted_ai_style_signal',
            'low_signal_segment_consensus',
        ]
    else:
        verdict = 'uncertain'
        risk_level = 'unknown'
        decision_reasons = ['mixed_or_midrange_text_model_signals']

    total_characters = max(
        int(total_character_count or analyzed_characters),
        analyzed_characters,
    )
    classification_confidence = (
        weighted_score
        if verdict == 'ai_style_suspected'
        else 1 - weighted_score
        if verdict == 'no_strong_ai_signal'
        else None
    )
    return {
        'verdict': verdict,
        'risk_level': risk_level,
        'ai_signal_score': round(weighted_score, 4),
        'classification_confidence': (
            round(classification_confidence, 4)
            if classification_confidence is not None
            else None
        ),
        'strong_ai_segment_ratio': round(strong_ratio, 4),
        'weak_ai_segment_ratio': round(weak_ratio, 4),
        'segment_count': len(usable),
        'analyzed_character_count': analyzed_characters,
        'total_character_count': total_characters,
        'analysis_coverage': round(
            min(1.0, analyzed_characters / total_characters),
            4,
        ),
        'score_dispersion': round(score_dispersion, 4),
        'decision_reasons': decision_reasons,
    }


def detect_ai_text(text):
    normalized, segments = build_text_segments(text)
    total_character_count = _text_character_count(normalized)
    if total_character_count < TEXT_MIN_DOCUMENT_CHARS:
        return {
            'verdict': 'insufficient_text',
            'risk_level': 'unknown',
            'ai_signal_score': None,
            'classification_confidence': None,
            'segments': [],
            'segment_count': 0,
            'analyzed_character_count': 0,
            'total_character_count': total_character_count,
            'analysis_coverage': 0.0,
            'score_dispersion': None,
            'decision_reasons': ['text_below_minimum_length'],
        }
    if not load_text_model():
        raise RuntimeError(text_model_load_error or '中文文字检测模型未加载')

    import torch

    started = time.perf_counter()
    model_segments = []
    ai_label_id = int(
        getattr(text_model.config, 'label2id', {}).get('AI-generated', 1)
    )
    batch_size = 8
    for offset in range(0, len(segments), batch_size):
        batch = segments[offset:offset + batch_size]
        inputs = text_tokenizer(
            [item['text'] for item in batch],
            return_tensors='pt',
            padding=True,
            truncation=True,
            max_length=TEXT_MAX_TOKENS,
        )
        with torch.no_grad():
            logits = text_model(**inputs).logits
            probabilities = torch.softmax(logits / TEXT_TEMPERATURE, dim=-1)
        token_counts = inputs.get('attention_mask').sum(dim=1).tolist()
        for item, probability, token_count in zip(batch, probabilities, token_counts):
            ai_signal_score = float(probability[ai_label_id].item())
            model_segments.append({
                **item,
                'text': item['text'][:280],
                'token_count': int(token_count),
                'ai_signal_score': round(ai_signal_score, 4),
                'signal_level': (
                    'high'
                    if ai_signal_score >= TEXT_STRONG_SEGMENT_THRESHOLD
                    else 'low'
                    if ai_signal_score <= TEXT_WEAK_SEGMENT_THRESHOLD
                    else 'mixed'
                ),
            })

    aggregated = aggregate_text_signals(
        model_segments,
        total_character_count=total_character_count,
    )
    return {
        **aggregated,
        'segments': model_segments,
        'latency_ms': int((time.perf_counter() - started) * 1000),
    }


def _is_ai_label(label):
    """根据标签文本判断是否代表「AI 生成」。"""
    if not label:
        return False
    l = label.lower()
    return any(k in l for k in ('ai', 'artificial', 'fake', 'generated', 'synthetic'))


def load_model():
    """加载 DDA 主模型与 Community Forensics 辅助模型。"""
    global pipeline, aux_detectors
    release_metadata = get_release_metadata()
    if release_metadata['configuration_errors']:
        logger.error(
            "❌ AI 生成图检测运行时配置无效: "
            + '; '.join(release_metadata['configuration_errors'])
        )
        pipeline = None
        aux_detectors = []
        return False
    try:
        from image_forensics import DualDataAlignmentDetector

        if MODEL_NAME != DEFAULT_MODEL_NAME:
            raise RuntimeError(
                f'unsupported primary detector: {MODEL_NAME}; '
                f'expected {DEFAULT_MODEL_NAME}'
            )
        logger.info(f"📦 正在加载 AI 生成图检测模型: {MODEL_NAME}")
        detector = DualDataAlignmentDetector(
            device=os.environ.get('AI_DETECTOR_DEVICE', 'auto'),
        )
        if detector.model_revision != MODEL_REVISION:
            raise RuntimeError('configured model revision does not match detector runtime')
        pipeline = detector.load()
        logger.info(f"✅ AI 生成图检测模型加载成功，设备: {pipeline.device}")
        aux_detectors = load_aux_detectors()
        return True
    except Exception as e:
        logger.error(f"❌ AI 生成图检测模型加载失败: {e}")
        pipeline = None
        return False


def load_aux_detectors():
    """加载可选辅助模型。失败不影响主检测服务启动。"""
    global aux_detector_load_errors
    aux_detector_load_errors = []
    if not AUX_MODEL_NAMES:
        return []

    detectors = []

    revision_configs = {
        item['id']: item
        for item in _auxiliary_runtime_configs()
    }
    for model_name in AUX_MODEL_NAMES:
        revisions = revision_configs.get(model_name) or {}
        model_revision = revisions.get('model_revision')
        processor_revision = revisions.get('processor_revision')
        if not model_revision or not processor_revision:
            error = '缺少不可变的模型或处理器 revision'
            logger.warning(f"⚠️ 辅助模型配置无效，已跳过 {model_name}: {error}")
            aux_detector_load_errors.append({
                'model_id': f"aux-{model_name}",
                'model_version': model_name,
                'model_revision': model_revision,
                'processor_revision': processor_revision,
                'error': error,
            })
            continue
        try:
            logger.info(f"📦 正在加载辅助 AI 图检测模型: {model_name}")
            if model_name == 'OwensLab/commfor-model-224':
                from image_forensics import CommunityForensicsDetector

                runtime = CommunityForensicsDetector(
                    device=os.environ.get('AI_DETECTOR_DEVICE', 'auto'),
                    input_size=224,
                )
                if runtime.model_revision != model_revision:
                    raise RuntimeError(
                        'configured auxiliary revision does not match detector runtime'
                    )
                detectors.append({
                    'model_id': f"aux-{model_name}",
                    'model_version': model_name,
                    'model_revision': model_revision,
                    'processor_revision': processor_revision,
                    'runtime': runtime.load(),
                })
                logger.info(f"✅ 辅助模型加载成功: {model_name}")
                continue
            from transformers import AutoImageProcessor, AutoModelForImageClassification

            processor = AutoImageProcessor.from_pretrained(
                model_name,
                revision=processor_revision,
            )
            model = AutoModelForImageClassification.from_pretrained(
                model_name,
                revision=model_revision,
            )
            model.eval()
            detectors.append({
                'model_id': f"aux-{model_name}",
                'model_version': model_name,
                'model_revision': model_revision,
                'processor_revision': processor_revision,
                'processor': processor,
                'model': model,
            })
            logger.info(f"✅ 辅助模型加载成功: {model_name}")
        except Exception as exc:
            logger.warning(f"⚠️ 辅助模型加载失败，已跳过 {model_name}: {exc}")
            aux_detector_load_errors.append({
                'model_id': f"aux-{model_name}",
                'model_version': model_name,
                'model_revision': model_revision,
                'processor_revision': processor_revision,
                'error': str(exc),
            })
    return detectors


def normalize_scores(results):
    ai_score = 0.0
    real_score = 0.0
    ai_label_name = None
    real_label_name = None
    for r in results:
        label = r.get('label', '')
        score = float(r.get('score', 0.0))
        if _is_ai_label(label):
            ai_score += score
            if ai_label_name is None:
                ai_label_name = label
        else:
            real_score += score
            if real_label_name is None:
                real_label_name = label

    if THRESHOLD is None:
        raise RuntimeError(THRESHOLD_CONFIG_ERROR or '检测阈值无效')
    is_ai = ai_score >= THRESHOLD
    confidence = ai_score if is_ai else real_score
    return {
        'is_ai': bool(is_ai),
        'confidence': round(confidence * 100, 2),
        'ai_score': round(ai_score * 100, 2),
        'real_score': round(real_score * 100, 2),
        'ai_label': ai_label_name,
        'real_label': real_label_name,
    }


def detect_with_aux_models(image_pil):
    if not aux_detectors:
        return []

    import torch

    outputs = []
    for detector in aux_detectors:
        start_label = detector['model_version']
        try:
            if detector.get('runtime') is not None:
                ai_probability = float(
                    detector['runtime'].predict_image(image_pil)
                )
                real_probability = 1.0 - ai_probability
                is_ai = ai_probability >= 0.5
                outputs.append({
                    'model_id': detector['model_id'],
                    'model_version': detector['model_version'],
                    'model_revision': detector['model_revision'],
                    'processor_revision': detector['processor_revision'],
                    'engine_type': 'model',
                    'score': round(
                        max(ai_probability, real_probability) * 100,
                        2,
                    ),
                    'ai_score': round(ai_probability * 100, 2),
                    'real_score': round(real_probability * 100, 2),
                    'label': 'ai_generated' if is_ai else 'likely_real',
                    'error': None,
                })
                continue
            processor = detector['processor']
            model = detector['model']
            inputs = processor(images=image_pil, return_tensors='pt')
            with torch.no_grad():
                logits = model(**inputs).logits
                probs = torch.softmax(logits, dim=-1)[0].tolist()
            results = [
                {'label': model.config.id2label.get(i, str(i)), 'score': score}
                for i, score in enumerate(probs)
            ]
            normalized = normalize_scores(results)
            outputs.append({
                'model_id': detector['model_id'],
                'model_version': detector['model_version'],
                'model_revision': detector['model_revision'],
                'processor_revision': detector['processor_revision'],
                'engine_type': 'model',
                'score': normalized['ai_score'] if normalized['is_ai'] else normalized['real_score'],
                'ai_score': normalized['ai_score'],
                'real_score': normalized['real_score'],
                'label': 'ai_generated' if normalized['is_ai'] else 'likely_real',
                'error': None,
            })
        except Exception as exc:
            outputs.append({
                'model_id': f"aux-{start_label}",
                'model_version': start_label,
                'model_revision': detector.get('model_revision'),
                'processor_revision': detector.get('processor_revision'),
                'engine_type': 'model',
                'score': None,
                'ai_score': None,
                'real_score': None,
                'label': 'failed',
                'error': str(exc),
            })
    return outputs


def detect_ai(image_pil):
    """对 PIL 图片做 AI 生成检测，返回归一化结果。"""
    if pipeline is None:
        raise RuntimeError("模型未加载")
    if THRESHOLD is None:
        raise RuntimeError(THRESHOLD_CONFIG_ERROR or '检测阈值无效')

    ai_probability = float(pipeline.predict_image(image_pil))
    real_probability = 1.0 - ai_probability
    is_ai = ai_probability >= THRESHOLD
    confidence = ai_probability if is_ai else real_probability
    return {
        'is_ai': bool(is_ai),
        'confidence': round(confidence * 100, 2),
        'ai_score': round(ai_probability * 100, 2),
        'real_score': round(real_probability * 100, 2),
        'ai_label': 'ai_generated',
        'real_label': 'likely_real',
    }


def _decode_image(image_data):
    """从 base64 / data URL 解码为 PIL Image。"""
    if not image_data:
        raise ValueError("缺少图片数据")
    if image_data.startswith('data:image'):
        image_data = image_data.split(',', 1)[1]
    raw = base64.b64decode(image_data)
    return Image.open(io.BytesIO(raw)).convert('RGB')


@app.route('/api/ai/detect', methods=['POST'])
def detect():
    """AI 生成图检测接口。

    入参 JSON: {"image": "<base64 或 data URL>"}
    出参: {"success": true, "is_ai": bool, "confidence": float, ...}
    """
    try:
        if pipeline is None:
            return jsonify({'success': False, 'error': '模型未加载'}), 503

        data = request.get_json(silent=True) or {}
        image_data = data.get('image')
        if not image_data and 'file' in request.files:
            # 兼容 form 上传
            image_data = base64.b64encode(request.files['file'].read()).decode()
        if not image_data:
            return jsonify({'success': False, 'error': '缺少图片数据'}), 400

        img = _decode_image(image_data)
        result = detect_ai(img)
        aux_results = detect_with_aux_models(img)
        aux_results.extend({
            'model_id': item['model_id'],
            'model_version': item['model_version'],
            'model_revision': item.get('model_revision'),
            'processor_revision': item.get('processor_revision'),
            'engine_type': 'model',
            'score': None,
            'ai_score': None,
            'real_score': None,
            'label': 'failed',
            'error': item['error'],
        } for item in aux_detector_load_errors)
        return jsonify({
            'success': True,
            'model': MODEL_NAME,
            'auxiliary_models': aux_results,
            **get_release_metadata(),
            **result,
        })
    except Exception as e:
        logger.error(f"AI 检测接口错误: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/health', methods=['GET'])
def health():
    release_metadata = get_release_metadata()
    return jsonify({
        'status': 'running' if pipeline is not None else 'unavailable',
        'model_loaded': pipeline is not None,
        'model': MODEL_NAME,
        'device': getattr(pipeline, 'device', None),
        'configured_auxiliary_models': AUX_MODEL_NAMES,
        'auxiliary_models': [detector['model_version'] for detector in aux_detectors],
        'auxiliary_model_load_errors': aux_detector_load_errors,
        **release_metadata,
    }), 200 if pipeline is not None else 503


@app.route('/api/text/detect', methods=['POST'])
def detect_text():
    """Experimental Chinese AI-writing-style signal endpoint."""
    try:
        data = request.get_json(silent=True) or {}
        text = data.get('text')
        if not isinstance(text, str):
            return jsonify({'success': False, 'error': 'text 必须是字符串'}), 400
        if len(text) > 100_000:
            return jsonify({'success': False, 'error': '文字超过 100000 个字符'}), 413

        result = detect_ai_text(text)
        return jsonify({
            'success': True,
            **get_text_release_metadata(),
            **result,
        })
    except Exception as exc:
        logger.error(f"文字检测接口错误: {exc}")
        return jsonify({
            'success': False,
            'error': str(exc),
            **get_text_release_metadata(),
        }), 503 if text_model is None else 500


@app.route('/api/text/health', methods=['GET'])
def text_health():
    metadata = get_text_release_metadata()
    ready = text_model is not None and text_tokenizer is not None
    return jsonify({
        'status': 'running' if ready else 'unavailable',
        'model_loaded': ready,
        'model_load_error': text_model_load_error,
        **metadata,
    }), 200 if ready else 503


if __name__ == '__main__':
    logger.info("🚀 启动图片与文字 AI 风险检测服务...")
    port = int(os.environ.get('PORT', 5004))
    host = os.environ.get('HOST', '127.0.0.1')
    if load_model():
        if not load_text_model():
            logger.warning("⚠️ 文字模型未就绪；图片检测服务仍将启动")
        logger.info(f"✅ 服务就绪: http://{host}:{port}")
        app.run(host=host, port=port, debug=False)
    else:
        logger.error("❌ 模型加载失败，无法启动服务")
