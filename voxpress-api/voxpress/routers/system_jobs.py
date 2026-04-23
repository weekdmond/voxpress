from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from voxpress.db import get_session
from voxpress.models import SystemJobRun
from voxpress.schemas import Page, SystemJobRunOut, SystemJobSummaryOut

router = APIRouter(prefix="/api/system-jobs", tags=["system-jobs"])


def _local_now() -> datetime:
    return datetime.now().astimezone()


def _time_cutoff(value: str | None) -> datetime | None:
    if not value or value == "all":
        return None
    now = _local_now()
    if value == "1h":
        return now - timedelta(hours=1)
    if value in {"24h", "today"}:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if value == "7d":
        return now - timedelta(days=7)
    if value == "30d":
        return now - timedelta(days=30)
    return None


def _job_filters(*, status: str | None, time_range: str | None, q: str | None) -> list[Any]:
    clauses: list[Any] = []
    if status:
        clauses.append(SystemJobRun.status == status)
    cutoff = _time_cutoff(time_range)
    if cutoff is not None:
        clauses.append(SystemJobRun.started_at >= cutoff)
    if q:
        like = f"%{q.strip()}%"
        clauses.append(
            or_(
                cast(SystemJobRun.id, Text).ilike(like),
                SystemJobRun.job_key.ilike(like),
                SystemJobRun.job_name.ilike(like),
                SystemJobRun.scope.ilike(like),
                SystemJobRun.detail.ilike(like),
                SystemJobRun.error.ilike(like),
            )
        )
    return clauses


@router.get("", response_model=Page[SystemJobRunOut])
async def list_system_jobs(
    s: AsyncSession = Depends(get_session),
    status: str | None = Query(None),
    time_range: str | None = Query(None),
    since: str | None = Query(None),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    offset: int | None = Query(None, ge=0),
    limit: int = Query(20, ge=1, le=200),
) -> Page[SystemJobRunOut]:
    clauses = _job_filters(status=status, time_range=time_range or since, q=q)
    total = await s.scalar(select(func.count()).select_from(SystemJobRun).where(*clauses))
    resolved_offset = offset if offset is not None else max(0, (page - 1) * limit)
    rows = (
        await s.scalars(
            select(SystemJobRun)
            .where(*clauses)
            .order_by(SystemJobRun.started_at.desc(), SystemJobRun.updated_at.desc())
            .offset(resolved_offset)
            .limit(limit)
        )
    ).all()
    return Page(
        items=[SystemJobRunOut.model_validate(row) for row in rows],
        cursor=None,
        total=int(total or 0),
    )


@router.get("/summary", response_model=SystemJobSummaryOut)
async def system_jobs_summary(
    s: AsyncSession = Depends(get_session),
    status: str | None = Query(None),
    time_range: str | None = Query(None),
    since: str | None = Query(None),
    q: str | None = Query(None),
) -> SystemJobSummaryOut:
    clauses = _job_filters(status=status, time_range=time_range or since, q=q)
    today_cutoff = _local_now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_runs = int(
        await s.scalar(select(func.count()).select_from(SystemJobRun).where(*clauses, SystemJobRun.started_at >= today_cutoff))
        or 0
    )
    today_done = int(
        await s.scalar(
            select(func.count()).select_from(SystemJobRun).where(
                *clauses,
                SystemJobRun.started_at >= today_cutoff,
                SystemJobRun.status == "done",
            )
        )
        or 0
    )
    today_failed = int(
        await s.scalar(
            select(func.count()).select_from(SystemJobRun).where(
                *clauses,
                SystemJobRun.started_at >= today_cutoff,
                SystemJobRun.status == "failed",
            )
        )
        or 0
    )
    today_processed = int(
        await s.scalar(
            select(func.coalesce(func.sum(SystemJobRun.processed_items), 0)).where(
                *clauses,
                SystemJobRun.started_at >= today_cutoff,
            )
        )
        or 0
    )
    today_failed_items = int(
        await s.scalar(
            select(func.coalesce(func.sum(SystemJobRun.failed_items), 0)).where(
                *clauses,
                SystemJobRun.started_at >= today_cutoff,
            )
        )
        or 0
    )
    avg_duration = int(
        await s.scalar(
            select(func.coalesce(func.avg(SystemJobRun.duration_ms), 0)).where(
                *clauses,
                SystemJobRun.started_at >= today_cutoff,
                SystemJobRun.duration_ms.is_not(None),
            )
        )
        or 0
    )
    denom = today_done + today_failed
    success_rate = round((today_done / denom) * 100, 1) if denom else 0.0
    status_rows = (await s.execute(select(SystemJobRun.status, func.count()).where(*clauses).group_by(SystemJobRun.status))).all()
    status_counts = {"running": 0, "done": 0, "failed": 0, "skipped": 0}
    for run_status, count in status_rows:
        if run_status in status_counts:
            status_counts[run_status] = int(count)
    return SystemJobSummaryOut(
        today_runs=today_runs,
        today_success_rate=success_rate,
        today_processed_items=today_processed,
        today_failed_items=today_failed_items,
        avg_duration_ms=avg_duration,
        status_counts=status_counts,
    )

