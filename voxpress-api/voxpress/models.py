from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
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
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    creator: Mapped[Creator] = relationship(back_populates="videos")
    article: Mapped[Article | None] = relationship(back_populates="video", uselist=False)


# ─── articles ───────────────────────────────────────


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        Index("idx_articles_creator_pub", "creator_id", "published_at"),
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


# ─── tasks ──────────────────────────────────────────


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('download','transcribe','organize','save')", name="ck_tasks_stage"
        ),
        CheckConstraint(
            "status IN ('queued','running','done','failed','canceled')", name="ck_tasks_status"
        ),
        Index("idx_tasks_status", "status", "started_at"),
        Index("idx_tasks_creator", "creator_id"),
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
    stage: Mapped[str] = mapped_column(Text, nullable=False, default="download")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    eta_sec: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[str | None] = mapped_column(Text)
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id", ondelete="SET NULL")
    )
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    creator: Mapped[Creator | None] = relationship()


# ─── settings (single-row KV) ───────────────────────


class SettingEntry(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
