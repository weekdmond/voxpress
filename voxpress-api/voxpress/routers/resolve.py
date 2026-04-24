"""Single-entry URL dispatcher used by the home-page submit box.

Frontend POSTs any douyin URL — short, video, or creator profile — and we
decide what to do with it server-side. Returns either a kicked-off task
(`kind: "video"`) or a creator id the UI should navigate to (`kind:
"creator"`).

Creator flow: f2 (signed web-API scraper) pulls real profile + video list.
Video flow: yt-dlp handles the download when the task runs.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from voxpress.config import settings
from voxpress.creator_backfill import start_creator_backfill_run
from voxpress.creator_sync import fetch_creator_page, load_cookie_text, upsert_scraped_page
from voxpress.db import get_session
from voxpress.errors import ApiError, InvalidUrl
from voxpress.models import Task, Video
from voxpress.pipeline.douyin_scraper import ScrapeError
from voxpress.schemas import ResolveIn
from voxpress.system_job_store import SystemJobAlreadyRunning
from voxpress.task_store import emit_task_create
from voxpress.url_resolve import UnknownDouyinLink, resolve


class ScrapeFailed(ApiError):
    status_code = 502
    code = "scrape_failed"


router = APIRouter(prefix="/api", tags=["resolve"])
logger = logging.getLogger(__name__)


@router.post("/resolve")
async def resolve_link(
    payload: ResolveIn, s: AsyncSession = Depends(get_session)
) -> dict:
    url = payload.url.strip()
    if not url:
        raise InvalidUrl("链接不能为空")
    try:
        info = await resolve(url)
    except UnknownDouyinLink as e:
        raise InvalidUrl(str(e)) from e

    if info.kind == "video":
        task = Task(source_url=info.canonical_url, trigger_kind="manual")
        s.add(task)
        await s.commit()
        await s.refresh(task)
        await emit_task_create(task.id)
        return {"kind": "video", "task_id": str(task.id)}

    # Creator: scrape via f2 (signs Douyin's web API with ms_token/a_bogus).
    assert info.external_id, "classifier should always produce sec_uid for creators"
    cookie = await _load_cookie_text(s)
    try:
        scraped = await fetch_creator_page(
            info.external_id,
            cookie_text=cookie,
            max_videos=settings.creator_import_max_videos,
        )
    except ScrapeError as e:
        raise ScrapeFailed(str(e)) from e

    backfill_run_id: str | None = None
    backfill_started = False
    listed_count = scraped.creator.video_count or 0
    hit_initial_cap = len(scraped.videos) >= settings.creator_import_max_videos
    initial_partial = listed_count > len(scraped.videos) or (
        listed_count <= 0 and hit_initial_cap
    )
    creator = await upsert_scraped_page(s, scraped, prune_missing=not initial_partial)
    await s.flush()
    stored_count = await s.scalar(
        select(func.count()).select_from(Video).where(Video.creator_id == creator.id)
    )
    needs_backfill = listed_count > int(stored_count or 0)
    await s.commit()
    if needs_backfill:
        try:
            run_id = await start_creator_backfill_run(
                creator_id=creator.id,
                trigger_kind="auto",
                background=True,
            )
            backfill_run_id = str(run_id)
            backfill_started = True
        except SystemJobAlreadyRunning:
            logger.info("creator backfill skipped: another run is already active")
    return {
        "kind": "creator",
        "creator_id": creator.id,
        "name": creator.name,
        "video_count": creator.video_count,
        "fetched_video_count": len(scraped.videos),
        "backfill_started": backfill_started,
        "backfill_run_id": backfill_run_id,
    }


async def _load_cookie_text(s: AsyncSession) -> str | None:
    return await load_cookie_text(s)
