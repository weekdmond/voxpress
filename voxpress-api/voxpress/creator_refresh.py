from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from voxpress.config import settings
from voxpress.creator_sync import refresh_all_creators
from voxpress.system_job_store import finish_system_job_run, start_system_job_run

logger = logging.getLogger(__name__)


class CreatorRefreshScheduler:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not settings.creator_refresh_enabled:
            logger.info("creator refresh scheduler disabled")
            return
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop(), name="creator-refresh-scheduler")

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run_loop(self) -> None:
        interval_sec = settings.creator_refresh_interval_hours * 3600
        recent_count = settings.creator_refresh_recent_count
        job_scope = f"抖音博主库 · 最近 {recent_count} 条作品"
        logger.info(
            "creator refresh scheduler started: every %sh, latest %s videos",
            settings.creator_refresh_interval_hours,
            recent_count,
        )
        while True:
            run_id = await start_system_job_run(
                job_key="creator_refresh",
                job_name="博主定时刷新",
                scope=job_scope,
                detail=f"每 {settings.creator_refresh_interval_hours} 小时刷新一次",
            )
            try:
                summary = await refresh_all_creators(max_videos=recent_count)
                status = "done"
                if summary.skipped >= summary.total and summary.total > 0:
                    status = "skipped"
                elif summary.failed > 0:
                    status = "failed"
                detail = (
                    f"刷新 {summary.refreshed}/{summary.total} 位博主"
                    f" · 失败 {summary.failed}"
                    f" · 跳过 {summary.skipped}"
                )
                await finish_system_job_run(
                    run_id,
                    status=status,
                    detail=detail,
                    total_items=summary.total,
                    processed_items=summary.refreshed,
                    failed_items=summary.failed,
                    skipped_items=summary.skipped,
                )
                logger.info(
                    "creator refresh cycle finished: refreshed=%s failed=%s skipped=%s total=%s",
                    summary.refreshed,
                    summary.failed,
                    summary.skipped,
                    summary.total,
                )
            except asyncio.CancelledError:
                await finish_system_job_run(
                    run_id,
                    status="skipped",
                    detail="调度器停止，当前刷新被取消",
                )
                raise
            except Exception as exc:
                logger.exception("creator refresh cycle crashed")
                await finish_system_job_run(
                    run_id,
                    status="failed",
                    detail="刷新循环异常退出",
                    error=str(exc),
                )

            try:
                await asyncio.sleep(interval_sec)
            except asyncio.CancelledError:
                raise


scheduler = CreatorRefreshScheduler()
