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


@dataclass
class TranscriptResult:
    segments: list[tuple[int, str]]  # (ts_sec, text)


@runtime_checkable
class Extractor(Protocol):
    """Fetches video metadata + audio file. Implementations: yt-dlp, stub."""

    async def extract(self, url: str) -> ExtractorResult: ...


@runtime_checkable
class Transcriber(Protocol):
    """Turns an audio file into timed segments. Implementations: mlx-whisper, faster-whisper, stub."""

    async def transcribe(self, audio_path: Path, language: str = "zh") -> TranscriptResult: ...


@runtime_checkable
class LLMBackend(Protocol):
    """Turns a raw transcript into a structured article.

    Implementations: OllamaLLM, (future) ClaudeLLM, stub."""

    async def organize(
        self,
        *,
        transcript: str,
        title_hint: str,
        creator_hint: str,
        prompt_template: str,
    ) -> dict: ...  # {title, summary, content_md, content_html, word_count, tags}
