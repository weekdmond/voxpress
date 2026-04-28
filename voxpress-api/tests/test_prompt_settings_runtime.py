from __future__ import annotations

import importlib
from types import SimpleNamespace
from uuid import uuid4

import pytest

from voxpress.pipeline.runner import TaskRunner


@pytest.mark.asyncio
async def test_organize_stage_uses_prompt_settings_for_article_and_background(monkeypatch) -> None:
    runner = TaskRunner()
    runner_module = importlib.import_module("voxpress.pipeline.runner")
    llm = _FakeLLM()

    async def _llm_backend() -> _FakeLLM:
        return llm

    async def _load_prompt_runtime_settings() -> SimpleNamespace:
        return SimpleNamespace(
            organizer_template="custom organizer prompt",
            background_notes_template="custom background prompt",
        )

    async def _load_topic_taxonomy_runtime_settings() -> SimpleNamespace:
        return SimpleNamespace(
            paths=["金融投资/股票市场", "科技数码/AI大模型"],
            synonyms={"AI": "科技数码/AI大模型"},
        )

    async def _load_video_context(_task_id):
        return SimpleNamespace(
            video=SimpleNamespace(
                id="video-1",
                title="视频标题",
                duration_sec=180,
            ),
            creator=SimpleNamespace(name="创作者"),
        )

    async def _load_transcript(_video_id):
        return SimpleNamespace(raw_text="原始逐字稿", corrected_text=None)

    async def _background_notes_enabled() -> bool:
        return True

    monkeypatch.setattr(runner, "_llm_backend", _llm_backend)
    monkeypatch.setattr(runner, "_load_video_context", _load_video_context)
    monkeypatch.setattr(runner, "_load_transcript", _load_transcript)
    monkeypatch.setattr(runner, "background_notes_enabled", _background_notes_enabled)
    monkeypatch.setattr(runner_module, "load_prompt_runtime_settings", _load_prompt_runtime_settings)
    monkeypatch.setattr(
        runner_module,
        "load_topic_taxonomy_runtime_settings",
        _load_topic_taxonomy_runtime_settings,
    )

    organized = await runner.organize_stage(uuid4())

    assert organized["title"] == "整理标题"
    assert organized["topics"] == ["科技数码/AI大模型"]
    assert organized["tags"] == ["AI"]
    assert organized["entities"] == {"creators": ["创作者"], "people": [], "organizations": []}
    assert llm.organize_kwargs["prompt_template"] == "custom organizer prompt"
    assert llm.annotate_kwargs["prompt_template"] == "custom background prompt"
    assert llm.classify_kwargs["taxonomy_paths"] == ["金融投资/股票市场", "科技数码/AI大模型"]


class _FakeLLM:
    def __init__(self) -> None:
        self.organize_kwargs = {}
        self.annotate_kwargs = {}
        self.classify_kwargs = {}

    async def organize(self, **kwargs):
        self.organize_kwargs = kwargs
        return {
            "title": "整理标题",
            "summary": "摘要",
            "content_md": "正文",
            "tags": [],
            "_usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        }

    async def annotate_background(self, **kwargs):
        self.annotate_kwargs = kwargs
        return {
            "aliases": [],
            "_usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        }

    async def classify_article(self, **kwargs):
        self.classify_kwargs = kwargs
        return {
            "topics": ["科技数码/AI大模型"],
            "tags": ["AI"],
            "entities": {"creators": ["创作者"], "people": [], "organizations": []},
            "_usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        }
