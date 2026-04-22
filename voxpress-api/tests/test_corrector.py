from __future__ import annotations

import pytest

from voxpress.pipeline.corrector import (
    CorrectionTooAggressive,
    normalize_correction_changes,
    split_correction_chunks,
    validate_correction_result,
)


def test_split_correction_chunks_prefers_paragraph_boundaries() -> None:
    text = "第一段" + ("甲" * 30) + "\n第二段" + ("乙" * 30) + "\n第三段" + ("丙" * 30)

    chunks = split_correction_chunks(text, max_chars=45)

    assert len(chunks) == 3
    assert chunks[0].startswith("第一段")
    assert chunks[1].startswith("第二段")
    assert chunks[2].startswith("第三段")


def test_normalize_correction_changes_filters_invalid_items() -> None:
    original = "每一交战，化宠为灵，勿接必反。"
    raw = [
        {"from": "每一交战", "to": "媒体交战", "reason": "同音字"},
        {"from": "不存在", "to": "无效", "reason": "应被过滤"},
        {"from": "勿接必反", "to": "无懈必反", "reason": "术语"},
        {"from": "化宠为灵", "to": "化整为零", "reason": "成语"},
        {"from": "同词", "to": "同词", "reason": "无变化"},
    ]

    normalized = normalize_correction_changes(raw, original=original)

    assert normalized == [
        {"from": "每一交战", "to": "媒体交战", "reason": "同音字"},
        {"from": "勿接必反", "to": "无懈必反", "reason": "术语"},
        {"from": "化宠为灵", "to": "化整为零", "reason": "成语"},
    ]


def test_validate_correction_result_accepts_small_edits() -> None:
    original = "每一交战，化宠为灵，勿接必反。"
    corrected = "媒体交战，化整为零，无懈必反。"

    text, changes = validate_correction_result(
        original,
        corrected,
        [
            {"from": "每一交战", "to": "媒体交战", "reason": "同音字"},
            {"from": "化宠为灵", "to": "化整为零", "reason": "成语"},
            {"from": "勿接必反", "to": "无懈必反", "reason": "术语"},
        ],
    )

    assert text == corrected
    assert len(changes) == 3


def test_validate_correction_result_rejects_over_aggressive_rewrite() -> None:
    with pytest.raises(CorrectionTooAggressive):
        validate_correction_result(
            "短句原文",
            "这是一个完全不同的长篇重写版本，长度已经远远偏离原稿。",
            [],
        )
