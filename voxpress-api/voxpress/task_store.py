from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select

from voxpress.config import settings
from voxpress.db import session_scope
from voxpress.models import Article, Creator, Task, TaskArtifact, TaskStageRun, Transcript, Video
from voxpress.schemas import first_grapheme
from voxpress.sse import publish_task_event
from voxpress.task_metrics import merge_usage

ACTIVE_STATUSES = ("queued", "running")
STAGE_SEQUENCE = ("download", "transcribe", "correct", "organize", "save")
PRIMARY_MODEL_STAGE_PRIORITY = ("organize", "correct", "transcribe")
_ETA_UNSET = object()


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _elapsed_ms(task: Task) -> int | None:
    if task.elapsed_ms is not None:
        return int(task.elapsed_ms)
    if task.finished_at and task.started_at:
        return max(0, int((task.finished_at - task.started_at).total_seconds() * 1000))
    return None


@dataclass(slots=True)
class ClaimedTask:
    id: UUID
    stage: str
    lease_owner: str


@dataclass(slots=True)
class ArtifactSnapshot:
    transcript_segments: list[tuple[int, str]]
    organized: dict[str, Any] | None


async def _load_video(s, task: Task) -> Video | None:
    if task.video_id:
        video = await s.get(Video, task.video_id)
        if video is not None:
            return video
    return await s.scalar(
        select(Video).where(Video.source_url == task.source_url).order_by(Video.updated_at.desc()).limit(1)
    )


async def _load_article(s, task: Task, video: Video | None) -> Article | None:
    if task.article_id:
        article = await s.get(Article, task.article_id)
        if article is not None:
            return article
    if video is None:
        return None
    return await s.scalar(select(Article).where(Article.video_id == video.id).limit(1))


def _serialize_stage_run(run: TaskStageRun) -> dict[str, Any]:
    return {
        "stage": run.stage,
        "status": run.status,
        "provider": run.provider,
        "model": run.model,
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "duration_ms": run.duration_ms,
        "input_tokens": int(run.input_tokens or 0),
        "output_tokens": int(run.output_tokens or 0),
        "total_tokens": int(run.total_tokens or 0),
        "cost_cny": float(run.cost_cny or 0.0),
        "detail": run.detail,
        "error": run.error,
    }


def _pick_primary_model(runs: list[TaskStageRun]) -> str | None:
    run_map = {run.stage: run.model for run in runs if run.model}
    for stage in PRIMARY_MODEL_STAGE_PRIORITY:
        if run_map.get(stage):
            return run_map[stage]
    for run in runs:
        if run.model:
            return run.model
    return None


async def _build_task_payload_from_session(
    s,
    task: Task,
    *,
    include_stage_runs: bool = False,
) -> dict[str, Any]:
    creator = await s.get(Creator, task.creator_id) if task.creator_id else None
    video = await _load_video(s, task)
    article = await _load_article(s, task, video)
    runs = (
        list(
            (
                await s.scalars(
                    select(TaskStageRun)
                    .where(TaskStageRun.task_id == task.id)
                    .order_by(TaskStageRun.started_at.asc().nulls_last(), TaskStageRun.stage.asc())
                )
            ).all()
        )
        if include_stage_runs
        else list(
            (
                await s.scalars(
                    select(TaskStageRun)
                    .where(TaskStageRun.task_id == task.id)
                    .order_by(TaskStageRun.started_at.asc().nulls_last(), TaskStageRun.stage.asc())
                )
            ).all()
        )
    )
    payload = {
        "id": str(task.id),
        "source_url": task.source_url,
        "title_guess": task.title_guess,
        "creator_id": task.creator_id,
        "creator_name": creator.name if creator else None,
        "creator_initial": first_grapheme(creator.name) if creator else None,
        "stage": task.stage,
        "status": task.status,
        "progress": task.progress,
        "eta_sec": task.eta_sec,
        "detail": task.detail,
        "article_id": str(task.article_id) if task.article_id else (str(article.id) if article else None),
        "article_title": article.title if article else None,
        "cover_url": (video.cover_url if video else None),
        "error": task.error,
        "trigger_kind": task.trigger_kind,
        "rerun_of_task_id": str(task.rerun_of_task_id) if task.rerun_of_task_id else None,
        "resume_from_stage": task.resume_from_stage,
        "primary_model": _pick_primary_model(runs),
        "models": [run.model for run in runs if run.model],
        "elapsed_ms": _elapsed_ms(task),
        "input_tokens": int(task.input_tokens or 0),
        "output_tokens": int(task.output_tokens or 0),
        "total_tokens": int(task.total_tokens or 0),
        "cost_cny": float(task.cost_cny or 0.0),
        "started_at": _iso(task.started_at),
        "updated_at": _iso(task.updated_at),
        "finished_at": _iso(task.finished_at),
    }
    if include_stage_runs:
        payload["stage_runs"] = [_serialize_stage_run(run) for run in runs]
    return payload


