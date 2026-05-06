"""Single-entry URL dispatcher used by the home-page submit box.

Frontend POSTs any douyin URL — short, video, or creator profile — and we
decide what to do with it server-side. Returns either a kicked-off task
(`kind: "video"`) or a creator id the UI should navigate to (`kind:
"creator"`).

Creator flow: f2 (signed web-API scraper) pulls real profile + video list.
Video flow: yt-dlp handles the download when the task runs.
"""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from voxpress.auto_tasks import create_auto_tasks_for_videos
from voxpress.config import settings
from voxpress.creator_backfill import start_creator_backfill_run
from voxpress.creator_sync import fetch_creator_page, load_cookie_text, upsert_scraped_page
from voxpress.db import get_session
from voxpress.errors import ApiError, InvalidUrl
from voxpress.models import Task, Video
from voxpress.pipeline.douyin_scraper import ScrapeError
from voxpress.pipeline.youtube_url import UnknownYouTubeLink, is_youtube_url, resolve_youtube_url
from voxpress.pipeline.youtube_ytdlp import YouTubeExtractError, probe_video
from voxpress.schemas import ResolveIn
from voxpress.system_job_store import SystemJobAlreadyRunning
from voxpress.task_store import emit_task_create
from voxpress.url_resolve import UnknownDouyinLink, normalize_douyin_input, resolve
from voxpress.youtube_sync import sync_youtube_channel, upsert_youtube_channel, upsert_youtube_video


class ScrapeFailed(ApiError):
    status_code = 502
    code = "scrape_failed"


class CreatorResolveTimeout(ApiError):
    status_code = 504
    code = "creator_resolve_timeout"


router = APIRouter(prefix="/api", tags=["resolve"])
logger = logging.getLogger(__name__)


@router.post("/resolve")
async def resolve_link(
    payload: ResolveIn, s: AsyncSession = Depends(get_session)
) -> dict:
    started_at = time.perf_counter()
    if is_youtube_url(payload.url):
        return await _resolve_youtube_link(payload.url, s=s, started_at=started_at)

    url = normalize_douyin_input(payload.url)
    if not url:
        raise InvalidUrl("链接不能为空")
    logger.info("resolve start url=%s", url)
    try:
        info = await resolve(url)
    except UnknownDouyinLink as e:
        raise InvalidUrl(str(e)) from e
    logger.info(
        "resolve classified kind=%s canonical_url=%s elapsed_ms=%d",
        info.kind,
        info.canonical_url,
        int((time.perf_counter() - started_at) * 1000),
    )

    if info.kind == "video":
        task = Task(source_url=info.canonical_url, trigger_kind="manual")
        s.add(task)
        await s.commit()
        await s.refresh(task)
        await emit_task_create(task.id)
        logger.info(
            "resolve video queued task_id=%s elapsed_ms=%d",
            task.id,
            int((time.perf_counter() - started_at) * 1000),
        )
        return {"kind": "video", "task_id": str(task.id)}

    # Creator: scrape via f2 (signs Douyin's web API with ms_token/a_bogus).
    assert info.external_id, "classifier should always produce sec_uid for creators"
    cookie = await _load_cookie_text(s)
    logger.info(
        "resolve creator scrape start sec_uid=%s max_videos=%d",
        info.external_id,
        settings.creator_import_max_videos,
    )
    try:
        async with asyncio.timeout(settings.creator_resolve_timeout_sec):
            scraped = await fetch_creator_page(
                info.external_id,
                cookie_text=cookie,
                max_videos=settings.creator_import_max_videos,
            )
    except TimeoutError as e:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        logger.warning(
            "resolve creator timeout sec_uid=%s timeout_sec=%d elapsed_ms=%d",
            info.external_id,
            settings.creator_resolve_timeout_sec,
            elapsed_ms,
        )
        raise CreatorResolveTimeout(
            "创作者主页同步超时，请稍后重试。通常是抖音响应较慢，或当前 Cookie 已失效。",
            detail={
                "stage": "creator_scrape",
                "timeout_sec": settings.creator_resolve_timeout_sec,
            },
        ) from e
    except ScrapeError as e:
        logger.warning("resolve creator failed sec_uid=%s error=%s", info.external_id, e)
        raise ScrapeFailed(str(e), detail={"stage": "creator_scrape"}) from e

    backfill_run_id: str | None = None
    backfill_started = False
    listed_count = scraped.creator.video_count or 0
    hit_initial_cap = len(scraped.videos) >= settings.creator_import_max_videos
    initial_partial = listed_count > len(scraped.videos) or (
        listed_count <= 0 and hit_initial_cap
    )
    new_videos: list[Video] = []
    creator = await upsert_scraped_page(
        s,
        scraped,
        prune_missing=not initial_partial,
        new_videos_out=new_videos,
    )
    await s.flush()
    stored_count = await s.scalar(
        select(func.count()).select_from(Video).where(Video.creator_id == creator.id)
    )
    needs_backfill = listed_count > int(stored_count or 0)
    auto_tasks = []
    if settings.creator_auto_task_enabled:
        auto_tasks = await create_auto_tasks_for_videos(
            s,
            new_videos,
            limit=settings.creator_auto_task_recent_count,
        )
    await s.commit()
    for task in auto_tasks:
        await emit_task_create(task.id)
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
    logger.info(
        "resolve creator synced creator_id=%s fetched_videos=%d stored_videos=%d elapsed_ms=%d",
        creator.id,
        len(scraped.videos),
        int(stored_count or 0),
        int((time.perf_counter() - started_at) * 1000),
    )
    return {
        "kind": "creator",
        "creator_id": creator.id,
        "name": creator.name,
        "video_count": creator.video_count,
        "fetched_video_count": len(scraped.videos),
        "backfill_started": backfill_started,
        "backfill_run_id": backfill_run_id,
    }


