"""Load the pinned text detector and print a compact local inference report."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ai_image_api


SAMPLES = {
    "structured_explanation": (
        "人工智能生成文本检测并不是作者身份认证。实际使用时，需要把模型分数、"
        "文本长度、文体差异和人工复核放在一起考虑。尤其是经过改写的文章，"
        "可能同时包含人工表达和模型生成片段，因此系统应该允许返回不确定结果，"
        "而不是把每篇文章简单分成机器或人类两类。"
    ),
    "personal_note": (
        "上周六我去城南修那辆旧自行车，老板先说半小时能好，结果发现后轮里还卡着一小截铁丝。"
        "我坐在门口等了快两个小时，顺手把旁边早餐店剩下的豆浆喝完了。回家时天已经暗了，"
        "链条还是偶尔会响，不过骑到桥上有风，心情倒比出门时轻松很多。"
    ),
}


def main():
    started = time.perf_counter()
    if not ai_image_api.load_text_model():
        raise RuntimeError(ai_image_api.text_model_load_error or "text model failed to load")

    model = ai_image_api.text_model
    output = {
        "model_id": ai_image_api.TEXT_MODEL_NAME,
        "model_revision": ai_image_api.TEXT_MODEL_REVISION,
        "labels": getattr(model.config, "id2label", {}),
        "load_seconds": round(time.perf_counter() - started, 2),
        "samples": {},
    }
    for name, text in SAMPLES.items():
        result = ai_image_api.detect_ai_text(text)
        output["samples"][name] = {
            "verdict": result["verdict"],
            "ai_signal_score": result["ai_signal_score"],
            "segment_count": result["segment_count"],
            "latency_ms": result["latency_ms"],
        }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