async def _build_task_payloads_from_session(
    s,
    tasks: list[Task],
    *,
    include_stage_runs: bool = False,
) -> list[dict[str, Any]]:
    if not tasks:
        return []

    task_ids = [task.id for task in tasks]
    creator_ids = {task.creator_id for task in tasks if task.creator_id is not None}
    explicit_video_ids = {task.video_id for task in tasks if task.video_id}
    fallback_source_urls = {task.source_url for task in tasks if not task.video_id}
    explicit_article_ids = {task.article_id for task in tasks if task.article_id is not None}

    creators = {
        creator.id: creator
        for creator in (
            (await s.scalars(select(Creator).where(Creator.id.in_(creator_ids)))).all() if creator_ids else []
        )
    }

    videos_by_id = {
        video.id: video
        for video in (
            (await s.scalars(select(Video).where(Video.id.in_(explicit_video_ids)))).all() if explicit_video_ids else []
        )
    }
    videos_by_source: dict[str, Video] = {}
    if fallback_source_urls:
        rows = (
            await s.scalars(
                select(Video)
                .where(Video.source_url.in_(fallback_source_urls))
                .order_by(Video.updated_at.desc())
            )
        ).all()
        for video in rows:
            videos_by_source.setdefault(video.source_url, video)

    resolved_videos = []
    for task in tasks:
        video = videos_by_id.get(task.video_id) if task.video_id else None
        if video is None:
            video = videos_by_source.get(task.source_url)
        if video is not None:
            resolved_videos.append(video)
    resolved_video_ids = {video.id for video in resolved_videos}

    articles_by_id = {
        article.id: article
        for article in (
            (await s.scalars(select(Article).where(Article.id.in_(explicit_article_ids)))).all()
            if explicit_article_ids
            else []
        )
    }
    articles_by_video = {
        article.video_id: article
        for article in (
            (await s.scalars(select(Article).where(Article.video_id.in_(resolved_video_ids)))).all()
            if resolved_video_ids
            else []
        )
    }

    runs_by_task: dict[UUID, list[TaskStageRun]] = defaultdict(list)
    runs = (
        await s.scalars(
            select(TaskStageRun)
            .where(TaskStageRun.task_id.in_(task_ids))
            .order_by(TaskStageRun.started_at.asc().nulls_last(), TaskStageRun.stage.asc())
        )
    ).all()
    for run in runs:
        runs_by_task[run.task_id].append(run)

    payloads: list[dict[str, Any]] = []
    for task in tasks:
        creator = creators.get(task.creator_id) if task.creator_id is not None else None
        video = videos_by_id.get(task.video_id) if task.video_id else None
        if video is None:
            video = videos_by_source.get(task.source_url)
        article = articles_by_id.get(task.article_id) if task.article_id is not None else None
        if article is None and video is not None:
            article = articles_by_video.get(video.id)
        task_runs = runs_by_task.get(task.id, [])
        payload = {
            "id": str(task.id),
            "source_url": task.source_url,
            "title_guess": task.title_guess,
            "creator_id": task.creator_id,
            "creator_name": creator.name if creator else None,
            "creator_initial": first_grapheme(creator.name) if creator else None,
            "stage": task.stage,
            "status": task.status,
            "progress": task.progress,
            "eta_sec": task.eta_sec,
            "detail": task.detail,
            "article_id": str(task.article_id) if task.article_id else (str(article.id) if article else None),
            "article_title": article.title if article else None,
            "cover_url": video.cover_url if video else None,
            "error": task.error,
            "trigger_kind": task.trigger_kind,
            "rerun_of_task_id": str(task.rerun_of_task_id) if task.rerun_of_task_id else None,
            "resume_from_stage": task.resume_from_stage,
            "primary_model": _pick_primary_model(task_runs),
            "models": [run.model for run in task_runs if run.model],
            "elapsed_ms": _elapsed_ms(task),
            "input_tokens": int(task.input_tokens or 0),
            "output_tokens": int(task.output_tokens or 0),
            "total_tokens": int(task.total_tokens or 0),
            "cost_cny": float(task.cost_cny or 0.0),
            "started_at": _iso(task.started_at),
            "updated_at": _iso(task.updated_at),
            "finished_at": _iso(task.finished_at),
        }
        if include_stage_runs:
            payload["stage_runs"] = [_serialize_stage_run(run) for run in task_runs]
        payloads.append(payload)
    return payloads


