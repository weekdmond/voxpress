from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from voxpress.config import settings
from voxpress.db import session_scope
from voxpress.models import SystemJobRun

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class SystemJobAlreadyRunning(Exception):
    def __init__(self, job_key: str) -> None:
        super().__init__(job_key)
        self.job_key = job_key


def _is_running_job_conflict(exc: IntegrityError) -> bool:
    constraint_name = getattr(getattr(exc, "orig", None), "constraint_name", "")
    return constraint_name == "uq_system_job_runs_running_job_key" or (
        "uq_system_job_runs_running_job_key" in str(exc.orig)
    )


async def start_system_job_run(
    *,
    job_key: str,
    job_name: str,
    trigger_kind: str = "scheduled",
    scope: str | None = None,
    detail: str | None = None,
) -> UUID:
    await recover_stale_system_job_runs(job_key=job_key)
    try:
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
    except IntegrityError as exc:
        if _is_running_job_conflict(exc):
            raise SystemJobAlreadyRunning(job_key) from exc
        raise


async def heartbeat_system_job_run(run_id: UUID) -> None:
    async with session_scope() as s:
        row = await s.scalar(
            select(SystemJobRun)
            .where(SystemJobRun.id == run_id, SystemJobRun.status == "running")
            .limit(1)
        )
        if row is not None:
            row.updated_at = _utc_now()


async def recover_stale_system_job_runs(
    *,
    job_key: str | None = None,
    stale_after_seconds: int | None = None,
) -> int:
    stale_after = stale_after_seconds or settings.system_job_stale_after_seconds
    cutoff = _utc_now() - timedelta(seconds=stale_after)
    clauses = [
        SystemJobRun.status == "running",
        SystemJobRun.updated_at < cutoff,
    ]
    if job_key:
        clauses.append(SystemJobRun.job_key == job_key)

    async with session_scope() as s:
        rows = (await s.scalars(select(SystemJobRun).where(*clauses))).all()
        now = _utc_now()
        for row in rows:
            row.status = "failed"
            row.detail = f"{row.detail or row.job_name} · 运行心跳超时，已自动收口"
            row.error = "system job heartbeat timed out"
            row.finished_at = now
            if row.started_at:
                row.duration_ms = max(0, int((now - row.started_at).total_seconds() * 1000))
        count = len(rows)
    if count:
        logger.warning("recovered %s stale system job run(s): job_key=%s", count, job_key or "*")
    return count


async def _heartbeat_loop(run_id: UUID, interval_seconds: int) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await heartbeat_system_job_run(run_id)
        except Exception:
            logger.warning("system job heartbeat failed: run_id=%s", run_id, exc_info=True)


@asynccontextmanager
async def system_job_heartbeat(run_id: UUID) -> AsyncIterator[None]:
    task = asyncio.create_task(
        _heartbeat_loop(run_id, settings.system_job_heartbeat_seconds),
        name=f"system-job-heartbeat:{run_id}",
    )
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


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
