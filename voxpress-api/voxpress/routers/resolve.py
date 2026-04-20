"""Single-entry URL dispatcher used by the home-page submit box.

Frontend POSTs any douyin URL — short, video, or creator profile — and we
decide what to do with it server-side. Returns either a kicked-off task
(`kind: "video"`) or a creator id the UI should navigate to (`kind:
"creator"`).

Creator flow: f2 (signed web-API scraper) pulls real profile + video list.
Video flow: yt-dlp handles the download when the task runs.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voxpress.db import get_session
from voxpress.errors import ApiError, InvalidUrl
from voxpress.models import Creator, SettingEntry, Task, Video
from voxpress.pipeline import runner
from voxpress.pipeline.douyin_scraper import (
    ScrapeError,
    ScrapedCreator,
    ScrapedUserPage,
    ScrapedVideo,
    scrape_user_page,
)
from voxpress.schemas import ResolveIn
from voxpress.url_resolve import UnknownDouyinLink, resolve


class ScrapeFailed(ApiError):
    status_code = 502
    code = "scrape_failed"


router = APIRouter(prefix="/api", tags=["resolve"])


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
        task = Task(source_url=info.canonical_url)
        s.add(task)
        await s.commit()
        await s.refresh(task)
        await runner.enqueue(task, None)
        return {"kind": "video", "task_id": str(task.id)}

    # Creator: scrape via f2 (signs Douyin's web API with ms_token/a_bogus).
    assert info.external_id, "classifier should always produce sec_uid for creators"
    cookie = await _load_cookie_text(s)
    try:
        scraped = await scrape_user_page(info.external_id, cookie=cookie)
    except ScrapeError as e:
        raise ScrapeFailed(str(e)) from e

    creator = await _upsert_scraped(s, scraped)
    await s.commit()
    return {
        "kind": "creator",
        "creator_id": creator.id,
        "name": creator.name,
        "video_count": len(scraped.videos),
    }


async def _load_cookie_text(s: AsyncSession) -> str | None:
    row = await s.get(SettingEntry, "cookie")
    return row.value.get("text") if row else None


async def _upsert_scraped(s: AsyncSession, page: ScrapedUserPage) -> Creator:
    creator = await _upsert_creator(s, page.creator)
    await s.flush()
    for v in page.videos:
        await _upsert_video(s, creator.id, v)
    creator.video_count = max(creator.video_count, len(page.videos))
    return creator


async def _upsert_creator(s: AsyncSession, c: ScrapedCreator) -> Creator:
    existing = await s.scalar(
        select(Creator).where(Creator.platform == "douyin", Creator.external_id == c.sec_uid)
    )
    now = datetime.now(tz=timezone.utc)
    if existing:
        existing.name = c.name
        existing.handle = c.handle
        existing.bio = c.bio
        existing.region = c.region
        existing.verified = c.verified
        existing.followers = c.followers
        existing.total_likes = c.total_likes
        existing.recent_update_at = now
        return existing
    row = Creator(
        platform="douyin",
        external_id=c.sec_uid,
        handle=c.handle,
        name=c.name,
        bio=c.bio,
        region=c.region,
        verified=c.verified,
        followers=c.followers,
        total_likes=c.total_likes,
        video_count=0,
        recent_update_at=now,
    )
    s.add(row)
    return row


async def _upsert_video(s: AsyncSession, creator_id: int, v: ScrapedVideo) -> None:
    published = (
        datetime.fromtimestamp(v.published_at_ts, tz=timezone.utc)
        if v.published_at_ts
        else datetime.now(tz=timezone.utc)
    )
    existing = await s.get(Video, v.id)
    if existing:
        existing.title = v.title
        existing.duration_sec = v.duration_sec
        existing.likes = v.likes
        existing.plays = v.plays
        existing.comments = v.comments
        existing.shares = v.shares
        existing.collects = v.collects
        existing.cover_url = v.cover_url
        existing.published_at = published
        return
    s.add(
        Video(
            id=v.id,
            creator_id=creator_id,
            title=v.title,
            duration_sec=v.duration_sec,
            likes=v.likes,
            plays=v.plays,
            comments=v.comments,
            shares=v.shares,
            collects=v.collects,
            published_at=published,
            cover_url=v.cover_url,
            source_url=v.source_url,
        )
    )
