from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import Text, cast, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from voxpress.db import get_session, session_scope
from voxpress.errors import InvalidUrl, TaskNotFound
from voxpress.models import Article, Creator, Task, TaskStageRun, Transcript, Video
from voxpress.schemas import (
    Page,
    TaskBatchIn,
    TaskCancelBatchIn,
    TaskCancelBatchOut,
    TaskCreateIn,
    TaskDetailOut,
    TaskOut,
    TaskRerunIn,
    TaskRerunOut,
    TaskSummaryOut,
)
from voxpress.sse import listen_task_events
from voxpress.task_store import (
    ACTIVE_STATUSES,
    build_task_detail_payload,
    build_task_payload,
    build_task_payloads,
    cancel_task as cancel_task_record,
    emit_task_create,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

RERUN_STAGE_PROGRESS = {
    "download": 0,
    "transcribe": 40,
    "correct": 58,
    "organize": 72,
    "save": 92,
}


def _url_kind(url: str) -> str | None:
    url = url.strip()
    if not url:
        return None
    if "v.douyin.com" in url:
        return "short"
    if "douyin.com/video/" in url:
        return "video"
    if "douyin.com/user/" in url:
        return "user"
    return None


def _local_now() -> datetime:
    return datetime.now().astimezone()


def _time_cutoff(value: str | None) -> datetime | None:
    if not value or value == "all":
        return None
    now = _local_now()
    if value == "1h":
        return now - timedelta(hours=1)
    if value == "24h":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if value == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if value == "7d":
        return now - timedelta(days=7)
    if value == "30d":
        return now - timedelta(days=30)
    return None


async def _create_task(
    s: AsyncSession,
    *,
    source_url: str,
    title_guess: str = "",
    creator_id: int | None = None,
    video_id: str | None = None,
    trigger_kind: str = "manual",
    rerun_of_task_id: UUID | None = None,
    resume_from_stage: str | None = None,
    stage: str = "download",
    progress: int = 0,
    detail: str | None = None,
) -> Task:
    task = Task(
        source_url=source_url,
        title_guess=title_guess,
        creator_id=creator_id,
        video_id=video_id,
        trigger_kind=trigger_kind,
        rerun_of_task_id=rerun_of_task_id,
        resume_from_stage=resume_from_stage,
        stage=stage,
        progress=progress,
        detail=detail,
    )
    s.add(task)
    await s.flush()
    return task


def _task_filters(
    *,
    status: str | None,
    stage: str | None,
    time_range: str | None,
    q: str | None,
    model: str | None,
) -> list[Any]:
    clauses: list[Any] = []
    if status == "active":
        clauses.append(Task.status.in_(ACTIVE_STATUSES))
    elif status:
        clauses.append(Task.status == status)
    if stage:
        clauses.append(Task.stage == stage)
    cutoff = _time_cutoff(time_range)
    if cutoff is not None:
        clauses.append(Task.started_at >= cutoff)
    if model:
        clauses.append(
            exists(
                select(TaskStageRun.id).where(
                    TaskStageRun.task_id == Task.id,
                    TaskStageRun.model == model,
                )
            )
        )
    if q:
        like = f"%{q.strip()}%"
        clauses.append(
            or_(
                cast(Task.id, Text).ilike(like),
                Task.title_guess.ilike(like),
                exists(select(Creator.id).where(Creator.id == Task.creator_id, Creator.name.ilike(like))),
                exists(
                    select(Article.id).where(
                        or_(Article.id == Task.article_id, Article.video_id == Task.video_id),
                        Article.title.ilike(like),
                    )
                ),
            )
        )
    return clauses


def _task_sort_order(sort: str) -> list[Any]:
    sort = sort or "started_at:desc"
    field, _, direction = sort.partition(":")
    desc = direction != "asc"
    expr = {
        "started_at": Task.started_at,
        "elapsed_ms": Task.elapsed_ms,
        "total_tokens": Task.total_tokens,
        "cost_cny": Task.cost_cny,
    }.get(field, Task.started_at)
    return [expr.asc().nulls_last()] if not desc else [expr.desc().nulls_last(), Task.started_at.desc()]


async def _resolve_rerun_stage(s: AsyncSession, task: Task, mode: str) -> str | None:
    if task.status in {"queued", "running"}:
        return None
    transcript_exists = False
    organized_ready = False
    if task.video_id:
        transcript_exists = (
            await s.scalar(select(Transcript.video_id).where(Transcript.video_id == task.video_id).limit(1))
        ) is not None
    if task.stage == "save":
        from voxpress.models import TaskArtifact

        organized_ready = (
            await s.scalar(select(TaskArtifact.task_id).where(TaskArtifact.task_id == task.id).limit(1))
        ) is not None

    if mode == "full":
        return "download"
    if mode == "organize":
        return "organize" if transcript_exists else None
    if task.status not in {"failed", "canceled"}:
        return None
    if task.stage == "download":
        return "download"
    if not task.video_id:
        return "download"
    if task.stage == "transcribe":
        return "transcribe"
    if task.stage == "correct":
        return "correct" if transcript_exists else "download"
    if task.stage == "organize":
        return "organize" if transcript_exists else "download"
    if task.stage == "save":
        if organized_ready:
            return "save"
        if transcript_exists:
            return "organize"
        return "download"
    return "download"


@router.get("", response_model=Page[TaskOut])
async def list_tasks(
    s: AsyncSession = Depends(get_session),
    status: str | None = Query(None),
    stage: str | None = Query(None),
    model: str | None = Query(None),
    time_range: str | None = Query(None),
    since: str | None = Query(None),
    q: str | None = Query(None),
    sort: str = Query("started_at:desc"),
    page: int = Query(1, ge=1),
    offset: int | None = Query(None, ge=0),
    limit: int = Query(20, ge=1, le=200),
) -> Page[TaskOut]:
    clauses = _task_filters(
        status=status,
        stage=stage,
        time_range=time_range or since,
        q=q,
        model=model,
    )
    total = await s.scalar(select(func.count()).select_from(Task).where(*clauses))
    resolved_offset = offset if offset is not None else max(0, (page - 1) * limit)
    task_ids = list(
        (
            await s.scalars(
                select(Task.id)
                .where(*clauses)
                .order_by(*_task_sort_order(sort))
                .offset(resolved_offset)
                .limit(limit)
            )
        ).all()
    )
    payloads = await build_task_payloads(task_ids)
    payload_map = {item["id"]: item for item in payloads}
    ordered = [payload_map[str(task_id)] for task_id in task_ids if str(task_id) in payload_map]
    return Page(items=[TaskOut.model_validate(item) for item in ordered], cursor=None, total=total or 0)


@router.get("/summary", response_model=TaskSummaryOut)
async def tasks_summary(
    s: AsyncSession = Depends(get_session),
    status: str | None = Query(None),
    stage: str | None = Query(None),
    model: str | None = Query(None),
    time_range: str | None = Query(None),
    since: str | None = Query(None),
    q: str | None = Query(None),
) -> TaskSummaryOut:
    clauses = _task_filters(
        status=status,
        stage=stage,
        time_range=time_range or since,
        q=q,
        model=model,
    )
    today_cutoff = _local_now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_tasks = int(await s.scalar(select(func.count()).select_from(Task).where(*clauses, Task.started_at >= today_cutoff)) or 0)
    today_success = int(
        await s.scalar(
            select(func.count()).select_from(Task).where(*clauses, Task.started_at >= today_cutoff, Task.status == "done")
        )
        or 0
    )
    today_failed = int(
        await s.scalar(
            select(func.count()).select_from(Task).where(*clauses, Task.started_at >= today_cutoff, Task.status == "failed")
        )
        or 0
    )
    denom = today_success + today_failed
    success_rate = round((today_success / denom) * 100, 1) if denom else 0.0
    total_cost = round(
        float(
            await s.scalar(
                select(func.coalesce(func.sum(Task.cost_cny), 0)).where(*clauses, Task.started_at >= today_cutoff)
            )
            or 0.0
        ),
        4,
    )
    total_tokens = int(
        await s.scalar(
            select(func.coalesce(func.sum(Task.total_tokens), 0)).where(*clauses, Task.started_at >= today_cutoff)
        )
        or 0
    )
    avg_elapsed = int(
        await s.scalar(
            select(func.coalesce(func.avg(Task.elapsed_ms), 0)).where(
                *clauses,
                Task.started_at >= today_cutoff,
                Task.elapsed_ms.is_not(None),
            )
        )
        or 0
    )
    status_rows = (
        await s.execute(select(Task.status, func.count()).where(*clauses).group_by(Task.status))
    ).all()
    status_counts = {"running": 0, "queued": 0, "done": 0, "failed": 0, "canceled": 0}
    for task_status, count in status_rows:
        if task_status in status_counts:
            status_counts[task_status] = int(count)
    status_counts["active"] = status_counts["running"] + status_counts["queued"]
    task_ids_subquery = select(Task.id).where(*clauses).subquery()
    model_rows = (
        await s.execute(
            select(TaskStageRun.model, func.count(func.distinct(TaskStageRun.task_id)))
            .where(
                TaskStageRun.model.is_not(None),
                TaskStageRun.task_id.in_(select(task_ids_subquery.c.id)),
            )
            .group_by(TaskStageRun.model)
        )
    ).all()
    return TaskSummaryOut(
        today_tasks=today_tasks,
        today_success_rate=success_rate,
        today_cost_cny=total_cost,
        today_total_tokens=total_tokens,
        avg_elapsed_ms=avg_elapsed,
        status_counts=status_counts,
        model_facets=[
            {"value": str(model_name), "count": int(count)}
            for model_name, count in sorted(model_rows, key=lambda row: (-int(row[1]), str(row[0])))
            if model_name
        ],
    )


@router.post("", response_model=TaskOut)
async def create_task(
    payload: TaskCreateIn, s: AsyncSession = Depends(get_session)
) -> TaskOut:
    kind = _url_kind(payload.url)
    if kind is None:
        raise InvalidUrl("链接无法识别或非抖音域名")
    if kind == "user":
        raise InvalidUrl("博主主页请用 /creators/resolve 然后 /tasks/batch")
    task = await _create_task(s, source_url=payload.url, trigger_kind="manual")
    await s.commit()
    await s.refresh(task)
    await emit_task_create(task.id)
    payload = await build_task_payload(task.id)
    assert payload is not None
    return TaskOut.model_validate(payload)


@router.post("/batch")
async def create_batch(payload: TaskBatchIn, s: AsyncSession = Depends(get_session)) -> dict:
    video_ids = payload.video_ids or []
    if not video_ids:
        raise InvalidUrl("video_ids 不能为空")

    stmt = select(Video).where(Video.id.in_(video_ids))
    if payload.creator_id is not None:
        stmt = stmt.where(Video.creator_id == payload.creator_id)
    rows = (await s.scalars(stmt)).all()
    found = {v.id: v for v in rows}

    created: list[Task] = []
    for vid in video_ids:
        v = found.get(vid)
        if not v:
            continue
        task = await _create_task(
            s,
            source_url=v.source_url,
            title_guess=v.title,
            creator_id=v.creator_id,
            video_id=v.id,
            trigger_kind="batch",
        )
        created.append(task)
    await s.commit()
    for t in created:
        await emit_task_create(t.id)
    return {"tasks": [TaskOut.model_validate(item).model_dump() for item in await build_task_payloads([t.id for t in created])]}


@router.post("/rerun", response_model=TaskRerunOut)
async def rerun_tasks(payload: TaskRerunIn, s: AsyncSession = Depends(get_session)) -> TaskRerunOut:
    rows = (
        await s.scalars(select(Task).where(Task.id.in_(payload.task_ids)).order_by(Task.started_at.desc()))
    ).all()
    task_map = {task.id: task for task in rows}
    created: list[UUID] = []
    skipped: list[UUID] = []
    for task_id in payload.task_ids:
        task = task_map.get(task_id)
        if task is None:
            skipped.append(task_id)
            continue
        rerun_stage = await _resolve_rerun_stage(s, task, payload.mode)
        if rerun_stage is None:
            skipped.append(task_id)
            continue
        next_task = await _create_task(
            s,
            source_url=task.source_url,
            title_guess=task.title_guess,
            creator_id=task.creator_id,
            video_id=task.video_id,
            trigger_kind="rerun",
            rerun_of_task_id=task.id,
            resume_from_stage=rerun_stage,
            stage=rerun_stage,
            progress=RERUN_STAGE_PROGRESS[rerun_stage],
            detail=(
                "等待重跑 · 从整理开始"
                if payload.mode == "organize"
                else "等待重跑 · 从失败步骤继续"
                if payload.mode == "resume"
                else "等待重跑 · 全链路"
            ),
        )
        created.append(next_task.id)
    await s.commit()
    for task_id in created:
        await emit_task_create(task_id)
    return TaskRerunOut(
        requested=len(payload.task_ids),
        processed=len(created),
        task_ids=created,
        skipped_ids=skipped,
    )


@router.post("/cancel", response_model=TaskCancelBatchOut)
async def cancel_tasks(payload: TaskCancelBatchIn, s: AsyncSession = Depends(get_session)) -> TaskCancelBatchOut:
    rows = (await s.scalars(select(Task).where(Task.id.in_(payload.task_ids)))).all()
    task_map = {task.id: task for task in rows}
    processed = 0
    skipped: list[UUID] = []
    for task_id in payload.task_ids:
        task = task_map.get(task_id)
        if task is None or task.status not in ACTIVE_STATUSES:
            skipped.append(task_id)
            continue
        await cancel_task_record(task_id)
        processed += 1
    return TaskCancelBatchOut(requested=len(payload.task_ids), processed=processed, skipped_ids=skipped)


@router.get("/export")
async def export_tasks(
    s: AsyncSession = Depends(get_session),
    status: str | None = Query(None),
    stage: str | None = Query(None),
    model: str | None = Query(None),
    time_range: str | None = Query(None),
    since: str | None = Query(None),
    q: str | None = Query(None),
    sort: str = Query("started_at:desc"),
) -> Response:
    clauses = _task_filters(
        status=status,
        stage=stage,
        time_range=time_range or since,
        q=q,
        model=model,
    )
    task_ids = list(
        (
            await s.scalars(
                select(Task.id)
                .where(*clauses)
                .order_by(*_task_sort_order(sort))
            )
        ).all()
    )
    payloads = await build_task_payloads(task_ids)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["任务 ID", "状态", "阶段", "文章标题", "博主", "触发方式", "开始", "结束", "耗时(ms)", "tokens", "成本(¥)", "错误信息"])
    for item in payloads:
        writer.writerow(
            [
                item["id"],
                item["status"],
                item["stage"],
                item.get("article_title") or item.get("title_guess") or "",
                item.get("creator_name") or "",
                item.get("trigger_kind") or "",
                item.get("started_at") or "",
                item.get("finished_at") or "",
                item.get("elapsed_ms") or 0,
                item.get("total_tokens") or 0,
                item.get("cost_cny") or 0,
                item.get("error") or "",
            ]
        )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="voxpress-tasks.csv"'},
    )


