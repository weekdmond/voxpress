"""Pipeline runner.

* One global limiter controls whole-pipeline concurrency (downloads +
  transcription + LLM are all gated by it so we can't DOS ourselves
  with 50 URLs at once).
* Task state transitions publish SSE events via the broker.
* Startup reconciliation marks orphan `running`/`queued` tasks as `failed`
  (they died with the previous process).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from voxpress.config import settings as app_settings
from voxpress.db import session_scope
from voxpress.models import Article, Creator, SettingEntry, Task, TranscriptSegment, Video
from voxpress.pipeline.protocols import Extractor, LLMBackend, Transcriber
from voxpress.pipeline.stub import StubExtractor, StubLLM, StubTranscriber
from voxpress.sse import TaskEvent, broker

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _task_to_payload(t: Task, creator: Creator | None = None) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "source_url": t.source_url,
        "title_guess": t.title_guess,
        "creator_id": t.creator_id,
        "creator_name": creator.name if creator else None,
        "creator_initial": (creator.name[0] if creator and creator.name else None),
        "stage": t.stage,
        "status": t.status,
        "progress": t.progress,
        "eta_sec": t.eta_sec,
        "detail": t.detail,
        "article_id": str(t.article_id) if t.article_id else None,
        "error": t.error,
        "started_at": t.started_at.isoformat() if t.started_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "finished_at": t.finished_at.isoformat() if t.finished_at else None,
    }


class TaskRunner:
    def __init__(self) -> None:
        self._default_concurrency = app_settings.max_pipeline_concurrency
        self._concurrency_limit = app_settings.max_pipeline_concurrency
        self._running = 0
        self._gate = asyncio.Condition()
        self._inflight: dict[UUID, asyncio.Task] = {}

    async def _backends(self) -> tuple[Extractor, Transcriber, LLMBackend]:
        """Pick backends at task-start so settings changes apply without restart."""
        if app_settings.pipeline == "stub":
            return StubExtractor(), StubTranscriber(), StubLLM()

        # Real pipeline — lazy-import so stub mode never loads mlx/yt-dlp.
        from voxpress.pipeline.mlx import MlxWhisperTranscriber
        from voxpress.pipeline.ollama import OllamaLLM
        from voxpress.pipeline.ytdlp import YtDlpExtractor

        cookie_row = await self._load_settings_entry("cookie")
        llm_row = await self._load_settings_entry("llm")
        whisper_row = await self._load_settings_entry("whisper")

        cookie_text = (cookie_row or {}).get("text") if cookie_row else None
        llm_model = (llm_row or {}).get("model", "qwen2.5:72b")
        whisper_model = (whisper_row or {}).get("model", "large-v3")

        return (
            YtDlpExtractor(cookie_text=cookie_text),
            MlxWhisperTranscriber(model=whisper_model),
            OllamaLLM(model=llm_model),
        )

    # ───── lifecycle ─────

    async def reconcile(self) -> int:
        """Called on startup. Mark orphan running/queued tasks as failed."""
        async with session_scope() as s:
            res = await s.execute(
                update(Task)
                .where(Task.status.in_(["running", "queued"]))
                .values(status="failed", error="进程重启,任务中断", finished_at=_now())
                .returning(Task.id)
            )
            orphaned = [row[0] for row in res.all()]
            return len(orphaned)

    async def enqueue(self, task: Task, creator: Creator | None) -> None:
        """Dispatch a task for background execution. Returns immediately."""
        await broker.publish(TaskEvent("create", _task_to_payload(task, creator)))
        t = asyncio.create_task(self._run(task.id))
        self._inflight[task.id] = t
        t.add_done_callback(lambda _t, tid=task.id: self._inflight.pop(tid, None))

    async def cancel(self, task_id: UUID) -> bool:
        t = self._inflight.get(task_id)
        if not t:
            return False
        t.cancel()
        return True

    async def set_concurrency(self, value: Any) -> int:
        limit = self._normalize_concurrency(value)
        async with self._gate:
            self._concurrency_limit = limit
            self._gate.notify_all()
        return limit

    # ───── private ─────

    async def _run(self, task_id: UUID) -> None:
        acquired = False
        try:
            await self._acquire_slot()
            acquired = True
            await self._run_pipeline(task_id)
        except asyncio.CancelledError:
            await self._set(task_id, status="canceled", detail="已取消")
            raise
        except Exception as e:
            logger.exception("task %s failed", task_id)
            await self._set(task_id, status="failed", error=str(e))
        finally:
            if acquired:
                await self._release_slot()

    async def _run_pipeline(self, task_id: UUID) -> None:
        extractor, transcriber, llm = await self._backends()
        whisper_row = await self._load_settings_entry("whisper")
        llm_row = await self._load_settings_entry("llm")
        whisper_model = (whisper_row or {}).get("model", "large-v3")
        whisper_language = (whisper_row or {}).get("language", "zh")
        llm_model = (llm_row or {}).get("model", "qwen2.5:72b")

        # Stage 1: download / extract
        await self._set(task_id, status="running", stage="download", progress=5, detail="yt-dlp 读取元数据")
        async with session_scope() as s:
            task = await s.get(Task, task_id)
            if not task:
                return
            url = task.source_url
        meta = await extractor.extract(url)
        await self._set(task_id, progress=30, detail="下载完成")

        # Upsert creator & video
        async with session_scope() as s:
            creator = await self._upsert_creator(s, meta)
            video = await self._upsert_video(s, meta, creator.id)
            task = await s.get(Task, task_id)
            if task:
                task.creator_id = creator.id
                task.video_id = video.id
                task.title_guess = meta.title

        # Stage 2: transcribe
        await self._set(task_id, stage="transcribe", progress=45, detail=f"mlx-whisper {whisper_model}")
        transcript = await transcriber.transcribe(meta.audio_path, language=whisper_language)
        await self._set(task_id, progress=65, detail=f"转写完成 · {len(transcript.segments)} 段")

        # Stage 3: organize
        await self._set(task_id, stage="organize", progress=75, detail=f"Ollama {llm_model}")
        settings_row = await self._load_settings_entry("prompt")
        prompt_template = (settings_row or {}).get("template", "")
        transcript_text = "\n".join(seg[1] for seg in transcript.segments)
        organized = await llm.organize(
            transcript=transcript_text,
            title_hint=meta.title,
            creator_hint=meta.creator_name,
            prompt_template=prompt_template,
        )

        # Stage 4: save
        await self._set(task_id, stage="save", progress=92, detail="写入数据库")
        article_id = await self._save_article(
            meta=meta,
            transcript=transcript,
            organized=organized,
        )
        await self._set(
            task_id,
            status="done",
            stage="save",
            progress=100,
            detail="完成",
            article_id=article_id,
            finished_at=_now(),
        )

    async def _set(self, task_id: UUID, **fields: Any) -> None:
        async with session_scope() as s:
            task = await s.get(Task, task_id)
            if not task:
                return
            for k, v in fields.items():
                setattr(task, k, v)
            task.updated_at = _now()
            await s.flush()
            creator = None
            if task.creator_id:
                creator = await s.get(Creator, task.creator_id)
            payload = _task_to_payload(task, creator)
        # Publish outside the session.
        # `done` and `canceled` → task leaves the running list.
        # `failed`             → stays visible so the user can see the error + retry.
        await broker.publish(TaskEvent("update", payload))
        if fields.get("status") in ("done", "canceled"):
            await broker.publish(TaskEvent("remove", {"id": payload["id"]}))

    async def _acquire_slot(self) -> None:
        await self._sync_concurrency_from_settings()
        async with self._gate:
            while self._running >= self._concurrency_limit:
                await self._gate.wait()
            self._running += 1

    async def _release_slot(self) -> None:
        async with self._gate:
            self._running = max(0, self._running - 1)
            self._gate.notify_all()

    async def _sync_concurrency_from_settings(self) -> int:
        llm_row = await self._load_settings_entry("llm")
        requested = (llm_row or {}).get("concurrency", self._default_concurrency)
        return await self.set_concurrency(requested)

    def _normalize_concurrency(self, value: Any) -> int:
        try:
            limit = int(value)
        except (TypeError, ValueError):
            limit = self._default_concurrency
        return max(1, min(limit, 20))

    async def _upsert_creator(self, s: AsyncSession, meta) -> Creator:
        existing = await s.scalar(
            select(Creator).where(
                Creator.platform == "douyin", Creator.external_id == meta.creator_external_id
            )
        )
        if existing:
            existing.name = meta.creator_name
            existing.handle = meta.creator_handle
            existing.region = meta.creator_region
            existing.verified = meta.creator_verified
            existing.followers = meta.creator_followers
            existing.total_likes = meta.creator_total_likes
            existing.recent_update_at = _now()
            await s.flush()
            return existing
        c = Creator(
            platform="douyin",
            external_id=meta.creator_external_id,
            handle=meta.creator_handle,
            name=meta.creator_name,
            region=meta.creator_region,
            verified=meta.creator_verified,
            followers=meta.creator_followers,
            total_likes=meta.creator_total_likes,
            video_count=0,
            recent_update_at=_now(),
        )
        s.add(c)
        await s.flush()
        return c

    async def _upsert_video(self, s: AsyncSession, meta, creator_id: int) -> Video:
        published_at = _parse_iso(meta.published_at_iso)
        existing = await s.get(Video, meta.video_id)
        if existing:
            # Refresh mutable metrics so rebuild / creator-refresh reflect reality.
            # id / creator_id / source_url are the immutable identity — don't touch.
            existing.title = meta.title
            existing.duration_sec = meta.duration_sec
            existing.likes = meta.likes
            existing.plays = meta.plays
            existing.comments = meta.comments
            existing.shares = meta.shares
            existing.collects = meta.collects
            existing.cover_url = meta.cover_url
            existing.published_at = published_at
            await s.flush()
            return existing
        v = Video(
            id=meta.video_id,
            creator_id=creator_id,
            title=meta.title,
            duration_sec=meta.duration_sec,
            likes=meta.likes,
            plays=meta.plays,
            comments=meta.comments,
            shares=meta.shares,
            collects=meta.collects,
            published_at=published_at,
            cover_url=meta.cover_url,
            source_url=meta.source_url,
        )
        s.add(v)
        await s.flush()
        return v

    async def _save_article(self, *, meta, transcript, organized) -> UUID:
        async with session_scope() as s:
            creator = await s.scalar(
                select(Creator).where(
                    Creator.platform == "douyin", Creator.external_id == meta.creator_external_id
                )
            )
            if creator is None:
                raise RuntimeError(
                    f"creator {meta.creator_external_id!r} missing at save — upsert didn't run?"
                )

            article = await s.scalar(select(Article).where(Article.video_id == meta.video_id))
            if article is None:
                article = Article(video_id=meta.video_id, creator_id=creator.id)
                s.add(article)
            else:
                await s.execute(
                    delete(TranscriptSegment).where(TranscriptSegment.article_id == article.id)
                )

            article.creator_id = creator.id
            article.title = organized["title"]
            article.summary = organized["summary"]
            article.content_md = organized["content_md"]
            article.content_html = organized["content_html"]
            article.word_count = organized["word_count"]
            article.tags = organized["tags"]
            article.likes_snapshot = meta.likes
            article.published_at = _parse_iso(meta.published_at_iso)
            await s.flush()

            for i, (ts, text) in enumerate(transcript.segments):
                s.add(TranscriptSegment(article_id=article.id, idx=i, ts_sec=ts, text=text))
            return article.id

    async def _load_settings_entry(self, key: str) -> dict | None:
        async with session_scope() as s:
            row = await s.get(SettingEntry, key)
            return row.value if row else None


runner = TaskRunner()