async def build_task_payload(task_id: UUID | str) -> dict[str, Any] | None:
    async with session_scope() as s:
        task = await s.get(Task, task_id)
        if task is None:
            return None
        payloads = await _build_task_payloads_from_session(s, [task])
        return payloads[0] if payloads else None


async def build_task_payloads(task_ids: list[UUID | str]) -> list[dict[str, Any]]:
    async with session_scope() as s:
        tasks = list((await s.scalars(select(Task).where(Task.id.in_(task_ids)))).all())
        task_map = {task.id: task for task in tasks}
        ordered = [task_map[task_id] for task_id in task_ids if task_id in task_map]
        return await _build_task_payloads_from_session(s, ordered)


async def build_task_detail_payload(task_id: UUID | str) -> dict[str, Any] | None:
    async with session_scope() as s:
        task = await s.get(Task, task_id)
        if task is None:
            return None
        payloads = await _build_task_payloads_from_session(s, [task], include_stage_runs=True)
        if not payloads:
            return None
        payload = payloads[0]
        payload["available_rerun_modes"] = await available_rerun_modes(task.id, session=s)
        return payload


async def emit_task_update(task_id: UUID | str) -> None:
    await publish_task_event("update", task_id)


async def emit_task_create(task_id: UUID | str) -> None:
    await publish_task_event("create", task_id)


async def emit_task_remove(task_id: UUID | str) -> None:
    await publish_task_event("remove", task_id)


