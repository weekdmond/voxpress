from __future__ import annotations

import httpx
import pytest

from voxpress.pipeline.corrector import (
    CorrectionTooAggressive,
    normalize_correction_changes,
    split_correction_chunks,
    validate_correction_result,
)
from voxpress.pipeline.dashscope import (
    DashScopeChatResult,
    DashScopeCorrector,
    DashScopeError,
    _is_retryable_corrector_error,
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


def _build_dashscope_corrector(client, *, max_attempts: int = 3) -> DashScopeCorrector:
    corrector = object.__new__(DashScopeCorrector)
    corrector.model = "qwen-turbo"
    corrector.template = "template"
    corrector.client = client
    corrector.max_attempts = max_attempts
    corrector.retry_base_delay_sec = 0.0
    return corrector


@pytest.mark.asyncio
async def test_dashscope_corrector_retries_retryable_error(monkeypatch) -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.calls = 0

        async def chat_json_result(self, **_kwargs) -> DashScopeChatResult:
            self.calls += 1
            if self.calls == 1:
                raise DashScopeError("DashScope 对话请求失败: HTTP 429 rate limit")
            return DashScopeChatResult(
                data={"corrected": "修正后的文本", "changes": [{"from": "原文", "to": "修正", "reason": "同音字"}]},
                usage={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2, "cost_cny": 0.0},
            )

    async def _no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("voxpress.pipeline.dashscope.asyncio.sleep", _no_sleep)
    client = FakeClient()
    corrector = _build_dashscope_corrector(client)

    payload = await corrector._correct_chunk("原文", title_hint="标题", creator_hint="作者")

    assert client.calls == 2
    assert payload["corrected"] == "修正后的文本"


@pytest.mark.asyncio
async def test_dashscope_corrector_does_not_retry_non_retryable_error() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.calls = 0

        async def chat_json_result(self, **_kwargs) -> DashScopeChatResult:
            self.calls += 1
            raise DashScopeError("DashScope 对话请求失败: HTTP 400 bad request")

    client = FakeClient()
    corrector = _build_dashscope_corrector(client)

    with pytest.raises(DashScopeError):
        await corrector._correct_chunk("原文", title_hint="标题", creator_hint="作者")

    assert client.calls == 1


def test_is_retryable_corrector_error_recognizes_retryable_failures() -> None:
    assert _is_retryable_corrector_error(DashScopeError("HTTP 429 rate limit"))
    assert _is_retryable_corrector_error(DashScopeError("HTTP 503 upstream unavailable"))
    assert _is_retryable_corrector_error(httpx.ReadTimeout("timed out"))


def test_is_retryable_corrector_error_rejects_non_retryable_failures() -> None:
    assert not _is_retryable_corrector_error(DashScopeError("HTTP 400 bad request"))
