from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class ExtractorResult:
    video_id: str
    creator_external_id: str
    creator_handle: str
    creator_name: str
    creator_region: str | None
    creator_verified: bool
    creator_followers: int
    creator_total_likes: int
    title: str
    duration_sec: int
    likes: int
    plays: int
    comments: int
    shares: int
    collects: int
    published_at_iso: str
    cover_url: str | None
    source_url: str
    audio_path: Path
    video_path: Path | None = None
    media_object_key: str | None = None
    audio_object_key: str | None = None


@dataclass
class TranscriptResult:
    segments: list[tuple[int, str]]  # (ts_sec, text)
    raw_text: str = ""

    def __post_init__(self) -> None:
        if not self.raw_text:
            self.raw_text = "\n".join(text for _ts, text in self.segments if text).strip()


@runtime_checkable
class Extractor(Protocol):
    """Fetches video metadata + audio file. Implementations: yt-dlp, stub."""

    async def extract(self, url: str) -> ExtractorResult: ...


@runtime_checkable
class Transcriber(Protocol):
    """Turns an audio file into timed segments. Implementations: DashScope ASR, stub."""

    async def transcribe(
        self,
        audio_path: Path,
        language: str = "zh",
        initial_prompt: str | None = None,
    ) -> TranscriptResult: ...


@runtime_checkable
class LLMBackend(Protocol):
    """Turns a raw transcript into a structured article.

    Implementations: DashScopeLLM, stub."""

    async def organize(
        self,
        *,
        transcript: str,
        title_hint: str,
        creator_hint: str,
        prompt_template: str,
        duration_sec: int | None = None,
    ) -> dict: ...  # {title, summary, content_md, tags}

    async def annotate_background(
        self,
        *,
        transcript: str,
        title_hint: str,
        creator_hint: str,
        article_title: str,
        article_summary: str,
        prompt_template: str,
    ) -> dict | None: ...

    async def classify_article(
        self,
        *,
        title: str,
        summary: str,
        content_md: str,
        source_title: str,
        creator_hint: str,
        taxonomy_paths: list[str],
        synonyms: dict[str, str],
    ) -> dict: ...  # {topics, tags, entities}
