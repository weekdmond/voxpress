from __future__ import annotations

from voxpress.jobs.rebackfill_background_notes import (
    _notes_changed,
    _select_transcript_text,
    _sync_prompt_value,
)
from voxpress.prompts import DEFAULT_ORGANIZER_TEMPLATE, DEFAULT_PROMPT_VERSION
from voxpress.schemas import PromptSettings


def test_select_transcript_text_prefers_corrected_text() -> None:
    assert _select_transcript_text(" 修正稿 ", "原稿") == "修正稿"
    assert _select_transcript_text("", " 原稿 ") == "原稿"


def test_notes_changed_ignores_key_order() -> None:
    left = {"aliases": [{"term": "西大", "refers_to": "美国", "confidence": "high"}], "context": "背景"}
    right = {"context": "背景", "aliases": [{"confidence": "high", "refers_to": "美国", "term": "西大"}]}

    assert not _notes_changed(left, right)
    assert _notes_changed(left, None)


def test_sync_prompt_value_sets_version_and_preserves_template() -> None:
    current = {"version": "v1.0", "template": "custom"}

    synced = _sync_prompt_value(current)

    assert synced["version"] == DEFAULT_PROMPT_VERSION
    assert synced["template"] == "custom"


def test_sync_prompt_value_fills_default_template_when_missing() -> None:
    synced = _sync_prompt_value(None)

    assert synced["version"] == DEFAULT_PROMPT_VERSION
    assert synced["template"] == DEFAULT_ORGANIZER_TEMPLATE


def test_prompt_settings_default_version_matches_prompt_constant() -> None:
    assert PromptSettings().version == DEFAULT_PROMPT_VERSION
