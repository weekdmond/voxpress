from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from voxpress.config import settings
from voxpress.creator_sync import refresh_all_creators

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
        logger.info(
            "creator refresh scheduler started: every %sh, latest %s videos",
            settings.creator_refresh_interval_hours,
            recent_count,
        )
        while True:
            try:
                summary = await refresh_all_creators(max_videos=recent_count)
                logger.info(
                    "creator refresh cycle finished: refreshed=%s failed=%s skipped=%s total=%s",
                    summary.refreshed,
                    summary.failed,
                    summary.skipped,
                    summary.total,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("creator refresh cycle crashed")

            try:
                await asyncio.sleep(interval_sec)
            except asyncio.CancelledError:
                raise


scheduler = CreatorRefreshScheduler()
