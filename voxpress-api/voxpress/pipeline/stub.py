"""Stub implementations so the backend works end-to-end before real integrations land."""

from __future__ import annotations

import asyncio
import random
from pathlib import Path

from voxpress.pipeline.protocols import (
    Extractor,
    ExtractorResult,
    LLMBackend,
    Transcriber,
    TranscriptResult,
)


class StubExtractor(Extractor):
    async def extract(self, url: str) -> ExtractorResult:
        await asyncio.sleep(0.8)
        seed = abs(hash(url)) % 10_000
        return ExtractorResult(
            video_id=f"stub_{seed}",
            creator_external_id=f"sec_uid_{seed}",
            creator_handle=f"@stub-{seed % 100}",
            creator_name=f"演示创作者 {seed % 100}",
            creator_region="北京",
            creator_verified=seed % 2 == 0,
            creator_followers=100_000 + seed * 37,
            creator_total_likes=500_000 + seed * 128,
            title=f"演示任务 · {url[-24:]}",
            duration_sec=180 + (seed % 600),
            likes=1000 + (seed * 13) % 50_000,
            plays=10_000 + (seed * 101) % 500_000,
            comments=120 + (seed * 7) % 800,
            shares=40 + (seed * 11) % 400,
            collects=300 + (seed * 17) % 2_000,
            published_at_iso="2026-04-18T12:00:00Z",
            cover_url=None,
            source_url=url,
            audio_path=Path(f"/tmp/voxpress/audio/stub_{seed}.m4a"),
        )


class StubTranscriber(Transcriber):
    async def transcribe(
        self,
        audio_path: Path,
        language: str = "zh",
        initial_prompt: str | None = None,
    ) -> TranscriptResult:
        await asyncio.sleep(1.2)
        segments = [
            (0, "这是占位逐字稿第一段。"),
            (18, "接入真实 DashScope ASR 后会替换为实际音频转写。"),
            (42, "第三段内容由 stub 提供。"),
            (78, "系统整体流程已经打通,只差真实后端。"),
        ]
        return TranscriptResult(segments=segments)


class StubLLM(LLMBackend):
    async def organize(
        self,
        *,
        transcript: str,
        title_hint: str,
        creator_hint: str,
        prompt_template: str,
        duration_sec: int | None = None,
    ) -> dict:
        await asyncio.sleep(1.0)
        summary = "这是由 stub LLM 生成的摘要。接入 DashScope 后替换。"
        paragraphs = [
            "这是第一段正文,由占位后端生成。",
            "第二段继续占位。真实后端会严格按照 Prompt 模板把逐字稿整理成结构化文章。",
            f"来源提示:{creator_hint}。",
        ]
        content_md = f"# {title_hint}\n\n> {summary}\n\n" + "\n\n".join(paragraphs)
        tags = random.sample(["AI", "职场", "产品", "创业", "科技观察"], k=2)
        return {
            "title": title_hint,
            "summary": summary,
            "content_md": content_md,
            "tags": tags,
        }

    async def annotate_background(
        self,
        *,
        transcript: str,
        title_hint: str,
        creator_hint: str,
        article_title: str,
        article_summary: str,
    ) -> dict | None:
        await asyncio.sleep(0.2)
        return {
            "aliases": [
                {
                    "term": "占位术语",
                    "refers_to": "示例背景注",
                    "confidence": "high",
                }
            ]
        }
