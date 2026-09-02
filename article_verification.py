#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Deterministic, offline preparation for claim-level article verification.

This module inventories source declarations, links, and checkable claims. It
never estimates AI authorship and never treats model knowledge as fact evidence.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


ARTICLE_POLICY_VERSION = "article-verification-policy-v1"
MAX_ARTICLE_CHARS = 100_000
MAX_ARTICLE_TITLE_CHARS = 500
MAX_ARTICLE_URLS = 100
MAX_CANDIDATE_CLAIMS = 30
DEFAULT_MAX_MATERIAL_CLAIMS = 20

URL_PATTERN = re.compile(r"https?://[^\s<>{}\[\]\"']+", re.IGNORECASE)
REFERENCE_PATTERN = re.compile(r"\[(\d{1,3})\]")
NUMBER_PATTERN = re.compile(
    r"(?<![\w.])(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"
    r"(?:\s*[%％‰万亿千百元美元欧元人次件项倍年月日小时分钟秒公里米吨克GBMB])?"
)
DATE_PATTERN = re.compile(
    r"(?:19|20)\d{2}(?:[-/.年]\d{1,2})?(?:[-/.月]\d{1,2}日?)?"
    r"|\d{1,2}月\d{1,2}日"
)
SENTENCE_PATTERN = re.compile(r"[^\n。！？!?]+[。！？!?]?")
ATTRIBUTION_MARKERS = (
    "表示",
    "称",
    "宣布",
    "指出",
    "报告显示",
    "数据显示",
    "研究发现",
    "据报道",
    "据悉",
    "according to",
    "reported",
    "announced",
    "said",
)
CAUSAL_MARKERS = (
    "导致",
    "造成",
    "因此",
    "由于",
    "增长",
    "下降",
    "上升",
    "减少",
    "增加",
    "创下",
    "最大",
    "最小",
    "首次",
    "最新",
    "because",
    "caused",
    "increased",
    "decreased",
    "largest",
    "first",
    "latest",
)
OPINION_MARKERS = (
    "我认为",
    "本文认为",
    "笔者认为",
    "建议",
    "应该",
    "或许",
    "可能",
    "预计",
    "in my opinion",
    "we believe",
    "should",
    "might",
    "may ",
    "expected to",
)
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


class ArticleContentError(ValueError):
    """Raised when article input cannot be safely normalized."""


