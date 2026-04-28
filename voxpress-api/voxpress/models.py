from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from voxpress.db import Base

# ─── creators ───────────────────────────────────────


class Creator(Base):
    __tablename__ = "creators"
    __table_args__ = (
        UniqueConstraint("platform", "external_id", name="uq_creators_platform_extid"),
        Index("idx_creators_followers", "followers"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(Text, nullable=False, default="douyin")
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    handle: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    bio: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    followers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_likes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    video_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recent_update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    videos: Mapped[list[Video]] = relationship(back_populates="creator", cascade="all, delete-orphan")
    articles: Mapped[list[Article]] = relationship(
        back_populates="creator", cascade="all, delete-orphan"
    )


# ─── videos ─────────────────────────────────────────


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (
        Index("idx_videos_creator_published", "creator_id", "published_at"),
        Index("idx_videos_likes", "likes"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    creator_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    duration_sec: Mapped[int] = mapped_column(Integer, nullable=False)
    likes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    plays: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    comments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shares: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    collects: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cover_url: Mapped[str | None] = mapped_column(Text)
    media_object_key: Mapped[str | None] = mapped_column(Text)
    audio_object_key: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    creator: Mapped[Creator] = relationship(back_populates="videos")
    article: Mapped[Article | None] = relationship(back_populates="video", uselist=False)


# ─── articles ───────────────────────────────────────


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        Index("idx_articles_creator_pub", "creator_id", "published_at"),
        Index("idx_articles_topics_gin", "topics", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    video_id: Mapped[str] = mapped_column(
        Text, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    creator_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    content_html: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    topics: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    background_notes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    likes_snapshot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    creator: Mapped[Creator] = relationship(back_populates="articles")
    video: Mapped[Video] = relationship(back_populates="article")
    segments: Mapped[list[TranscriptSegment]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
        order_by="TranscriptSegment.idx",
    )


# ─── transcript_segments ────────────────────────────


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts_sec: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    article: Mapped[Article] = relationship(back_populates="segments")


# ─── transcripts ────────────────────────────────────


class Transcript(Base):
    __tablename__ = "transcripts"
    __table_args__ = (
        CheckConstraint(
            "correction_status IN ('pending','ok','skipped','failed')",
            name="ck_transcripts_correction_status",
        ),
        Index(
            "idx_transcripts_raw_trgm",
            "raw_text",
            postgresql_using="gin",
            postgresql_ops={"raw_text": "gin_trgm_ops"},
        ),
        Index(
            "idx_transcripts_corrected_trgm",
            "corrected_text",
            postgresql_using="gin",
            postgresql_ops={"corrected_text": "gin_trgm_ops"},
        ),
    )

    video_id: Mapped[str] = mapped_column(
        Text, ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    segments: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    corrected_text: Mapped[str | None] = mapped_column(Text)
    corrections: Mapped[list[Any] | None] = mapped_column(JSONB)
    correction_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    initial_prompt_used: Mapped[str | None] = mapped_column(Text)
    whisper_model: Mapped[str | None] = mapped_column(Text)
    whisper_language: Mapped[str | None] = mapped_column(Text)
    corrector_model: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


# ─── tasks ──────────────────────────────────────────


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('download','transcribe','correct','organize','save')", name="ck_tasks_stage"
        ),
        CheckConstraint(
            "status IN ('queued','running','done','failed','canceled')", name="ck_tasks_status"
        ),
        CheckConstraint(
            "trigger_kind IN ('manual','batch','rerun','auto')",
            name="ck_tasks_trigger_kind",
        ),
        Index("idx_tasks_status", "status", "started_at"),
        Index("idx_tasks_creator", "creator_id"),
        Index("idx_tasks_stage_ready", "stage", "status", "run_after"),
        Index("idx_tasks_rerun_of", "rerun_of_task_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title_guess: Mapped[str] = mapped_column(Text, nullable=False, default="")
    creator_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("creators.id", ondelete="SET NULL")
    )
    video_id: Mapped[str | None] = mapped_column(Text)
    trigger_kind: Mapped[str] = mapped_column(Text, nullable=False, default="manual")
    rerun_of_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL")
    )
    resume_from_stage: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(Text, nullable=False, default="download")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    eta_sec: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[str | None] = mapped_column(Text)
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id", ondelete="SET NULL")
    )
    error: Mapped[str | None] = mapped_column(Text)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_cny: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), server_default=func.now()
    )
    lease_owner: Mapped[str | None] = mapped_column(Text)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    creator: Mapped[Creator | None] = relationship()


class TaskArtifact(Base):
    __tablename__ = "task_artifacts"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    transcript_segments: Mapped[list | None] = mapped_column(JSONB)
    organized: Mapped[dict | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TaskStageRun(Base):
    __tablename__ = "task_stage_runs"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('download','transcribe','correct','organize','save')",
            name="ck_task_stage_runs_stage",
        ),
        CheckConstraint(
            "status IN ('queued','running','done','failed','canceled','skipped')",
            name="ck_task_stage_runs_status",
        ),
        UniqueConstraint("task_id", "stage", name="uq_task_stage_runs_task_stage"),
        Index("idx_task_stage_runs_task", "task_id"),
        Index("idx_task_stage_runs_model", "model"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    provider: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_cny: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    detail: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SystemJobRun(Base):
    __tablename__ = "system_job_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','done','failed','skipped')",
            name="ck_system_job_runs_status",
        ),
        CheckConstraint(
            "trigger_kind IN ('scheduled','manual','auto')",
            name="ck_system_job_runs_trigger_kind",
        ),
        Index("idx_system_job_runs_status", "status", "started_at"),
        Index("idx_system_job_runs_job_key", "job_key", "started_at"),
        Index(
            "uq_system_job_runs_running_job_key",
            "job_key",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_key: Mapped[str] = mapped_column(Text, nullable=False)
    job_name: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_kind: Mapped[str] = mapped_column(Text, nullable=False, default="scheduled")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")
    scope: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ─── settings (single-row KV) ───────────────────────


class SettingEntry(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