async def _resolve_youtube_link(
    url: str,
    *,
    s: AsyncSession,
    started_at: float,
) -> dict:
    try:
        info = resolve_youtube_url(url)
    except UnknownYouTubeLink as e:
        raise InvalidUrl(str(e)) from e

    logger.info("resolve youtube classified kind=%s canonical_url=%s", info.kind, info.canonical_url)
    if info.kind == "playlist":
        raise InvalidUrl("暂不支持 YouTube playlist，请导入单条视频或频道")

    if info.kind == "video":
        try:
            video_info = await probe_video(info.canonical_url)
        except YouTubeExtractError as e:
            raise ScrapeFailed(str(e), detail={"stage": "youtube_video_probe"}) from e
        creator = await upsert_youtube_channel(s, video_info.channel)
        await s.flush()
        video = await upsert_youtube_video(s, creator.id, video_info)
        task = Task(
            source_url=video_info.source_url,
            title_guess=video_info.title,
            creator_id=creator.id,
            video_id=video_info.id,
            trigger_kind="manual",
        )
        s.add(task)
        await s.commit()
        await s.refresh(task)
        await emit_task_create(task.id)
        logger.info(
            "resolve youtube video queued task_id=%s elapsed_ms=%d",
            task.id,
            int((time.perf_counter() - started_at) * 1000),
        )
        return {"kind": "video", "task_id": str(task.id)}

    try:
        creator, fetched_count, task_ids = await sync_youtube_channel(
            info.canonical_url,
            max_videos=settings.creator_import_max_videos,
            prune_missing=False,
        )
    except YouTubeExtractError as e:
        raise ScrapeFailed(str(e), detail={"stage": "youtube_channel_sync"}) from e
    return {
        "kind": "creator",
        "creator_id": creator.id,
        "name": creator.name,
        "video_count": creator.video_count,
        "fetched_video_count": fetched_count,
        "backfill_started": False,
        "backfill_run_id": None,
        "auto_task_count": len(task_ids),
    }


async def _load_cookie_text(s: AsyncSession) -> str | None:
    return await load_cookie_text(s)
