from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from voxpress.config import settings as app_settings
from voxpress.prompts import DEFAULT_PROMPT_VERSION

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
    external_id: str
    handle: str
    name: str
    initial: str = ""
    bio: str | None = None
    region: str | None = None
    avatar_url: str | None = None
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
            external_id=c.external_id,
            handle=c.handle,
            name=c.name,
            initial=first_grapheme(c.name),
            bio=c.bio,
            region=c.region,
            avatar_url=c.avatar_url,
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
    updated_at: datetime
    cover_url: str | None
    source_url: str
    article_id: str | None = None
    media_url: str | None = None

    @classmethod
    def from_model(cls, v, *, article_id: str | None = None) -> VideoOut:
        media_url = f"/api/videos/{v.id}/media" if getattr(v, "media_object_key", None) else None
        return cls(
            id=v.id,
            creator_id=v.creator_id,
            title=v.title,
            duration_sec=v.duration_sec,
            likes=v.likes,
            plays=v.plays,
            comments=v.comments,
            shares=v.shares,
            collects=v.collects,
            published_at=v.published_at,
            updated_at=v.updated_at,
            cover_url=v.cover_url,
            source_url=v.source_url,
            article_id=article_id,
            media_url=media_url,
        )


class VideoSummaryOut(BaseModel):
    total: int
    organized: int
    pending: int


# ─── Article ────────────────────────────────────────


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    video_id: str
    creator_id: int
    latest_task_id: UUID | None = None
    cover_url: str | None = None
    title: str
    summary: str
    content_md: str
    content_html: str
    word_count: int
    tags: list[str]
    background_notes: dict[str, Any] | None = None
    likes_snapshot: int
    duration_sec: int = 0
    cost_cny: float = 0
    published_at: datetime
    created_at: datetime
    updated_at: datetime


class TranscriptSegmentOut(BaseModel):
    ts_sec: int
    text: str


class ArticleSource(BaseModel):
    platform: Platform
    source_url: str
    media_url: str | None = None
    duration_sec: int
    metrics: dict[str, int]
    topics: list[str]
    creator_snapshot: dict[str, Any]


class ArticleDetailOut(ArticleOut):
    source: ArticleSource
    segments: list[TranscriptSegmentOut]
    raw_text: str | None = None
    corrected_text: str | None = None
    correction_status: Literal["pending", "ok", "skipped", "failed"] | None = None
    corrections: list[dict[str, Any]] = Field(default_factory=list)
    whisper_model: str | None = None
    whisper_language: str | None = None
    corrector_model: str | None = None
    initial_prompt_used: str | None = None


class ArticlePatch(BaseModel):
    title: str | None = None
    tags: list[str] | None = None
    content_md: str | None = None


RebuildStage = Literal["download", "transcribe", "correct", "organize"]


class ArticleBatchIn(BaseModel):
    article_ids: list[UUID] = Field(min_length=1, max_length=200)
    from_stage: RebuildStage | None = None


class ArticleRebuildIn(BaseModel):
    from_stage: RebuildStage | None = None


class ArticleBatchOut(BaseModel):
    requested: int
    matched: int
    processed: int
    task_ids: list[UUID] = Field(default_factory=list)
    missing_ids: list[UUID] = Field(default_factory=list)


# ─── Task ───────────────────────────────────────────

TaskStage = Literal["download", "transcribe", "correct", "organize", "save"]
TaskStatus = Literal["queued", "running", "done", "failed", "canceled"]
TaskTriggerKind = Literal["manual", "batch", "rerun"]
SystemJobStatus = Literal["running", "done", "failed", "skipped"]


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
    article_title: str | None = None
    cover_url: str | None = None
    error: str | None = None
    trigger_kind: TaskTriggerKind = "manual"
    rerun_of_task_id: UUID | None = None
    resume_from_stage: TaskStage | None = None
    primary_model: str | None = None
    elapsed_ms: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_cny: float = 0
    started_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None


class TaskStageRunOut(BaseModel):
    stage: TaskStage
    status: Literal["queued", "running", "done", "failed", "canceled", "skipped"]
    provider: str | None = None
    model: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_cny: float = 0
    detail: str | None = None
    error: str | None = None


class TaskFacetItemOut(BaseModel):
    value: str
    count: int


class TaskSummaryOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    today_tasks: int
    today_success_rate: float
    today_cost_cny: float
    today_total_tokens: int
    avg_elapsed_ms: int
    status_counts: dict[str, int]
    model_facets: list[TaskFacetItemOut] = Field(default_factory=list)