async def claim_next_task(stage: str, *, worker_name: str) -> ClaimedTask | None:
    now = _now()
    lease_owner = f"{worker_name}:{uuid4()}"
    lease_until = now + timedelta(seconds=settings.task_lease_seconds)
    async with session_scope() as s:
        task = await s.scalar(
            select(Task)
            .where(Task.stage == stage)
            .where(
                or_(
                    and_(
                        Task.status == "queued",
                        or_(Task.run_after.is_(None), Task.run_after <= now),
                    ),
                    and_(
                        Task.status == "running",
                        or_(
                            Task.lease_expires_at.is_(None),
                            Task.lease_expires_at <= now,
                        ),
                    ),
                )
            )
            .order_by(Task.started_at.asc(), Task.updated_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if task is None:
            return None
        task.status = "running"
        task.lease_owner = lease_owner
        task.lease_expires_at = lease_until
        task.last_heartbeat_at = now
        task.attempt_count += 1
        task.updated_at = now
        task.error = None
        claimed = ClaimedTask(id=task.id, stage=task.stage, lease_owner=lease_owner)
    await emit_task_update(claimed.id)
    return claimed


async def heartbeat(task_id: UUID, *, lease_owner: str) -> bool:
    now = _now()
    lease_until = now + timedelta(seconds=settings.task_lease_seconds)
    async with session_scope() as s:
        task = await s.get(Task, task_id)
        if task is None or task.status != "running" or task.lease_owner != lease_owner:
            return False
        task.last_heartbeat_at = now
        task.lease_expires_at = lease_until
        task.updated_at = now
    return True


async def _rollup_task_metrics(s, task: Task) -> None:
    runs = list(
        (
            await s.scalars(
                select(TaskStageRun)
                .where(TaskStageRun.task_id == task.id)
                .order_by(TaskStageRun.started_at.asc().nulls_last())
            )
        ).all()
    )
    usage = merge_usage(
        *[
            {
                "input_tokens": int(run.input_tokens or 0),
                "output_tokens": int(run.output_tokens or 0),
                "total_tokens": int(run.total_tokens or 0),
                "cost_cny": float(run.cost_cny or 0.0),
            }
            for run in runs
        ]
    )
    task.input_tokens = int(usage["input_tokens"])
    task.output_tokens = int(usage["output_tokens"])
    task.total_tokens = int(usage["total_tokens"])
    task.cost_cny = float(usage["cost_cny"])
    task.elapsed_ms = _elapsed_ms(task)


async def start_stage_run(
    task_id: UUID,
    *,
    lease_owner: str,
    stage: str,
    provider: str | None = None,
    model: str | None = None,
    detail: str | None = None,
) -> bool:
    now = _now()
    async with session_scope() as s:
        task = await s.get(Task, task_id)
        if task is None or task.status != "running" or task.lease_owner != lease_owner:
            return False
        run = await s.scalar(
            select(TaskStageRun).where(TaskStageRun.task_id == task_id, TaskStageRun.stage == stage).limit(1)
        )
        if run is None:
            run = TaskStageRun(task_id=task_id, stage=stage)
            s.add(run)
        run.status = "running"
        run.provider = provider
        run.model = model
        run.started_at = now
        run.finished_at = None
        run.duration_ms = None
        run.input_tokens = 0
        run.output_tokens = 0
        run.total_tokens = 0
        run.cost_cny = 0
        run.detail = detail
        run.error = None
        run.updated_at = now
    await emit_task_update(task_id)
    return True


async def finish_stage_run(
    task_id: UUID,
    *,
    lease_owner: str,
    stage: str,
    status: str,
    detail: str | None = None,
    error: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    cost_cny: float = 0.0,
) -> bool:
    now = _now()
    async with session_scope() as s:
        task = await s.get(Task, task_id)
        if task is None or task.lease_owner not in (lease_owner, None):
            return False
        run = await s.scalar(
            select(TaskStageRun).where(TaskStageRun.task_id == task_id, TaskStageRun.stage == stage).limit(1)
        )
        if run is None:
            run = TaskStageRun(task_id=task_id, stage=stage)
            s.add(run)
        run.status = status
        run.provider = provider or run.provider
        run.model = model or run.model
        if run.started_at is None:
            run.started_at = task.started_at or now
        run.finished_at = now
        run.duration_ms = max(0, int((now - run.started_at).total_seconds() * 1000))
        run.input_tokens = max(0, int(input_tokens))
        run.output_tokens = max(0, int(output_tokens))
        run.total_tokens = max(0, int(total_tokens))
        run.cost_cny = max(0.0, float(cost_cny))
        run.detail = detail or run.detail
        run.error = error
        run.updated_at = now
        await _rollup_task_metrics(s, task)
    await emit_task_update(task_id)
    return True


async def update_task_progress(
    task_id: UUID,
    *,
    lease_owner: str,
    progress: int | None = None,
    detail: str | None = None,
    eta_sec: int | None | object = _ETA_UNSET,
) -> bool:
    async with session_scope() as s:
        task = await s.get(Task, task_id)
        if task is None or task.status != "running" or task.lease_owner != lease_owner:
            return False
        if progress is not None:
            task.progress = progress
        if detail is not None:
            task.detail = detail
        if eta_sec is not _ETA_UNSET:
            task.eta_sec = eta_sec
        task.updated_at = _now()
        run = await s.scalar(
            select(TaskStageRun).where(TaskStageRun.task_id == task_id, TaskStageRun.stage == task.stage).limit(1)
        )
        if run is not None and detail is not None:
            run.detail = detail
            run.updated_at = task.updated_at
    await emit_task_update(task_id)
    return True


async def queue_next_stage(
    task_id: UUID,
    *,
    lease_owner: str,
    next_stage: str,
    progress: int,
    detail: str,
) -> bool:
    async with session_scope() as s:
        task = await s.get(Task, task_id)
        if task is None or task.status != "running" or task.lease_owner != lease_owner:
            return False
        task.stage = next_stage
        task.status = "queued"
        task.progress = progress
        task.detail = detail
        task.error = None
        task.run_after = _now()
        task.lease_owner = None
        task.lease_expires_at = None
        task.last_heartbeat_at = None
        task.updated_at = _now()
        await _rollup_task_metrics(s, task)
    await emit_task_update(task_id)
    return True


async def _finalize_current_stage_run(s, task: Task, *, status: str, detail: str | None, error: str | None) -> None:
    run = await s.scalar(
        select(TaskStageRun).where(TaskStageRun.task_id == task.id, TaskStageRun.stage == task.stage).limit(1)
    )
    if run is None:
        run = TaskStageRun(task_id=task.id, stage=task.stage)
        s.add(run)
    elif run.finished_at is not None and run.status in {"done", "failed", "canceled", "skipped"}:
        return
    if run.started_at is None:
        run.started_at = task.started_at or _now()
    run.status = status
    run.finished_at = _now()
    run.duration_ms = max(0, int((run.finished_at - run.started_at).total_seconds() * 1000))
    run.detail = detail or run.detail
    run.error = error
    run.updated_at = _now()


async def mark_task_done(
    task_id: UUID,
    *,
    lease_owner: str,
    article_id: UUID,
) -> bool:
    async with session_scope() as s:
        task = await s.get(Task, task_id)
        if task is None or task.status != "running" or task.lease_owner != lease_owner:
            return False
        task.status = "done"
        task.stage = "save"
        task.progress = 100
        task.detail = "完成"
        task.article_id = article_id
        task.finished_at = _now()
        task.lease_owner = None
        task.lease_expires_at = None
        task.last_heartbeat_at = None
        task.updated_at = _now()
        await _finalize_current_stage_run(s, task, status="done", detail="完成", error=None)
        await _rollup_task_metrics(s, task)
    await emit_task_update(task_id)
    await emit_task_remove(task_id)
    return True


async def mark_task_failed(task_id: UUID, *, lease_owner: str, error: str) -> bool:
    async with session_scope() as s:
        task = await s.get(Task, task_id)
        if task is None:
            return False
        if task.status == "canceled":
            return False
        if task.lease_owner not in (lease_owner, None):
            return False
        task.status = "failed"
        task.error = error
        task.finished_at = _now()
        task.lease_owner = None
        task.lease_expires_at = None
        task.last_heartbeat_at = None
        task.updated_at = _now()
        await _finalize_current_stage_run(s, task, status="failed", detail=task.detail, error=error)
        await _rollup_task_metrics(s, task)
    await emit_task_update(task_id)
    return True


async def cancel_task(task_id: UUID) -> Task | None:
    async with session_scope() as s:
        task = await s.get(Task, task_id)
        if task is None:
            return None
        if task.status not in ACTIVE_STATUSES:
            return task
        task.status = "canceled"
        task.detail = "已取消"
        task.finished_at = _now()
        task.lease_owner = None
        task.lease_expires_at = None
        task.last_heartbeat_at = None
        task.updated_at = _now()
        await _finalize_current_stage_run(s, task, status="canceled", detail="已取消", error=None)
        await _rollup_task_metrics(s, task)
    await emit_task_update(task_id)
    await emit_task_remove(task_id)
    return task


async def load_active_task_ids() -> list[UUID]:
    async with session_scope() as s:
        return list(
            (
                await s.scalars(
                    select(Task.id)
                    .where(Task.status.in_(ACTIVE_STATUSES))
                    .order_by(Task.started_at.asc(), Task.updated_at.asc())
                )
            ).all()
        )


async def save_transcript_artifact(task_id: UUID, segments: list[tuple[int, str]]) -> None:
    payload = [[ts, text] for ts, text in segments]
    async with session_scope() as s:
        artifact = await s.get(TaskArtifact, task_id)
        if artifact is None:
            artifact = TaskArtifact(task_id=task_id)
            s.add(artifact)
        artifact.transcript_segments = payload
        artifact.updated_at = _now()


async def save_organized_artifact(task_id: UUID, organized: dict[str, Any]) -> None:
    async with session_scope() as s:
        artifact = await s.get(TaskArtifact, task_id)
        if artifact is None:
            artifact = TaskArtifact(task_id=task_id)
            s.add(artifact)
        artifact.organized = organized
        artifact.updated_at = _now()


async def load_artifact(task_id: UUID) -> ArtifactSnapshot:
    async with session_scope() as s:
        artifact = await s.get(TaskArtifact, task_id)
        segments_raw = list(artifact.transcript_segments or []) if artifact else []
        organized = dict(artifact.organized or {}) if artifact and artifact.organized else None
    segments: list[tuple[int, str]] = []
    for row in segments_raw:
        if isinstance(row, (list, tuple)) and len(row) == 2:
            segments.append((int(row[0]), str(row[1])))
    return ArtifactSnapshot(transcript_segments=segments, organized=organized)


async def clear_artifact(task_id: UUID) -> None:
    async with session_scope() as s:
        artifact = await s.get(TaskArtifact, task_id)
        if artifact is not None:
            await s.delete(artifact)


async def available_rerun_modes(task_id: UUID | str, *, session=None) -> dict[str, bool]:
    async def _compute(s) -> dict[str, bool]:
        task = await s.get(Task, task_id)
        if task is None:
            return {"resume": False, "organize": False, "full": False}
        transcript_exists = False
        if task.video_id:
            transcript_exists = (
                await s.scalar(select(TaskArtifact.task_id).where(TaskArtifact.task_id == task.id).limit(1))
            ) is not None or (
                await s.scalar(select(Transcript.video_id).where(Transcript.video_id == task.video_id).limit(1))
            ) is not None
        can_resume = task.status in {"failed", "canceled"}
        can_organize = bool(task.status in {"done", "failed", "canceled"} and task.video_id and transcript_exists)
        can_full = task.status in {"done", "failed", "canceled"}
        return {"resume": can_resume, "organize": can_organize, "full": can_full}

    if session is not None:
        return await _compute(session)
    async with session_scope() as s:
        return await _compute(s)
