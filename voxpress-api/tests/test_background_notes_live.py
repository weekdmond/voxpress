from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from voxpress.config import settings
from voxpress.pipeline.dashscope import DashScopeError, DashScopeLLM


def _load_fixture() -> dict:
    path = Path(__file__).parent / "fixtures" / "background_notes" / "yulun_zhan.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.skipif(not settings.dashscope_api_key, reason="DashScope API key is not configured")
async def test_background_notes_live_regression() -> None:
    fixture = _load_fixture()
    llm = DashScopeLLM(model=settings.dashscope_default_llm_model)

    try:
        notes = await llm.annotate_background(
            transcript=fixture["transcript"],
            title_hint=fixture["title_hint"],
            creator_hint=fixture["creator_hint"],
            article_title=fixture["title_hint"],
            article_summary="作者借美伊冲突讨论舆论战、影响力和商战打法。",
        )
    except DashScopeError as exc:
        if "AllocationQuota.FreeTierOnly" in str(exc):
            pytest.skip(f"DashScope quota unavailable for live regression: {exc}")
        raise

    assert notes is not None
    aliases = notes.get("aliases") or []
    assert len(aliases) <= 4
    alias_map = {item["term"]: item for item in aliases if isinstance(item, dict) and item.get("term")}

    for expected in fixture["expected_aliases"]:
        alias = alias_map.get(expected["term"])
        assert alias is not None, f"missing alias for {expected['term']}"
        assert alias["confidence"] in expected["confidence_in"]
        assert any(part in alias["refers_to"] for part in expected["refers_to_contains"])

    serialized = json.dumps(notes, ensure_ascii=False)
    for pattern in fixture["expected_no_patterns"]:
        assert re.search(pattern, serialized) is None, f"unexpected match for pattern: {pattern}"
