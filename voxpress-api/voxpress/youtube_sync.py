from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from voxpress.auto_tasks import create_auto_tasks_for_videos
from voxpress.config import settings
from voxpress.db import session_scope
from voxpress.models import Article, Creator, Task, Video
from voxpress.pipeline.youtube_rss import fetch_channel_feed
from voxpress.pipeline.youtube_ytdlp import (
    YouTubeChannelInfo,
    YouTubeVideoInfo,
    fetch_channel_videos,
    resolve_channel,
)
from voxpress.task_store import emit_task_create


async def sync_youtube_channel(
    url: str,
    *,
    max_videos: int | None,
    prune_missing: bool = False,
    create_tasks: bool = True,
) -> tuple[Creator, int, list[UUID]]:
    channel, videos = await fetch_channel_videos(url, max_videos=max_videos)
    if channel.channel_id:
        try:
            rss_videos = await fetch_channel_feed(channel.channel_id, max_videos=max_videos)
        except Exception:
            rss_videos = []
        if rss_videos:
            by_id = {video.id: video for video in videos}
            for rss_video in rss_videos:
                if rss_video.id not in by_id:
                    videos.append(
                        YouTubeVideoInfo(
                            id=rss_video.id,
                            external_id=rss_video.external_id,
                            title=rss_video.title,
                            duration_sec=0,
                            plays=0,
                            likes=0,
                            comments=0,
                            cover_url=f"https://i.ytimg.com/vi/{rss_video.external_id}/hqdefault.jpg",
                            source_url=rss_video.source_url,
                            published_at=rss_video.published_at,
                            channel=channel,
                        )
                    )

    new_videos: list[Video] = []
    async with session_scope() as s:
        creator = await upsert_youtube_channel(s, channel)
        await s.flush()
        for item in videos:
            new_video = await upsert_youtube_video(s, creator.id, item)
            if new_video is not None:
                new_videos.append(new_video)
        if prune_missing:
            await _prune_stale_videos(s, creator.id, [item.id for item in videos])
        creator.video_count = len(videos)
        tasks = await _create_auto_tasks(s, new_videos) if create_tasks else []
        task_ids = [task.id for task in tasks]
        await s.flush()
        creator_id = creator.id

    for task_id in task_ids:
        await emit_task_create(task_id)

    async with session_scope() as s:
        stored_creator = await s.get(Creator, creator_id)
        if stored_creator is None:
            raise RuntimeError(f"YouTube creator {creator_id} missing after sync")
        return stored_creator, len(videos), task_ids


async def sync_youtube_channel_by_id(
    channel_id: str,
    *,
    max_videos: int | None,
    prune_missing: bool = False,
) -> tuple[Creator, int, list[UUID]]:
    return await sync_youtube_channel(
        f"https://www.youtube.com/channel/{channel_id}",
        max_videos=max_videos,
        prune_missing=prune_missing,
    )


async def upsert_youtube_channel(s: AsyncSession, channel: YouTubeChannelInfo) -> Creator:
    now = datetime.now(tz=timezone.utc)
    existing = await s.scalar(
        select(Creator).where(
            Creator.platform == "youtube",
            Creator.external_id == channel.channel_id,
        )
    )
    if existing:
        existing.name = channel.name
        existing.handle = channel.handle
        existing.avatar_url = channel.avatar_url or existing.avatar_url
        existing.followers = max(existing.followers or 0, channel.followers or 0)
        existing.video_count = max(existing.video_count or 0, channel.video_count or 0)
        existing.recent_update_at = now
        return existing
    row = Creator(
        platform="youtube",
        external_id=channel.channel_id,
        handle=channel.handle,
        name=channel.name,
        bio=None,
        region=None,
        avatar_url=channel.avatar_url,
        verified=False,
        followers=channel.followers,
        total_likes=0,
        video_count=channel.video_count,
        recent_update_at=now,
    )
    s.add(row)
    return row


async def upsert_youtube_video(s: AsyncSession, creator_id: int, video: YouTubeVideoInfo) -> Video | None:
    now = datetime.now(tz=timezone.utc)
    existing = await s.get(Video, video.id)
    if existing:
        existing.creator_id = creator_id
        existing.title = video.title
        existing.duration_sec = video.duration_sec
        existing.likes = video.likes
        existing.plays = video.plays
        existing.comments = video.comments
        existing.cover_url = video.cover_url
        existing.source_url = video.source_url
        existing.published_at = video.published_at
        existing.updated_at = now
        return None
    row = Video(
        id=video.id,
        creator_id=creator_id,
        title=video.title,
        duration_sec=video.duration_sec,
        likes=video.likes,
        plays=video.plays,
        comments=video.comments,
        shares=0,
        collects=0,
        published_at=video.published_at,
        cover_url=video.cover_url,
        source_url=video.source_url,
        updated_at=now,
    )
    s.add(row)
    return row


async def resolve_youtube_channel_for_url(url: str) -> YouTubeChannelInfo:
    return await resolve_channel(url)


async def _create_auto_tasks(s: AsyncSession, videos: Sequence[Video]) -> list[Task]:
    if not settings.creator_auto_task_enabled:
        return []
    return await create_auto_tasks_for_videos(
        s,
        videos,
        limit=settings.creator_auto_task_recent_count,
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
    if stale_ids:
        await s.execute(delete(Video).where(Video.id.in_(stale_ids)))
