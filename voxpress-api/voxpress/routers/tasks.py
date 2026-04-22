from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voxpress.db import get_session, session_scope
from voxpress.errors import InvalidUrl, TaskNotFound
from voxpress.models import Task, Transcript, Video
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


async def _load_payloads(
    s: AsyncSession,
    *,
    status: str | None,
    stage: str | None,
    time_range: str | None,
    q: str | None,
    model: str | None,
) -> list[dict[str, Any]]:
    stmt = select(Task)
    if status == "active":
        stmt = stmt.where(Task.status.in_(ACTIVE_STATUSES))
    elif status:
        stmt = stmt.where(Task.status == status)
    if stage:
        stmt = stmt.where(Task.stage == stage)
    cutoff = _time_cutoff(time_range)
    if cutoff is not None:
        stmt = stmt.where(Task.started_at >= cutoff)
    stmt = stmt.order_by(Task.started_at.desc())
    tasks = list((await s.scalars(stmt)).all())
    payloads = await build_task_payloads([task.id for task in tasks])

    if model:
        payloads = [item for item in payloads if model in set(item.get("models") or [])]

    if q:
        needle = q.strip().casefold()
        payloads = [
            item
            for item in payloads
            if needle in (item.get("id") or "").casefold()
            or needle in (item.get("title_guess") or "").casefold()
            or needle in (item.get("article_title") or "").casefold()
            or needle in (item.get("creator_name") or "").casefold()
        ]

    return payloads


def _sort_payloads(items: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    sort = sort or "started_at:desc"
    field, _, direction = sort.partition(":")
    reverse = direction != "asc"

    key_map = {
        "started_at": lambda item: item.get("started_at") or "",
        "elapsed_ms": lambda item: int(item.get("elapsed_ms") or 0),
        "total_tokens": lambda item: int(item.get("total_tokens") or 0),
        "cost_cny": lambda item: float(item.get("cost_cny") or 0.0),
    }
    key_fn = key_map.get(field, key_map["started_at"])
    return sorted(items, key=key_fn, reverse=reverse)


def _page_slice(items: list[dict[str, Any]], *, page: int, limit: int) -> list[dict[str, Any]]:
    start = max(0, (page - 1) * limit)
    end = start + limit
    return items[start:end]


def _today_stats(items: list[dict[str, Any]]) -> tuple[int, float, float, int, int]:
    start = _local_now().replace(hour=0, minute=0, second=0, microsecond=0)
    today = [
        item
        for item in items
        if item.get("started_at") and datetime.fromisoformat(item["started_at"]) >= start
    ]
    success = sum(1 for item in today if item.get("status") == "done")
    failed = sum(1 for item in today if item.get("status") == "failed")
    denom = success + failed
    success_rate = round((success / denom) * 100, 1) if denom else 0.0
    total_cost = round(sum(float(item.get("cost_cny") or 0.0) for item in today), 4)
    total_tokens = sum(int(item.get("total_tokens") or 0) for item in today)
    elapsed_samples = [int(item.get("elapsed_ms") or 0) for item in today if item.get("elapsed_ms")]
    avg_elapsed = int(sum(elapsed_samples) / len(elapsed_samples)) if elapsed_samples else 0
    return len(today), success_rate, total_cost, total_tokens, avg_elapsed


def _status_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"running": 0, "queued": 0, "done": 0, "failed": 0, "canceled": 0}
    for item in items:
        status = str(item.get("status") or "")
        if status in counts:
            counts[status] += 1
    counts["active"] = counts["running"] + counts["queued"]
    return counts


def _model_facets(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for item in items:
        for model in item.get("models") or []:
            counts[model] = counts.get(model, 0) + 1
    return [
        {"value": model, "count": count}
        for model, count in sorted(counts.items(), key=lambda row: (-row[1], row[0]))
    ]


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
    q: str | None = Query(None),
    sort: str = Query("started_at:desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
) -> Page[TaskOut]:
    payloads = await _load_payloads(
        s,
        status=status,
        stage=stage,
        time_range=time_range,
        q=q,
        model=model,
    )
    total = len(payloads)
    items = _page_slice(_sort_payloads(payloads, sort), page=page, limit=limit)
    return Page(items=[TaskOut.model_validate(item) for item in items], cursor=None, total=total)


@router.get("/summary", response_model=TaskSummaryOut)
async def tasks_summary(
    s: AsyncSession = Depends(get_session),
    status: str | None = Query(None),
    stage: str | None = Query(None),
    model: str | None = Query(None),
    time_range: str | None = Query(None),
    q: str | None = Query(None),
) -> TaskSummaryOut:
    payloads = await _load_payloads(
        s,
        status=status,
        stage=stage,
        time_range=time_range,
        q=q,
        model=model,
    )
    today_tasks, success_rate, total_cost, total_tokens, avg_elapsed = _today_stats(payloads)
    return TaskSummaryOut(
        today_tasks=today_tasks,
        today_success_rate=success_rate,
        today_cost_cny=total_cost,
        today_total_tokens=total_tokens,
        avg_elapsed_ms=avg_elapsed,
        status_counts=_status_counts(payloads),
        model_facets=_model_facets(payloads),
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
    q: str | None = Query(None),
    sort: str = Query("started_at:desc"),
) -> Response:
    payloads = _sort_payloads(
        await _load_payloads(
            s,
            status=status,
            stage=stage,
            time_range=time_range,
            q=q,
            model=model,
        ),
        sort,
    )
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
