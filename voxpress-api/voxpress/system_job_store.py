from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from voxpress.db import session_scope
from voxpress.models import SystemJobRun


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


async def start_system_job_run(
    *,
    job_key: str,
    job_name: str,
    trigger_kind: str = "scheduled",
    scope: str | None = None,
    detail: str | None = None,
) -> UUID:
    async with session_scope() as s:
        row = SystemJobRun(
            job_key=job_key,
            job_name=job_name,
            trigger_kind=trigger_kind,
            status="running",
            scope=scope,
            detail=detail,
        )
        s.add(row)
        await s.flush()
        return row.id


async def finish_system_job_run(
    run_id: UUID,
    *,
    status: str,
    detail: str | None = None,
    error: str | None = None,
    total_items: int = 0,
    processed_items: int = 0,
    failed_items: int = 0,
    skipped_items: int = 0,
) -> None:
    async with session_scope() as s:
        row = await s.scalar(select(SystemJobRun).where(SystemJobRun.id == run_id).limit(1))
        if row is None:
            return
        now = _utc_now()
        row.status = status
        row.detail = detail
        row.error = error
        row.total_items = total_items
        row.processed_items = processed_items
        row.failed_items = failed_items
        row.skipped_items = skipped_items
        row.finished_at = now
        if row.started_at:
            row.duration_ms = max(0, int((now - row.started_at).total_seconds() * 1000))

