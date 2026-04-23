from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from voxpress.config import settings as app_settings
from voxpress.db import session_scope
from voxpress.markdown import md_to_html, strip_background_notes_md, word_count_cn
from voxpress.media_store import MediaStoreError, audio_object_key, media_store, video_object_key
from voxpress.models import Article, Creator, SettingEntry, Task, Transcript, TranscriptSegment, Video
from voxpress.pipeline.dashscope import DashScopeCorrector
from voxpress.pipeline.protocols import Extractor, ExtractorResult, LLMBackend, Transcriber, TranscriptResult
from voxpress.pipeline.stub import StubExtractor, StubLLM, StubTranscriber

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _normalize_runtime_settings(key: str, value: dict | None) -> dict:
    raw = dict(value or {})
    if key == "llm":
        model = str(raw.get("model") or "").strip()
        raw["backend"] = "dashscope"
        if not model or ":" in model or model not in app_settings.dashscope_llm_models_list:
            raw["model"] = app_settings.dashscope_default_llm_model
        return raw
    if key == "whisper":
        model = str(raw.get("model") or "").strip()
        if model not in app_settings.dashscope_asr_models_list:
            raw["model"] = app_settings.dashscope_default_asr_model
        language = str(raw.get("language") or "zh")
        raw["language"] = language if language in {"zh", "auto"} else "zh"
        raw["enable_initial_prompt"] = bool(raw.get("enable_initial_prompt", True))
        return raw
    if key == "corrector":
        model = str(raw.get("model") or "").strip()
        if not model or ":" in model or model not in app_settings.dashscope_corrector_models_list:
            raw["model"] = app_settings.dashscope_default_corrector_model
        return raw
    return raw


@dataclass(slots=True)
class VideoContext:
    task: Task
    video: Video
    creator: Creator


@dataclass(slots=True)
class TranscriptContext:
    video_id: str
    raw_text: str
    corrected_text: str | None
    segments: list[tuple[int, str]]
    corrections: list[dict[str, str]]
    correction_status: str
    initial_prompt_used: str | None


