from __future__ import annotations

from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voxpress.models import Article, Task, Video


def latest_videos(videos: Iterable[Video], *, limit: int) -> list[Video]:
    if limit <= 0:
        return []
    unique: dict[str, Video] = {}
    for video in videos:
        unique.setdefault(video.id, video)
    return sorted(
        unique.values(),
        key=lambda video: (video.published_at, video.id),
        reverse=True,
    )[:limit]


async def create_auto_tasks_for_videos(
    s: AsyncSession,
    videos: Sequence[Video],
    *,
    limit: int,
) -> list[Task]:
    candidates = latest_videos(videos, limit=limit)
    if not candidates:
        return []

    video_ids = [video.id for video in candidates]
    source_urls = [video.source_url for video in candidates]
    existing_video_ids = set(
        (
            await s.scalars(
                select(Task.video_id).where(Task.video_id.in_(video_ids))
            )
        ).all()
    )
    existing_source_urls = set(
        (
            await s.scalars(
                select(Task.source_url).where(Task.source_url.in_(source_urls))
            )
        ).all()
    )
    article_video_ids = set(
        (
            await s.scalars(
                select(Article.video_id).where(Article.video_id.in_(video_ids))
            )
        ).all()
    )

    created: list[Task] = []
    for video in candidates:
        if video.id in existing_video_ids or video.id in article_video_ids:
            continue
        if video.source_url in existing_source_urls:
            continue
        task = Task(
            source_url=video.source_url,
            title_guess=video.title,
            creator_id=video.creator_id,
            video_id=video.id,
            trigger_kind="auto",
            stage="download",
            progress=0,
            detail="自动转译 · 新作品入库后创建",
        )
        s.add(task)
        created.append(task)
        existing_video_ids.add(video.id)
        existing_source_urls.add(video.source_url)

    if created:
        await s.flush()
    return created
