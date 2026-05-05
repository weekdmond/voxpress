from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select

from voxpress.creator_sync import fetch_creator_page, load_cookie_text, upsert_scraped_page
from voxpress.db import session_scope
from voxpress.models import Creator
from voxpress.pipeline.douyin_scraper import ScrapeError
from voxpress.system_job_store import (
    finish_system_job_run,
    start_system_job_run,
    system_job_heartbeat,
)

logger = logging.getLogger(__name__)
_background_runs: set[asyncio.Task[None]] = set()


class CreatorBackfillNotFound(Exception):
    pass


@dataclass(frozen=True)
class CreatorBackfillTarget:
    creator_id: int
    sec_uid: str
    name: str
    listed_video_count: int
    cookie_text: str | None


async def _load_target(creator_id: int) -> CreatorBackfillTarget:
    async with session_scope() as s:
        creator = await s.scalar(
            select(Creator).where(Creator.id == creator_id, Creator.platform == "douyin").limit(1)
        )
        if creator is None:
            raise CreatorBackfillNotFound(str(creator_id))
        cookie_text = await load_cookie_text(s)
        return CreatorBackfillTarget(
            creator_id=creator.id,
            sec_uid=creator.external_id,
            name=creator.name,
            listed_video_count=creator.video_count,
            cookie_text=cookie_text,
        )


def _scope(target: CreatorBackfillTarget) -> str:
    return f"{target.name} · 全量作品"


def _detail(trigger_kind: str, target: CreatorBackfillTarget) -> str:
    prefix = "首次导入后自动补齐" if trigger_kind == "auto" else "手动补齐来源作品"
    return f"{prefix} · 主页标注 {target.listed_video_count} 条"


async def _execute_run(run_id: UUID, target: CreatorBackfillTarget) -> None:
    try:
        if not target.cookie_text or not target.cookie_text.strip():
            await finish_system_job_run(
                run_id,
                status="skipped",
                detail="未导入抖音 Cookie，无法补齐来源作品",
                total_items=target.listed_video_count,
                skipped_items=target.listed_video_count,
            )
            return

        async with system_job_heartbeat(run_id):
            page = await fetch_creator_page(
                target.sec_uid,
                cookie_text=target.cookie_text,
                max_videos=None,
            )
            async with session_scope() as s:
                await upsert_scraped_page(s, page, prune_missing=True)

        total = page.creator.video_count or target.listed_video_count or len(page.videos)
        processed = len(page.videos)
        skipped = max(0, total - processed)
        status = "done" if page.complete else "failed"
        detail = f"补齐 {page.creator.name} · 已入库 {processed}/{total} 条视频"
        if not page.complete:
            detail = f"{detail} · 抓取中途失败，保留已入库部分"
        await finish_system_job_run(
            run_id,
            status=status,
            detail=detail,
            total_items=total,
            processed_items=processed,
            skipped_items=skipped,
        )
        logger.info(
            "creator backfill finished: creator_id=%s processed=%s total=%s complete=%s",
            target.creator_id,
            processed,
            total,
            page.complete,
        )
    except asyncio.CancelledError:
        await finish_system_job_run(
            run_id,
            status="skipped",
            detail="补齐任务被取消",
            total_items=target.listed_video_count,
        )
        raise
    except ScrapeError as exc:
        await finish_system_job_run(
            run_id,
            status="failed",
            detail=f"补齐 {target.name} 失败",
            error=str(exc),
            total_items=target.listed_video_count,
        )
    except Exception as exc:
        logger.exception("creator backfill crashed: creator_id=%s", target.creator_id)
        await finish_system_job_run(
            run_id,
            status="failed",
            detail=f"补齐 {target.name} 异常退出",
            error=str(exc),
            total_items=target.listed_video_count,
        )


async def start_creator_backfill_run(
    *,
    creator_id: int,
    trigger_kind: str = "manual",
    background: bool = False,
) -> UUID:
    target = await _load_target(creator_id)
    run_id = await start_system_job_run(
        job_key="creator_backfill",
        job_name="来源作品补齐",
        trigger_kind=trigger_kind,
        scope=_scope(target),
        detail=_detail(trigger_kind, target),
    )
    if background:
        task = asyncio.create_task(
            _execute_run(run_id, target),
            name=f"creator-backfill:{creator_id}:{run_id}",
        )
        _background_runs.add(task)
        task.add_done_callback(_background_runs.discard)
        return run_id
    await _execute_run(run_id, target)
    return run_id


async def cancel_background_backfills() -> None:
    for task in list(_background_runs):
        task.cancel()
    for task in list(_background_runs):
        with suppress(asyncio.CancelledError):
            await task
