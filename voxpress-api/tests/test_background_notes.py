from __future__ import annotations

from voxpress.pipeline.dashscope import _looks_like_meta_context, _normalize_background_notes


def test_normalize_background_notes_discards_low_confidence_and_dedupes() -> None:
    notes = _normalize_background_notes(
        {
            "aliases": [
                {"term": "西大", "refers_to": "美国", "confidence": "high"},
                {"term": "西大", "refers_to": "某企业", "confidence": "medium"},
                {"term": "黄毛", "refers_to": "某政治人物", "confidence": "low"},
            ],
            "context": "",
        }
    )

    assert notes == {
        "aliases": [
            {"term": "西大", "refers_to": "美国", "confidence": "high"},
        ]
    }


def test_normalize_background_notes_drops_generic_meta_context() -> None:
    notes = _normalize_background_notes(
        {
            "aliases": [],
            "context": "全文以地缘冲突为引子，实则聚焦企业传播方法论，所有类比均服务于商业叙事。",
        }
    )

    assert notes is None


def test_meta_context_heuristic_keeps_specific_background() -> None:
    assert not _looks_like_meta_context("西贝指的是西贝莜面村，常被拿来讨论餐饮品牌公关。")