@router.get("/stream")
async def stream_tasks(request: Request) -> EventSourceResponse:
    async def event_gen():
        async with session_scope() as s:
            rows = (
                await s.scalars(
                    select(Task).where(Task.status.in_(ACTIVE_STATUSES)).order_by(Task.started_at.asc())
                )
            ).all()
            for task in rows:
                payload = await build_task_payload(task.id)
                if payload is None:
                    continue
                yield {
                    "event": "task.update",
                    "data": json.dumps(payload, default=str, ensure_ascii=False),
                }
        async for ev in listen_task_events():
            if await request.is_disconnected():
                break
            if ev.kind == "remove":
                yield {
                    "event": "task.remove",
                    "data": json.dumps({"id": ev.task_id}, ensure_ascii=False),
                }
                continue
            payload = await build_task_payload(ev.task_id)
            if payload is None:
                continue
            yield {
                "event": f"task.{ev.kind}",
                "data": json.dumps(payload, default=str, ensure_ascii=False),
            }

    return EventSourceResponse(event_gen(), ping=20)


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: UUID) -> TaskOut:
    payload = await build_task_payload(task_id)
    if payload is None:
        raise TaskNotFound(f"task {task_id} not found")
    return TaskOut.model_validate(payload)


@router.get("/{task_id}/detail", response_model=TaskDetailOut)
async def get_task_detail(task_id: UUID) -> TaskDetailOut:
    payload = await build_task_detail_payload(task_id)
    if payload is None:
        raise TaskNotFound(f"task {task_id} not found")
    return TaskDetailOut.model_validate(payload)


@router.post("/{task_id}/cancel", response_model=TaskOut)
async def cancel_task(task_id: UUID) -> TaskOut:
    t = await cancel_task_record(task_id)
    if not t:
        raise TaskNotFound(f"task {task_id} not found")
    payload = await build_task_payload(task_id)
    if payload is None:
        payload = {
            "id": str(t.id),
            "source_url": t.source_url,
            "title_guess": t.title_guess,
            "creator_id": t.creator_id,
            "creator_name": None,
            "creator_initial": None,
            "stage": t.stage,
            "status": t.status,
            "progress": t.progress,
            "eta_sec": t.eta_sec,
            "detail": t.detail,
            "article_id": str(t.article_id) if t.article_id else None,
            "error": t.error,
            "started_at": t.started_at,
            "updated_at": t.updated_at,
            "finished_at": t.finished_at,
        }
    return TaskOut.model_validate(payload)


# Export router alias for main.py
_ = Annotated  # keep import
