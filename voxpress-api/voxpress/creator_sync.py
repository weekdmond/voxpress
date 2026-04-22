from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from voxpress.db import session_scope
from voxpress.models import Article, Creator, SettingEntry, Video
from voxpress.pipeline.douyin_scraper import ScrapeError, ScrapedCreator, ScrapedUserPage, ScrapedVideo, scrape_user_page

logger = logging.getLogger(__name__)


@dataclass
class CreatorRefreshSummary:
    total: int
    refreshed: int
    failed: int
    skipped: int = 0


async def load_cookie_text(s: AsyncSession) -> str | None:
    row = await s.get(SettingEntry, "cookie")
    return row.value.get("text") if row else None


async def fetch_creator_page(
    sec_uid: str,
    *,
    cookie_text: str | None,
    max_videos: int | None = None,
) -> ScrapedUserPage:
    return await scrape_user_page(sec_uid, cookie=cookie_text, max_videos=max_videos)


async def upsert_scraped_page(
    s: AsyncSession,
    page: ScrapedUserPage,
    *,
    prune_missing: bool,
) -> Creator:
    creator = await _upsert_creator(s, page.creator)
    await s.flush()
    scraped_ids: list[str] = []
    for v in page.videos:
        await _upsert_video(s, creator.id, v)
        scraped_ids.append(v.id)
    if prune_missing and page.complete:
        await _prune_stale_videos(s, creator.id, scraped_ids)
    creator.video_count = page.creator.video_count or len(page.videos)
    return creator


async def refresh_all_creators(*, max_videos: int) -> CreatorRefreshSummary:
    async with session_scope() as s:
        cookie_text = await load_cookie_text(s)
        rows = (
            await s.execute(
                select(Creator.id, Creator.external_id)
                .where(Creator.platform == "douyin")
                .order_by(Creator.followers.desc(), Creator.id.asc())
            )
        ).all()

    total = len(rows)
    if total == 0:
        return CreatorRefreshSummary(total=0, refreshed=0, failed=0, skipped=0)
    if not cookie_text or not cookie_text.strip():
        logger.warning("creator refresh skipped: missing Douyin cookie")
        return CreatorRefreshSummary(total=total, refreshed=0, failed=0, skipped=total)

    refreshed = 0
    failed = 0

    for creator_id, sec_uid in rows:
        try:
            page = await fetch_creator_page(sec_uid, cookie_text=cookie_text, max_videos=max_videos)
        except ScrapeError as e:
            message = str(e)
            if _looks_like_cookie_issue(message):
                logger.warning("creator refresh aborted: %s", message)
                return CreatorRefreshSummary(
                    total=total,
                    refreshed=refreshed,
                    failed=total - refreshed,
                    skipped=0,
                )
            failed += 1
            logger.warning(
                "creator refresh failed for creator_id=%s sec_uid=%s: %s",
                creator_id,
                sec_uid,
                message,
            )
            continue

        async with session_scope() as s:
            await upsert_scraped_page(s, page, prune_missing=False)
        refreshed += 1

    return CreatorRefreshSummary(total=total, refreshed=refreshed, failed=failed, skipped=0)


def _looks_like_cookie_issue(message: str) -> bool:
    low = message.lower()
    return "cookie" in low or "登录" in message or "过期" in message


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
        existing.avatar_url = c.avatar_url
        existing.verified = c.verified
        existing.followers = c.followers
        existing.total_likes = c.total_likes
        existing.video_count = c.video_count
        existing.recent_update_at = now
        return existing
    row = Creator(
        platform="douyin",
        external_id=c.sec_uid,
        handle=c.handle,
        name=c.name,
        bio=c.bio,
        region=c.region,
        avatar_url=c.avatar_url,
        verified=c.verified,
        followers=c.followers,
        total_likes=c.total_likes,
        video_count=c.video_count,
        recent_update_at=now,
    )
    s.add(row)
    return row


async def _upsert_video(s: AsyncSession, creator_id: int, v: ScrapedVideo) -> None:
    now = datetime.now(tz=timezone.utc)
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
        existing.source_url = v.source_url
        existing.published_at = published
        existing.updated_at = now
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
            updated_at=now,
        )
    )


async def _prune_stale_videos(s: AsyncSession, creator_id: int, scraped_ids: list[str]) -> None:
    stmt = (
        select(Video.id)
        .outerjoin(Article, Article.video_id == Video.id)
        .where(Video.creator_id == creator_id, Article.id.is_(None))
    )
    if scraped_ids:
        stmt = stmt.where(Video.id.not_in(scraped_ids))
    stale_ids = list((await s.scalars(stmt)).all())
    if not stale_ids:
        return
    await s.execute(delete(Video).where(Video.id.in_(stale_ids)))
