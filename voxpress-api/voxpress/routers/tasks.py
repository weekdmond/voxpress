from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from voxpress.db import get_session, session_scope
from voxpress.errors import InvalidUrl, TaskNotFound
from voxpress.models import Creator, Task, Video
from voxpress.pipeline import runner
from voxpress.pipeline.runner import _task_to_payload  # reuse payload shaper
from voxpress.schemas import Page, TaskBatchIn, TaskCreateIn, TaskOut
from voxpress.sse import TaskEvent, broker

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


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


@router.get("", response_model=Page[TaskOut])
async def list_tasks(
    s: AsyncSession = Depends(get_session),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> Page[TaskOut]:
    stmt = select(Task).order_by(Task.started_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(Task.status == status)
    items = (await s.scalars(stmt)).all()
    out: list[TaskOut] = []
    for t in items:
        creator = await s.get(Creator, t.creator_id) if t.creator_id else None
        obj = TaskOut.model_validate(t).model_copy(
            update={
                "creator_name": creator.name if creator else None,
                "creator_initial": (creator.name[0] if creator and creator.name else None),
            }
        )
        out.append(obj)
    total = await s.scalar(select(func.count()).select_from(Task))
    return Page(items=out, cursor=None, total=total or 0)


@router.post("", response_model=TaskOut)
async def create_task(
    payload: TaskCreateIn, s: AsyncSession = Depends(get_session)
) -> TaskOut:
    kind = _url_kind(payload.url)
    if kind is None:
        raise InvalidUrl("链接无法识别或非抖音域名")
    if kind == "user":
        raise InvalidUrl("博主主页请用 /creators/resolve 然后 /tasks/batch")
    task = Task(source_url=payload.url)
    s.add(task)
    await s.commit()
    await s.refresh(task)
    await runner.enqueue(task, None)
    return TaskOut.model_validate(task)


@router.post("/batch")
async def create_batch(payload: TaskBatchIn, s: AsyncSession = Depends(get_session)) -> dict:
    video_ids = payload.video_ids or []
    if not video_ids:
        raise InvalidUrl("video_ids 不能为空")

    rows = (await s.scalars(select(Video).where(Video.id.in_(video_ids)))).all()
    found = {v.id: v for v in rows}

    created: list[Task] = []
    for vid in video_ids:
        v = found.get(vid)
        if not v:
            continue
        task = Task(
            source_url=v.source_url,
            title_guess=v.title,
            creator_id=v.creator_id,
            video_id=v.id,
        )
        s.add(task)
        created.append(task)
    await s.commit()
    for t in created:
        await s.refresh(t)
        creator = await s.get(Creator, t.creator_id) if t.creator_id else None
        await runner.enqueue(t, creator)
    return {"tasks": [TaskOut.model_validate(t).model_dump() for t in created]}


@router.get("/stream")
async def stream_tasks(request: Request) -> EventSourceResponse:
    """SSE endpoint.

    We use a short-lived session *only* for the initial snapshot, then let it
    close before returning the generator. Holding a session for the full life
    of the SSE connection would pin an `idle in transaction` on Postgres and
    block schema-level operations (TRUNCATE, DDL, VACUUM FULL)."""

    initial: list[TaskEvent] = []
    async with session_scope() as s:
        rows = (
            await s.scalars(
                select(Task).where(Task.status.in_(["running", "queued"])).order_by(Task.started_at.asc())
            )
        ).all()
        for t in rows:
            creator = await s.get(Creator, t.creator_id) if t.creator_id else None
            initial.append(TaskEvent("update", _task_to_payload(t, creator)))

    async def event_gen():
        async for ev in broker.stream(initial):
            if await request.is_disconnected():
                break
            yield ev

    return EventSourceResponse(event_gen(), ping=20)


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: UUID, s: AsyncSession = Depends(get_session)) -> TaskOut:
    t = await s.get(Task, task_id)
    if not t:
        raise TaskNotFound(f"task {task_id} not found")
    return TaskOut.model_validate(t)


@router.post("/{task_id}/cancel", response_model=TaskOut)
async def cancel_task(task_id: UUID, s: AsyncSession = Depends(get_session)) -> TaskOut:
    t = await s.get(Task, task_id)
    if not t:
        raise TaskNotFound(f"task {task_id} not found")
    await runner.cancel(t.id)
    if t.status in ("queued", "running"):
        t.status = "canceled"
        t.finished_at = datetime.now(tz=timezone.utc)
        await s.commit()
        await broker.publish(TaskEvent("remove", {"id": str(t.id)}))
    return TaskOut.model_validate(t)


# Export router alias for main.py
_ = Annotated  # keep import
