from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ─── Shared ─────────────────────────────────────────

T = TypeVar("T")

Platform = Literal["douyin"]


class Page(BaseModel, Generic[T]):
    items: list[T]
    cursor: str | None = None
    total: int | None = None


class ErrorEnvelope(BaseModel):
    error: dict[str, Any]


# ─── Creator ────────────────────────────────────────


def first_grapheme(s: str) -> str:
    if not s:
        return "?"
    s = s.lstrip("@")
    return s[0] if s else "?"


class CreatorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: Platform
    handle: str
    name: str
    initial: str = ""
    bio: str | None = None
    region: str | None = None
    verified: bool
    followers: int
    total_likes: int
    article_count: int = 0
    video_count: int
    recent_update_at: datetime | None = None
    imported_at: datetime

    @classmethod
    def from_model(cls, c, article_count: int = 0) -> CreatorOut:
        return cls(
            id=c.id,
            platform=c.platform,  # type: ignore[arg-type]
            handle=c.handle,
            name=c.name,
            initial=first_grapheme(c.name),
            bio=c.bio,
            region=c.region,
            verified=c.verified,
            followers=c.followers,
            total_likes=c.total_likes,
            article_count=article_count,
            video_count=c.video_count,
            recent_update_at=c.recent_update_at,
            imported_at=c.imported_at,
        )


class ResolveCreatorIn(BaseModel):
    url: str = Field(min_length=1)


# ─── Video ──────────────────────────────────────────


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    creator_id: int
    title: str
    duration_sec: int
    likes: int
    plays: int
    comments: int
    shares: int
    collects: int
    published_at: datetime
    cover_url: str | None
    source_url: str
    article_id: str | None = None


# ─── Article ────────────────────────────────────────


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    video_id: str
    creator_id: int
    title: str
    summary: str
    content_md: str
    content_html: str
    word_count: int
    tags: list[str]
    likes_snapshot: int
    published_at: datetime
    created_at: datetime
    updated_at: datetime


class TranscriptSegmentOut(BaseModel):
    ts_sec: int
    text: str


class ArticleSource(BaseModel):
    platform: Platform
    source_url: str
    duration_sec: int
    metrics: dict[str, int]
    topics: list[str]
    creator_snapshot: dict[str, Any]


class ArticleDetailOut(ArticleOut):
    source: ArticleSource
    segments: list[TranscriptSegmentOut]


class ArticlePatch(BaseModel):
    title: str | None = None
    tags: list[str] | None = None
    content_md: str | None = None


# ─── Task ───────────────────────────────────────────

TaskStage = Literal["download", "transcribe", "organize", "save"]
TaskStatus = Literal["queued", "running", "done", "failed", "canceled"]


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_url: str
    title_guess: str
    creator_id: int | None = None
    creator_name: str | None = None
    creator_initial: str | None = None
    stage: TaskStage
    status: TaskStatus
    progress: int
    eta_sec: int | None = None
    detail: str | None = None
    article_id: UUID | None = None
    error: str | None = None
    started_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None


class TaskCreateIn(BaseModel):
    url: str = Field(min_length=1)


class ResolveIn(BaseModel):
    url: str = Field(min_length=1)


class TaskBatchIn(BaseModel):
    video_ids: list[str] | None = None
    creator_id: int | None = None
    filter: dict[str, Any] | None = None


# ─── Settings ───────────────────────────────────────


class LlmSettings(BaseModel):
    backend: Literal["ollama", "claude"] = "ollama"
    model: str = "qwen2.5:72b"
    concurrency: int = Field(default=2, ge=1, le=20)


class WhisperSettings(BaseModel):
    model: Literal["large-v3", "medium", "small"] = "large-v3"
    language: Literal["zh", "auto"] = "zh"


class PromptSettings(BaseModel):
    version: str = "v1.0"
    template: str = ""


class CookieSettings(BaseModel):
    status: Literal["missing", "ok", "expired"] = "missing"
    last_tested_at: datetime | None = None
    text: str | None = None  # echoed back to the UI so the textarea can show what's stored


class StorageSettings(BaseModel):
    audio_retain_days: int = 7
    used_bytes: int = 0


class SettingsOut(BaseModel):
    llm: LlmSettings
    whisper: WhisperSettings
    prompt: PromptSettings
    cookie: CookieSettings
    storage: StorageSettings


class SettingsPatch(BaseModel):
    llm: LlmSettings | None = None
    whisper: WhisperSettings | None = None
    prompt: PromptSettings | None = None
    cookie: CookieSettings | None = None
    storage: StorageSettings | None = None


class CookiePostIn(BaseModel):
    text: str | None = None


class HealthOut(BaseModel):
    ok: bool
    version: str
    ollama: bool
    whisper: bool
    db: bool
