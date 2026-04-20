from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from voxpress.db import get_session
from voxpress.errors import CreatorNotFound
from voxpress.models import Article, Creator, Video
from voxpress.schemas import Page, VideoOut

router = APIRouter(prefix="/api/creators", tags=["videos"])


@router.get("/{creator_id}/videos", response_model=Page[VideoOut])
async def list_videos(
    creator_id: int,
    s: AsyncSession = Depends(get_session),
    min_dur: int = Query(0),
    min_likes: int = Query(0),
    since: str | None = Query(None, description="30d / 7d / null"),
    cursor: str | None = None,  # noqa: ARG001
) -> Page[VideoOut]:
    creator = await s.get(Creator, creator_id)
    if not creator:
        raise CreatorNotFound(f"creator {creator_id} not found")

    stmt = select(Video).where(Video.creator_id == creator_id)
    if min_dur:
        stmt = stmt.where(Video.duration_sec >= min_dur)
    if min_likes:
        stmt = stmt.where(Video.likes >= min_likes)
    if since == "30d":
        stmt = stmt.where(Video.published_at >= datetime.now(tz=timezone.utc) - timedelta(days=30))
    stmt = stmt.order_by(Video.published_at.desc())

    videos = (await s.scalars(stmt)).all()

    # Map video_id -> article_id (real UUID string) in one query.
    if videos:
        art_rows = await s.execute(
            select(Article.video_id, Article.id).where(
                Article.video_id.in_([v.id for v in videos])
            )
        )
        article_by_video = {vid: str(aid) for vid, aid in art_rows.all()}
    else:
        article_by_video = {}

    items = []
    for v in videos:
        out = VideoOut.model_validate(v)
        out.article_id = article_by_video.get(v.id)
        items.append(out)
    total = await s.scalar(select(func.count()).where(Video.creator_id == creator_id))
    return Page(items=items, cursor=None, total=total or 0)