class TaskRunner:
    async def _extractor_backend(self) -> Extractor:
        if app_settings.pipeline == "stub":
            return StubExtractor()
        from voxpress.pipeline.douyin_video import DouyinWebExtractor

        cookie_row = await self._load_settings_entry("cookie")
        cookie_text = (cookie_row or {}).get("text") if cookie_row else None
        return DouyinWebExtractor(cookie_text=cookie_text)

    async def _transcriber_backend(self) -> Transcriber:
        if app_settings.pipeline == "stub":
            return StubTranscriber()
        from voxpress.pipeline.dashscope import DashScopeFileTranscriber

        whisper_row = await self._load_settings_entry("whisper")
        whisper_model = (whisper_row or {}).get("model", app_settings.dashscope_default_asr_model)
        return DashScopeFileTranscriber(model=whisper_model)

    async def _llm_backend(self) -> LLMBackend:
        if app_settings.pipeline == "stub":
            return StubLLM()
        from voxpress.pipeline.dashscope import DashScopeLLM

        llm_row = await self._load_settings_entry("llm")
        llm_model = (llm_row or {}).get("model", app_settings.dashscope_default_llm_model)
        return DashScopeLLM(model=llm_model)

    async def _corrector_backend(self) -> DashScopeCorrector:
        llm_row = await self._load_settings_entry("llm")
        corrector_row = await self._load_settings_entry("corrector")
        model = str(
            (corrector_row or {}).get("model")
            or (llm_row or {}).get("model", app_settings.dashscope_default_corrector_model)
        )
        template = str((corrector_row or {}).get("template") or "")
        return DashScopeCorrector(model=model, template=template)

    async def current_whisper_label(self) -> str:
        whisper_row = await self._load_settings_entry("whisper")
        return f"DashScope {(whisper_row or {}).get('model', app_settings.dashscope_default_asr_model)}"

    async def current_whisper_model(self) -> str:
        whisper_row = await self._load_settings_entry("whisper")
        return str((whisper_row or {}).get("model", app_settings.dashscope_default_asr_model))

    async def current_whisper_language(self) -> str:
        whisper_row = await self._load_settings_entry("whisper")
        return str((whisper_row or {}).get("language", "zh"))

    async def enable_initial_prompt(self) -> bool:
        whisper_row = await self._load_settings_entry("whisper")
        return bool((whisper_row or {}).get("enable_initial_prompt", True))

    async def current_llm_label(self) -> str:
        llm_row = await self._load_settings_entry("llm")
        return f"DashScope {(llm_row or {}).get('model', app_settings.dashscope_default_llm_model)}"

    async def current_llm_model(self) -> str:
        llm_row = await self._load_settings_entry("llm")
        return str((llm_row or {}).get("model", app_settings.dashscope_default_llm_model))

    async def current_corrector_label(self) -> str:
        corrector_row = await self._load_settings_entry("corrector")
        llm_row = await self._load_settings_entry("llm")
        model = (corrector_row or {}).get("model") or (
            llm_row or {}
        ).get("model", app_settings.dashscope_default_corrector_model)
        return f"DashScope {model} · 纠错"

    async def current_corrector_model(self) -> str:
        corrector_row = await self._load_settings_entry("corrector")
        llm_row = await self._load_settings_entry("llm")
        return str(
            (corrector_row or {}).get("model")
            or (llm_row or {}).get("model", app_settings.dashscope_default_corrector_model)
        )

    async def auto_correct_enabled(self) -> bool:
        corrector_row = await self._load_settings_entry("corrector")
        return bool((corrector_row or {}).get("enabled", True))

    async def background_notes_enabled(self) -> bool:
        article_row = await self._load_settings_entry("article")
        return bool((article_row or {}).get("generate_background_notes", True))

    async def download_stage(self, task_id: UUID) -> ExtractorResult:
        extractor = await self._extractor_backend()
        async with session_scope() as s:
            task = await s.get(Task, task_id)
            if task is None:
                raise RuntimeError(f"task {task_id} missing")
            url = task.source_url

        meta = await self._restore_cached_extract(task_id)
        if meta is None:
            meta = await extractor.extract(url)
            await self._archive_media(meta)

        async with session_scope() as s:
            task = await s.get(Task, task_id)
            if task is None:
                raise RuntimeError(f"task {task_id} missing at save")
            meta = await self._pin_creator_context(s, task, meta)
            creator = await self._upsert_creator(s, meta)
            video = await self._upsert_video(s, meta, creator.id)
            task.creator_id = creator.id
            task.video_id = video.id
            task.title_guess = meta.title
            await s.flush()

        return meta

    async def prepare_audio(self, task_id: UUID) -> Path:
        ctx = await self._load_video_context(task_id)
        local_audio = self._find_local_audio(ctx.video.id)
        if local_audio is not None:
            return local_audio

        app_settings.audio_dir.mkdir(parents=True, exist_ok=True)
        audio_path = app_settings.audio_dir / f"{ctx.video.id}.m4a"
        if ctx.video.audio_object_key and media_store.enabled:
            await media_store.download_file(ctx.video.audio_object_key, path=audio_path)
            return audio_path

        if ctx.video.media_object_key and media_store.enabled:
            app_settings.video_dir.mkdir(parents=True, exist_ok=True)
            video_path = app_settings.video_dir / f"{ctx.video.id}.mp4"
            await media_store.download_file(ctx.video.media_object_key, path=video_path)
            from voxpress.pipeline.douyin_video import _extract_audio

            await _extract_audio(video_path, audio_path)
            return audio_path

        extractor = await self._extractor_backend()
        meta = await extractor.extract(ctx.task.source_url)
        await self._archive_media(meta)
        async with session_scope() as s:
            task = await s.get(Task, task_id)
            if task is not None:
                meta = await self._pin_creator_context(s, task, meta)
                creator = await self._upsert_creator(s, meta)
                video = await self._upsert_video(s, meta, creator.id)
                task.creator_id = creator.id
                task.video_id = video.id
                task.title_guess = meta.title
        return meta.audio_path

    async def transcribe_inline(self, task_id: UUID) -> TranscriptResult:
        audio_path = await self.prepare_audio(task_id)
        ctx = await self._load_video_context(task_id)
        if media_store.enabled and not ctx.video.audio_object_key and audio_path.exists():
            try:
                object_key = await media_store.upload_file(
                    audio_path,
                    object_key=audio_object_key(ctx.video.id, audio_path),
                )
            except MediaStoreError as exc:
                logger.warning("archive audio before transcribe failed for %s: %s", ctx.video.id, exc)
            else:
                if object_key:
                    async with session_scope() as s:
                        video = await s.get(Video, ctx.video.id)
                        if video is not None:
                            video.audio_object_key = object_key
        transcriber = await self._transcriber_backend()
        language = await self.current_whisper_language()
        initial_prompt = await self.build_initial_prompt(task_id)
        return await transcriber.transcribe(
            audio_path,
            language=language,
            initial_prompt=initial_prompt,
        )

    async def build_initial_prompt(self, task_id: UUID) -> str | None:
        if not await self.enable_initial_prompt():
            return None
        ctx = await self._load_video_context(task_id)
        parts = [ctx.video.title.strip(), ctx.creator.name.strip()]
        prompt = "。".join(part for part in parts if part).strip()
        return prompt[:200] or None

    async def save_transcript_stage(
        self,
        task_id: UUID,
        transcript: TranscriptResult,
        *,
        initial_prompt_used: str | None,
        whisper_model: str,
        whisper_language: str,
    ) -> None:
        ctx = await self._load_video_context(task_id)
        payload = [[ts, text] for ts, text in transcript.segments]
        async with session_scope() as s:
            row = await s.get(Transcript, ctx.video.id)
            if row is None:
                row = Transcript(video_id=ctx.video.id, raw_text=transcript.raw_text, segments=payload)
                s.add(row)
            else:
                row.raw_text = transcript.raw_text
                row.segments = payload
            row.initial_prompt_used = initial_prompt_used
            row.whisper_model = whisper_model
            row.whisper_language = whisper_language
            row.corrected_text = None
            row.corrections = None
            row.correction_status = "pending"
            row.corrector_model = None

    async def mark_correct_skipped(self, task_id: UUID) -> None:
        ctx = await self._load_video_context(task_id)
        async with session_scope() as s:
            row = await s.get(Transcript, ctx.video.id)
            if row is None:
                raise RuntimeError(f"transcript for video {ctx.video.id} missing")
            row.corrected_text = row.raw_text
            row.corrections = []
            row.correction_status = "skipped"
            row.corrector_model = None

    async def correct_stage(self, task_id: UUID) -> dict[str, Any]:
        ctx = await self._load_video_context(task_id)
        transcript = await self._load_transcript(ctx.video.id)
        if not transcript.raw_text:
            raise RuntimeError("逐字稿为空，无法纠错")
        corrector = await self._corrector_backend()
        try:
            corrected = await corrector.correct(
                text=transcript.raw_text,
                title_hint=ctx.video.title,
                creator_hint=ctx.creator.name,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("correct stage failed for %s: %s", ctx.video.id, exc)
            corrected = {
                "corrected_text": transcript.raw_text,
                "corrections": [],
                "correction_status": "skipped",
                "corrector_model": corrector.model,
            }
        async with session_scope() as s:
            row = await s.get(Transcript, ctx.video.id)
            if row is None:
                raise RuntimeError(f"transcript for video {ctx.video.id} missing")
            row.corrected_text = str(corrected.get("corrected_text") or transcript.raw_text)
            row.corrections = corrected.get("corrections") or []
            row.correction_status = str(corrected.get("correction_status") or "ok")
            row.corrector_model = str(corrected.get("corrector_model") or "")
        return corrected

    async def organize_stage(self, task_id: UUID) -> dict[str, Any]:
        llm = await self._llm_backend()
        settings_row = await self._load_settings_entry("prompt")
        prompt_template = (settings_row or {}).get("template", "")
        ctx = await self._load_video_context(task_id)
        transcript = await self._load_transcript(ctx.video.id)
        transcript_text = (transcript.corrected_text or transcript.raw_text).strip()
        if not transcript_text:
            raise RuntimeError("逐字稿为空，无法进入整理阶段")
        organized = await llm.organize(
            transcript=transcript_text,
            title_hint=ctx.video.title,
            creator_hint=ctx.creator.name,
            prompt_template=prompt_template,
            duration_sec=ctx.video.duration_sec,
        )
        usage = organized.get("_usage")
        if await self.background_notes_enabled():
            try:
                background_notes = await llm.annotate_background(
                    transcript=transcript_text,
                    title_hint=ctx.video.title,
                    creator_hint=ctx.creator.name,
                    article_title=str(organized.get("title") or ctx.video.title),
                    article_summary=str(organized.get("summary") or ""),
                )
                if isinstance(background_notes, dict) and background_notes.get("_usage") and usage:
                    from voxpress.task_metrics import merge_usage

                    usage = merge_usage(usage, background_notes.get("_usage"))
                elif isinstance(background_notes, dict) and background_notes.get("_usage"):
                    usage = background_notes.get("_usage")
                if isinstance(background_notes, dict):
                    background_notes.pop("_usage", None)
                    background_notes.pop("_primary_model", None)
                organized["background_notes"] = background_notes
            except Exception as exc:  # noqa: BLE001
                logger.warning("background notes generation failed for %s: %s", ctx.video.id, exc)
                organized["background_notes"] = None
        else:
            organized["background_notes"] = None
        if isinstance(organized, dict):
            organized["_usage"] = usage
        return organized

    async def save_stage(
        self,
        task_id: UUID,
        *,
        organized: dict[str, Any],
    ) -> UUID:
        ctx = await self._load_video_context(task_id)
        meta = self._meta_from_video_context(ctx)
        transcript = await self._load_transcript(ctx.video.id)
        return await self._save_article(meta=meta, transcript=transcript, organized=organized)

    async def _archive_media(self, meta: ExtractorResult) -> None:
        if not media_store.enabled:
            return
        if meta.video_path:
            try:
                meta.media_object_key = await media_store.upload_file(
                    meta.video_path,
                    object_key=video_object_key(meta.video_id, meta.video_path),
                )
                if meta.media_object_key and meta.video_path.exists():
                    meta.video_path.unlink()
            except MediaStoreError as e:
                logger.warning("archive video failed for %s: %s", meta.video_id, e)
            except OSError as e:
                logger.warning("cleanup local video failed for %s: %s", meta.video_id, e)
        if meta.audio_path and meta.audio_path.exists() and not meta.audio_object_key:
            try:
                meta.audio_object_key = await media_store.upload_file(
                    meta.audio_path,
                    object_key=audio_object_key(meta.video_id, meta.audio_path),
                )
            except MediaStoreError as e:
                logger.warning("archive audio failed for %s: %s", meta.video_id, e)

    async def _restore_cached_extract(self, task_id: UUID) -> ExtractorResult | None:
        async with session_scope() as s:
            task = await s.get(Task, task_id)
            if task is None:
                return None
            video = await self._find_existing_video(s, task)
            if video is None:
                return None
            creator = await s.get(Creator, video.creator_id)
            if creator is None:
                return None

        local_audio = self._find_local_audio(video.id)
        if local_audio is not None:
            return self._meta_from_cached_video(video=video, creator=creator, audio_path=local_audio)

        if video.audio_object_key and media_store.enabled:
            app_settings.audio_dir.mkdir(parents=True, exist_ok=True)
            audio_suffix = (
                video.audio_object_key.rsplit(".", 1)[-1] if "." in video.audio_object_key else "m4a"
            )
            audio_path = app_settings.audio_dir / f"{video.id}.{audio_suffix}"
            try:
                await media_store.download_file(video.audio_object_key, path=audio_path)
            except MediaStoreError as e:
                logger.warning("restore archived audio failed for %s: %s", video.id, e)
                return None
            return self._meta_from_cached_video(video=video, creator=creator, audio_path=audio_path)

        return None

    async def _find_existing_video(self, s: AsyncSession, task: Task) -> Video | None:
        if task.video_id:
            video = await s.get(Video, task.video_id)
            if video is not None:
                return video
        return await s.scalar(
            select(Video).where(Video.source_url == task.source_url).order_by(Video.updated_at.desc()).limit(1)
        )

    def _find_local_audio(self, video_id: str) -> Path | None:
        app_settings.audio_dir.mkdir(parents=True, exist_ok=True)
        for candidate in sorted(app_settings.audio_dir.glob(f"{video_id}.*")):
            if candidate.is_file():
                return candidate
        return None

    def _meta_from_cached_video(
        self,
        *,
        video: Video,
        creator: Creator,
        audio_path: Path,
    ) -> ExtractorResult:
        return ExtractorResult(
            video_id=video.id,
            creator_external_id=creator.external_id,
            creator_handle=creator.handle,
            creator_name=creator.name,
            creator_region=creator.region,
            creator_verified=creator.verified,
            creator_followers=creator.followers,
            creator_total_likes=creator.total_likes,
            title=video.title,
            duration_sec=video.duration_sec,
            likes=video.likes,
            plays=video.plays,
            comments=video.comments,
            shares=video.shares,
            collects=video.collects,
            published_at_iso=video.published_at.isoformat(),
            cover_url=video.cover_url,
            source_url=video.source_url,
            audio_path=audio_path,
            video_path=None,
            media_object_key=video.media_object_key,
            audio_object_key=video.audio_object_key,
        )

    def _meta_from_video_context(self, ctx: VideoContext) -> ExtractorResult:
        audio_path = self._find_local_audio(ctx.video.id) or (
            app_settings.audio_dir / f"{ctx.video.id}.m4a"
        )
        return self._meta_from_cached_video(video=ctx.video, creator=ctx.creator, audio_path=audio_path)

    async def _load_video_context(self, task_id: UUID) -> VideoContext:
        async with session_scope() as s:
            task = await s.get(Task, task_id)
            if task is None:
                raise RuntimeError(f"task {task_id} missing")
            if not task.video_id or not task.creator_id:
                raise RuntimeError(f"task {task_id} missing resolved video/creator")
            video = await s.get(Video, task.video_id)
            creator = await s.get(Creator, task.creator_id)
            if video is None:
                raise RuntimeError(f"video {task.video_id} missing")
            if creator is None:
                raise RuntimeError(f"creator {task.creator_id} missing")
            return VideoContext(task=task, video=video, creator=creator)

    async def task_duration_sec(self, task_id: UUID) -> int:
        ctx = await self._load_video_context(task_id)
        return int(ctx.video.duration_sec or 0)

    async def _load_transcript(self, video_id: str) -> TranscriptContext:
        async with session_scope() as s:
            row = await s.get(Transcript, video_id)
        if row is None:
            raise RuntimeError(f"transcript for video {video_id} missing")
        segments: list[tuple[int, str]] = []
        for item in list(row.segments or []):
            if isinstance(item, (list, tuple)) and len(item) == 2:
                segments.append((int(item[0]), str(item[1])))
        return TranscriptContext(
            video_id=row.video_id,
            raw_text=row.raw_text,
            corrected_text=row.corrected_text,
            segments=segments,
            corrections=[
                {
                    "from": str(change.get("from") or ""),
                    "to": str(change.get("to") or ""),
                    "reason": str(change.get("reason") or ""),
                }
                for change in list(row.corrections or [])
                if isinstance(change, dict)
            ],
            correction_status=row.correction_status,
            initial_prompt_used=row.initial_prompt_used,
        )

    async def _pin_creator_context(
        self,
        s: AsyncSession,
        task: Task,
        meta: ExtractorResult,
    ) -> ExtractorResult:
        if task.creator_id is None:
            return meta
        creator = await s.get(Creator, task.creator_id)
        if creator is None:
            return meta
        existing_video = await self._find_existing_video(s, task)
        if existing_video is None or existing_video.creator_id != creator.id:
            return meta

        meta.creator_external_id = creator.external_id
        meta.creator_handle = creator.handle
        meta.creator_name = creator.name
        meta.creator_region = creator.region
        meta.creator_verified = creator.verified
        meta.creator_followers = creator.followers
        meta.creator_total_likes = creator.total_likes
        return meta

    async def _upsert_creator(self, s: AsyncSession, meta: ExtractorResult) -> Creator:
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
            existing.followers = max(existing.followers or 0, meta.creator_followers or 0)
            existing.total_likes = max(existing.total_likes or 0, meta.creator_total_likes or 0)
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

    async def _upsert_video(self, s: AsyncSession, meta: ExtractorResult, creator_id: int) -> Video:
        now = _now()
        published_at = _parse_iso(meta.published_at_iso)
        existing = await s.get(Video, meta.video_id)
        if existing:
            existing.creator_id = creator_id
            existing.title = meta.title
            existing.duration_sec = meta.duration_sec
            existing.likes = meta.likes
            existing.plays = meta.plays
            existing.comments = meta.comments
            existing.shares = meta.shares
            existing.collects = meta.collects
            existing.cover_url = meta.cover_url
            existing.published_at = published_at
            existing.source_url = meta.source_url
            existing.updated_at = now
            if meta.media_object_key:
                existing.media_object_key = meta.media_object_key
            if meta.audio_object_key:
                existing.audio_object_key = meta.audio_object_key
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
            media_object_key=meta.media_object_key,
            audio_object_key=meta.audio_object_key,
            source_url=meta.source_url,
            updated_at=now,
        )
        s.add(v)
        await s.flush()
        return v

    async def _save_article(
        self,
        *,
        meta: ExtractorResult,
        transcript: TranscriptContext,
        organized: dict[str, Any],
    ) -> UUID:
        background_notes = organized.get("background_notes")
        final_md = strip_background_notes_md(str(organized["content_md"]))
        final_html = md_to_html(final_md)
        final_word_count = word_count_cn(final_md)
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
            article.content_md = final_md
            article.content_html = final_html
            article.word_count = final_word_count
            article.tags = organized["tags"]
            article.background_notes = background_notes
            article.likes_snapshot = meta.likes
            article.published_at = _parse_iso(meta.published_at_iso)
            await s.flush()

            for i, (ts, text) in enumerate(transcript.segments):
                s.add(TranscriptSegment(article_id=article.id, idx=i, ts_sec=ts, text=text))
            return article.id

    async def _load_settings_entry(self, key: str) -> dict | None:
        async with session_scope() as s:
            row = await s.get(SettingEntry, key)
            return _normalize_runtime_settings(key, row.value if row else None)


runner = TaskRunner()
