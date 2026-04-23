from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from voxpress.db import get_session
from voxpress.errors import CreatorNotFound, NotFound
from voxpress.media_store import MediaStoreError, media_store
from voxpress.models import Article, Creator, Video
from voxpress.schemas import Page, VideoOut, VideoSummaryOut

router = APIRouter(prefix="/api", tags=["videos"])


def _video_filters(
    *,
    creator_id: int,
    min_dur: int,
    min_likes: int,
    since: str | None,
    q: str | None,
    status: str | None,
) -> list:
    clauses: list = [Video.creator_id == creator_id]
    if min_dur:
        clauses.append(Video.duration_sec >= min_dur)
    if min_likes:
        clauses.append(Video.likes >= min_likes)
    if since and since.endswith("d"):
        try:
            days = int(since[:-1])
        except ValueError:
            days = 0
        if days > 0:
            clauses.append(Video.published_at >= datetime.now(tz=timezone.utc) - timedelta(days=days))
    if q:
        like = f"%{q}%"
        clauses.append(or_(Video.title.ilike(like), Video.id.ilike(like)))
    article_exists = exists(select(Article.id).where(Article.video_id == Video.id))
    if status == "organized":
        clauses.append(article_exists)
    elif status == "pending":
        clauses.append(~article_exists)
    return clauses


@router.get("/creators/{creator_id}/videos", response_model=Page[VideoOut])
async def list_videos(
    creator_id: int,
    s: AsyncSession = Depends(get_session),
    min_dur: int = Query(0),
    min_likes: int = Query(0),
    since: str | None = Query(None, description="30d / 7d / null"),
    q: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(40, ge=1, le=200),
    offset: int | None = Query(None, ge=0),
    cursor: str | None = None,  # noqa: ARG001
) -> Page[VideoOut]:
    creator = await s.get(Creator, creator_id)
    if not creator:
        raise CreatorNotFound(f"creator {creator_id} not found")

    clauses = _video_filters(
        creator_id=creator_id,
        min_dur=min_dur,
        min_likes=min_likes,
        since=since,
        q=q,
        status=status,
    )
    resolved_offset = offset if offset is not None else max(0, (page - 1) * limit)
    stmt = (
        select(Video)
        .where(*clauses)
        .order_by(Video.published_at.desc(), Video.id.desc())
        .offset(resolved_offset)
        .limit(limit)
    )

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
        items.append(VideoOut.from_model(v, article_id=article_by_video.get(v.id)))
    total = await s.scalar(select(func.count()).select_from(Video).where(*clauses))
    return Page(items=items, cursor=None, total=total or 0)


@router.get("/creators/{creator_id}/videos/summary", response_model=VideoSummaryOut)
async def summarize_videos(
    creator_id: int,
    s: AsyncSession = Depends(get_session),
    min_dur: int = Query(0),
    min_likes: int = Query(0),
    since: str | None = Query(None, description="30d / 7d / null"),
    q: str | None = Query(None),
) -> VideoSummaryOut:
    creator = await s.get(Creator, creator_id)
    if not creator:
        raise CreatorNotFound(f"creator {creator_id} not found")

    base_clauses = _video_filters(
        creator_id=creator_id,
        min_dur=min_dur,
        min_likes=min_likes,
        since=since,
        q=q,
        status=None,
    )
    total = int(await s.scalar(select(func.count()).select_from(Video).where(*base_clauses)) or 0)
    organized = int(
        await s.scalar(
            select(func.count())
            .select_from(Video)
            .where(
                *_video_filters(
                    creator_id=creator_id,
                    min_dur=min_dur,
                    min_likes=min_likes,
                    since=since,
                    q=q,
                    status="organized",
                )
            )
        )
        or 0
    )
    pending = int(
        await s.scalar(
            select(func.count())
            .select_from(Video)
            .where(
                *_video_filters(
                    creator_id=creator_id,
                    min_dur=min_dur,
                    min_likes=min_likes,
                    since=since,
                    q=q,
                    status="pending",
                )
            )
        )
        or 0
    )
    return VideoSummaryOut(total=total, organized=organized, pending=pending)


@router.get("/videos/{video_id}/media")
async def get_video_media(video_id: str, s: AsyncSession = Depends(get_session)) -> RedirectResponse:
    video = await s.get(Video, video_id)
    if not video or not video.media_object_key:
        raise NotFound("视频尚未归档到媒体存储")
    if not await media_store.is_enabled():
        raise NotFound("媒体存储尚未配置")
    try:
        signed = await media_store.sign_url(video.media_object_key)
    except MediaStoreError as e:
        raise NotFound(str(e)) from e
    return RedirectResponse(signed, status_code=307)