def normalize_article_text(text: Any) -> str:
    if not isinstance(text, str):
        raise ArticleContentError("文章正文必须是字符串")
    normalized = (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\x00", "")
        .strip()
    )
    if not normalized:
        raise ArticleContentError("文章正文为空")
    if len(normalized) > MAX_ARTICLE_CHARS:
        raise ArticleContentError(f"文章正文超过 {MAX_ARTICLE_CHARS} 个字符")
    control_chars = sum(
        1
        for char in normalized
        if ord(char) < 32 and char not in {"\n", "\t", "\f"}
    )
    if control_chars > max(4, len(normalized) // 200):
        raise ArticleContentError("文章正文包含过多不可打印字符")
    return normalized


def decode_article_bytes(raw: bytes) -> Tuple[str, str]:
    if not raw:
        raise ArticleContentError("文章内容为空")
    encodings = ["utf-8-sig"]
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings.insert(0, "utf-16")
    encodings.append("gb18030")
    for encoding in encodings:
        try:
            return normalize_article_text(raw.decode(encoding)), encoding
        except UnicodeDecodeError:
            continue
    raise ArticleContentError("文章文本编码无法识别，请使用 UTF-8、UTF-16 或 GB18030")


def _trimmed_span(text: str, start: int, end: int) -> Tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _strip_url_punctuation(value: str) -> str:
    return value.rstrip(".,;:!?，。；：！？、）)]}》」』")


def canonicalize_url(value: str) -> str:
    parsed = urlsplit(value)
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in TRACKING_QUERY_KEYS
    ]
    host = (parsed.hostname or "").lower().rstrip(".")
    port = parsed.port
    if port and not (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    else:
        netloc = host
    return urlunsplit(
        (
            parsed.scheme.lower(),
            netloc,
            parsed.path or "/",
            urlencode(query, doseq=True),
            "",
        )
    )


def extract_sources(text: str) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    by_canonical: Dict[str, Dict[str, Any]] = {}
    for match in URL_PATTERN.finditer(text):
        raw_url = _strip_url_punctuation(match.group(0))
        end = match.start() + len(raw_url)
        try:
            parsed = urlsplit(raw_url)
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
                continue
            canonical_url = canonicalize_url(raw_url)
        except ValueError:
            continue

        occurrence = {
            "start": match.start(),
            "end": end,
            "quote": text[match.start():end],
        }
        existing = by_canonical.get(canonical_url)
        if existing:
            existing["occurrences"].append(occurrence)
            continue

        item = {
            "source_id": f"source-{len(sources) + 1:03d}",
            "source_role": "inline_link",
            "raw_url": raw_url,
            "canonical_url": canonical_url,
            "domain": parsed.hostname.lower().rstrip("."),
            "title": None,
            "publisher": None,
            "author": None,
            "published_at": None,
            "verification_status": "not_fetched",
            "source_class": "unknown",
            "retrieved_at": None,
            "snapshot_sha256": None,
            "quality_flags": ["offline_mode"],
            "occurrences": [occurrence],
        }
        by_canonical[canonical_url] = item
        sources.append(item)
        if len(sources) >= MAX_ARTICLE_URLS:
            break
    return sources


def _paragraph_index(text: str, position: int) -> int:
    prefix = text[:position]
    return len(re.findall(r"\n\s*\n", prefix))


def iter_sentence_spans(text: str) -> Iterable[Tuple[int, int, str]]:
    masked_chars = list(text)
    for url_match in URL_PATTERN.finditer(text):
        for index in range(url_match.start(), url_match.end()):
            if masked_chars[index] in {"?", "!", "？", "！"}:
                masked_chars[index] = "x"
    masked_text = "".join(masked_chars)
    for match in SENTENCE_PATTERN.finditer(masked_text):
        start, end = _trimmed_span(text, match.start(), match.end())
        if start >= end:
            continue
        quote = text[start:end]
        if quote.startswith("```") or quote.endswith("```"):
            continue
        yield start, end, quote


def _analysis_text(quote: str) -> str:
    value = re.sub(r"^\s{0,3}(?:#{1,6}|[-*+]|>\s*)\s*", "", quote.strip())
    return re.sub(r"\s+", " ", value).strip()


def _claim_signals(sentence: str) -> List[str]:
    lower = sentence.lower()
    signals: List[str] = []
    if DATE_PATTERN.search(sentence):
        signals.append("date_or_time")
    if NUMBER_PATTERN.search(sentence):
        signals.append("quantitative")
    if any(marker in lower for marker in ATTRIBUTION_MARKERS):
        signals.append("attribution")
    if any(marker in lower for marker in CAUSAL_MARKERS):
        signals.append("causal_or_comparative")
    if URL_PATTERN.search(sentence) or REFERENCE_PATTERN.search(sentence):
        signals.append("source_reference")
    if any(marker in lower for marker in OPINION_MARKERS):
        signals.append("opinion_or_prediction")
    return signals


def _missing_evidence(signals: List[str], has_source: bool) -> List[str]:
    if has_source:
        return ["需读取引用来源正文，并核对其是否直接支持该声明"]
    missing = ["缺少可实际读取并定位的外部来源"]
    if "quantitative" in signals:
        missing.append("数值需要原始数据、报告或统计口径")
    if "attribution" in signals:
        missing.append("归属表述需要原始声明、公告或完整采访记录")
    if "causal_or_comparative" in signals:
        missing.append("因果或比较表述需要适用范围、基准与时间信息")
    return missing


def extract_claims(
    text: str,
    max_material_claims: int = DEFAULT_MAX_MATERIAL_CLAIMS,
) -> List[Dict[str, Any]]:
    claims: List[Dict[str, Any]] = []
    material_count = 0
    for start, end, quote in iter_sentence_spans(text):
        sentence = _analysis_text(quote)
        if len(sentence) < 10 or URL_PATTERN.fullmatch(sentence):
            continue
        non_source_text = URL_PATTERN.sub("", sentence)
        non_source_text = REFERENCE_PATTERN.sub("", non_source_text)
        non_source_text = non_source_text.strip(" \t-—:：,，.;；。")
        if len(non_source_text) < 10:
            continue
        signals = _claim_signals(sentence)
        opinion = "opinion_or_prediction" in signals
        factual_signals = [
            value
            for value in signals
            if value not in {"opinion_or_prediction", "source_reference"}
        ]
        general_declarative = (
            len(sentence) >= 20
            and not sentence.endswith(("：", ":", "？", "?"))
            and not opinion
        )
        if not factual_signals and not general_declarative and not opinion:
            continue

        checkability = "out_of_scope" if opinion else "checkable"
        if checkability == "checkable" and material_count >= max_material_claims:
            continue
        if checkability == "checkable":
            material_count += 1

        has_source = "source_reference" in signals
        materiality = (
            "high"
            if {"quantitative", "attribution", "causal_or_comparative"}.intersection(signals)
            else "medium"
        )
        claim = {
            "claim_id": f"claim-{len(claims) + 1:03d}",
            "text": sentence[:500],
            "source_span": {
                "start": start,
                "end": end,
                "quote": quote,
            },
            "paragraph_index": _paragraph_index(text, start),
            "claim_type": "factual" if checkability == "checkable" else "opinion_or_prediction",
            "materiality": materiality,
            "checkability": checkability,
            "signals": signals,
            "assessment": "not_checked" if checkability == "checkable" else "out_of_scope",
            "assessment_reason": "offline_mode" if checkability == "checkable" else "non_factual_statement",
            "evidence_links": [],
            "missing_evidence": (
                _missing_evidence(signals, has_source)
                if checkability == "checkable"
                else []
            ),
        }
        if text[start:end] != claim["source_span"]["quote"]:
            continue
        claims.append(claim)
        if len(claims) >= MAX_CANDIDATE_CLAIMS:
            break
    return claims


def extract_title(text: str, supplied_title: str = "") -> str:
    supplied = supplied_title.strip()
    if supplied:
        return supplied[:MAX_ARTICLE_TITLE_CHARS]
    for line in text.splitlines():
        candidate = _analysis_text(line)
        if candidate and candidate not in {"---", "***"}:
            return candidate[:MAX_ARTICLE_TITLE_CHARS]
    return "未命名文章"


def normalize_declared_origin(
    declared_url: str = "",
    declared_author: str = "",
    declared_published_at: str = "",
) -> Dict[str, Any]:
    values = {
        "url": declared_url.strip()[:2000],
        "author": declared_author.strip()[:500],
        "published_at": declared_published_at.strip()[:100],
    }
    if not any(values.values()):
        return {}
    values["verification_status"] = "unverified_user_declaration"
    return values


def analyze_article_text(
    text: str,
    title: str = "",
    declared_url: str = "",
    declared_author: str = "",
    declared_published_at: str = "",
    max_material_claims: int = DEFAULT_MAX_MATERIAL_CLAIMS,
) -> Dict[str, Any]:
    normalized = normalize_article_text(text)
    sources = extract_sources(normalized)
    claims = extract_claims(normalized, max_material_claims=max_material_claims)
    material_claims = [
        claim for claim in claims if claim.get("checkability") == "checkable"
    ]
    out_of_scope = [
        claim for claim in claims if claim.get("checkability") == "out_of_scope"
    ]
    declared_origin = normalize_declared_origin(
        declared_url,
        declared_author,
        declared_published_at,
    )
    chinese_chars = len(re.findall(r"[\u3400-\u9fff]", normalized))
    latin_tokens = len(
        re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*", normalized)
    )
    return {
        "normalized_text": normalized,
        "content_sha256": f"sha256:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}",
        "title": extract_title(normalized, title),
        "character_count": len(normalized),
        "language_token_estimate": chinese_chars + latin_tokens,
        "paragraph_count": len(
            [part for part in re.split(r"\n\s*\n", normalized) if part.strip()]
        ),
        "sentence_count": len(list(iter_sentence_spans(normalized))),
        "declared_origin": declared_origin,
        "sources": sources,
        "claims": claims,
        "candidate_claim_count": len(claims),
        "material_claim_count": len(material_claims),
        "out_of_scope_claim_count": len(out_of_scope),
        "explicit_source_count": len(sources),
        "analysis_scope": "offline_inventory",
    }


def analyze_article_bytes(
    raw: bytes,
    filename: str = "",
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    text, encoding = decode_article_bytes(raw)
    options = options or {}
    analysis = analyze_article_text(
        text,
        title=str(options.get("title") or filename),
        declared_url=str(options.get("declared_url") or ""),
        declared_author=str(options.get("declared_author") or ""),
        declared_published_at=str(options.get("declared_published_at") or ""),
        max_material_claims=int(
            options.get("max_material_claims") or DEFAULT_MAX_MATERIAL_CLAIMS
        ),
    )
    analysis["encoding"] = encoding
    return analysis