class TaskDetailOut(TaskOut):
    stage_runs: list[TaskStageRunOut] = Field(default_factory=list)
    available_rerun_modes: dict[str, bool] = Field(default_factory=dict)


class TaskRerunIn(BaseModel):
    task_ids: list[UUID] = Field(min_length=1, max_length=200)
    mode: Literal["resume", "organize", "full"]


class TaskRerunOut(BaseModel):
    requested: int
    processed: int
    task_ids: list[UUID] = Field(default_factory=list)
    skipped_ids: list[UUID] = Field(default_factory=list)


class TaskCancelBatchIn(BaseModel):
    task_ids: list[UUID] = Field(min_length=1, max_length=200)


class TaskCancelBatchOut(BaseModel):
    requested: int
    processed: int
    skipped_ids: list[UUID] = Field(default_factory=list)


class TaskCreateIn(BaseModel):
    url: str = Field(min_length=1)


class SystemJobRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_key: str
    job_name: str
    trigger_kind: Literal["scheduled", "manual"] = "scheduled"
    status: SystemJobStatus
    scope: str | None = None
    detail: str | None = None
    error: str | None = None
    total_items: int = 0
    processed_items: int = 0
    failed_items: int = 0
    skipped_items: int = 0
    duration_ms: int | None = None
    started_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None


class SystemJobSummaryOut(BaseModel):
    today_runs: int
    today_success_rate: float
    today_processed_items: int
    today_failed_items: int
    avg_duration_ms: int
    status_counts: dict[str, int]


class ResolveIn(BaseModel):
    url: str = Field(min_length=1)


class TaskBatchIn(BaseModel):
    video_ids: list[str] | None = None
    creator_id: int | None = None
    filter: dict[str, Any] | None = None


# ─── Settings ───────────────────────────────────────


class LlmSettings(BaseModel):
    backend: Literal["dashscope"] = "dashscope"
    model: str = Field(default_factory=lambda: app_settings.dashscope_default_llm_model)
    concurrency: int = Field(default=4, ge=1, le=20)


class WhisperSettings(BaseModel):
    model: str = Field(default_factory=lambda: app_settings.dashscope_default_asr_model)
    language: Literal["zh", "auto"] = "zh"
    enable_initial_prompt: bool = True


class CorrectorSettings(BaseModel):
    enabled: bool = True
    model: str = Field(default_factory=lambda: app_settings.dashscope_default_corrector_model)
    template: str = ""


class ArticleSettings(BaseModel):
    generate_background_notes: bool = True


class PromptSettings(BaseModel):
    version: str = DEFAULT_PROMPT_VERSION
    template: str = ""


class CookieSettings(BaseModel):
    status: Literal["missing", "ok", "expired"] = "missing"
    last_tested_at: datetime | None = None
    source_name: str | None = None


class DashScopeSettingsOut(BaseModel):
    configured: bool = False
    base_url: str = Field(default_factory=lambda: app_settings.dashscope_compatible_base_url)


class DashScopeSettingsPatch(BaseModel):
    api_key: str | None = None
    base_url: str | None = None


class StorageSettings(BaseModel):
    audio_retain_days: int = 7
    used_bytes: int = 0


class OssSettingsOut(BaseModel):
    configured: bool = False
    region: str | None = None
    endpoint: str | None = None
    bucket: str | None = None


class OssSettingsPatch(BaseModel):
    region: str | None = None
    endpoint: str | None = None
    bucket: str | None = None
    access_key_id: str | None = None
    access_key_secret: str | None = None


class SettingsOut(BaseModel):
    llm: LlmSettings
    whisper: WhisperSettings
    corrector: CorrectorSettings
    article: ArticleSettings
    prompt: PromptSettings
    cookie: CookieSettings
    dashscope: DashScopeSettingsOut
    oss: OssSettingsOut
    storage: StorageSettings


class SettingsPatch(BaseModel):
    llm: LlmSettings | None = None
    whisper: WhisperSettings | None = None
    corrector: CorrectorSettings | None = None
    article: ArticleSettings | None = None
    prompt: PromptSettings | None = None
    cookie: CookieSettings | None = None
    dashscope: DashScopeSettingsPatch | None = None
    oss: OssSettingsPatch | None = None
    storage: StorageSettings | None = None


class HealthOut(BaseModel):
    ok: bool
    version: str
    ollama: bool
    whisper: bool
    db: bool
