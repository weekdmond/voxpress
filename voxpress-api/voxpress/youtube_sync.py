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
    probe_video,
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
            videos = _merge_rss_video_metadata(channel, videos, rss_videos)

    videos = await _enrich_lightweight_youtube_videos(videos)
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
        creator.video_count = max(channel.video_count, len(videos))
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


async def refresh_youtube_channel_by_id(
    channel_id: str,
    *,
    max_videos: int | None,
    prune_missing: bool = False,
) -> tuple[Creator, int, list[UUID]]:
    """Refresh a known YouTube source from RSS without re-parsing the channel page."""
    rss_videos = await fetch_channel_feed(channel_id, max_videos=max_videos)
    async with session_scope() as s:
        existing = await s.scalar(
            select(Creator).where(
                Creator.platform == "youtube",
                Creator.external_id == channel_id,
            )
        )
        if existing is None:
            raise RuntimeError(f"YouTube 来源不存在:{channel_id}")
        channel = YouTubeChannelInfo(
            channel_id=existing.external_id,
            handle=existing.handle,
            name=existing.name,
            bio=existing.bio,
            region=existing.region,
            avatar_url=existing.avatar_url,
            followers=existing.followers,
            video_count=existing.video_count,
        )
        videos = _videos_from_rss(channel, rss_videos)
        existing_rows = (
            await s.execute(
                select(Video.id, Video.duration_sec, Video.likes, Video.plays).where(
                    Video.id.in_([video.id for video in videos])
                )
            )
        ).all()
        missing_metadata_ids = _videos_requiring_metadata_probe(videos, existing_rows)
        videos = await _enrich_lightweight_youtube_videos(videos, probe_ids=missing_metadata_ids)
        creator = await upsert_youtube_channel(s, channel)
        await s.flush()
        new_videos: list[Video] = []
        for item in videos:
            new_video = await upsert_youtube_video(s, creator.id, item)
            if new_video is not None:
                new_videos.append(new_video)
        if prune_missing:
            await _prune_stale_videos(s, creator.id, [item.id for item in videos])
        creator.video_count = max(channel.video_count, len(videos))
        tasks = await _create_auto_tasks(s, new_videos)
        task_ids = [task.id for task in tasks]
        await s.flush()
        creator_id = creator.id

    for task_id in task_ids:
        await emit_task_create(task_id)

    async with session_scope() as s:
        stored_creator = await s.get(Creator, creator_id)
        if stored_creator is None:
            raise RuntimeError(f"YouTube creator {creator_id} missing after refresh")
        return stored_creator, len(videos), task_ids


def _videos_from_rss(channel: YouTubeChannelInfo, rss_videos: Sequence) -> list[YouTubeVideoInfo]:
    return [
        YouTubeVideoInfo(
            id=item.id,
            external_id=item.external_id,
            title=item.title,
            duration_sec=0,
            plays=0,
            likes=0,
            comments=0,
            cover_url=f"https://i.ytimg.com/vi/{item.external_id}/hqdefault.jpg",
            source_url=item.source_url,
            published_at=item.published_at,
            channel=channel,
        )
        for item in rss_videos
    ]


def _merge_rss_video_metadata(
    channel: YouTubeChannelInfo,
    videos: Sequence[YouTubeVideoInfo],
    rss_videos: Sequence,
) -> list[YouTubeVideoInfo]:
    """Prefer RSS publication dates while preserving richer yt-dlp metadata."""
    by_id = {video.id: video for video in videos}
    for rss_video in rss_videos:
        existing = by_id.get(rss_video.id)
        if existing is None:
            by_id[rss_video.id] = YouTubeVideoInfo(
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
            continue
        by_id[rss_video.id] = YouTubeVideoInfo(
            id=existing.id,
            external_id=existing.external_id or rss_video.external_id,
            title=existing.title or rss_video.title,
            duration_sec=existing.duration_sec,
            plays=existing.plays,
            likes=existing.likes,
            comments=existing.comments,
            cover_url=existing.cover_url or f"https://i.ytimg.com/vi/{rss_video.external_id}/hqdefault.jpg",
            source_url=existing.source_url or rss_video.source_url,
            published_at=rss_video.published_at,
            channel=existing.channel or channel,
        )
    return sorted(by_id.values(), key=lambda item: item.published_at, reverse=True)


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
        existing.bio = channel.bio or existing.bio
        existing.region = channel.region or existing.region
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
        bio=channel.bio,
        region=channel.region,
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
        published_at = existing.published_at if _looks_like_refresh_timestamp(video.published_at, now) else video.published_at
        existing.creator_id = creator_id
        existing.title = video.title
        existing.duration_sec = video.duration_sec or existing.duration_sec
        existing.likes = max(existing.likes or 0, video.likes or 0)
        existing.plays = max(existing.plays or 0, video.plays or 0)
        existing.comments = max(existing.comments or 0, video.comments or 0)
        existing.cover_url = video.cover_url or existing.cover_url
        existing.source_url = video.source_url
        existing.published_at = published_at
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


def _videos_requiring_metadata_probe(videos: Sequence[YouTubeVideoInfo], existing_rows: Sequence) -> set[str]:
    probe_ids = {video.id for video in videos}
    for video_id, duration_sec, likes, plays in existing_rows:
        if duration_sec or likes or plays:
            probe_ids.discard(video_id)
    return probe_ids


async def _enrich_lightweight_youtube_videos(
    videos: Sequence[YouTubeVideoInfo],
    *,
    probe_ids: set[str] | None = None,
) -> list[YouTubeVideoInfo]:
    enriched: list[YouTubeVideoInfo] = []
    for video in videos:
        if probe_ids is not None and video.id not in probe_ids:
            enriched.append(video)
            continue
        if video.duration_sec or video.likes or video.plays:
            enriched.append(video)
            continue
        try:
            probed = await probe_video(video.source_url)
        except Exception:
            enriched.append(video)
            continue
        enriched.append(
            YouTubeVideoInfo(
                id=probed.id or video.id,
                external_id=probed.external_id or video.external_id,
                title=probed.title or video.title,
                duration_sec=probed.duration_sec or video.duration_sec,
                plays=probed.plays or video.plays,
                likes=probed.likes or video.likes,
                comments=probed.comments or video.comments,
                cover_url=probed.cover_url or video.cover_url,
                source_url=probed.source_url or video.source_url,
                published_at=video.published_at,
                channel=video.channel,
            )
        )
    return enriched


def _looks_like_refresh_timestamp(value: datetime, now: datetime) -> bool:
    value_utc = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return abs((now - value_utc).total_seconds()) <= 600


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
