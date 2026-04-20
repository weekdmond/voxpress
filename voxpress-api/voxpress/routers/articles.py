from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from voxpress.db import get_session
from voxpress.errors import NotFound
from voxpress.markdown import md_to_html, word_count_cn
from voxpress.models import Article, Creator, Task, Video
from voxpress.schemas import (
    ArticleDetailOut,
    ArticleOut,
    ArticlePatch,
    ArticleSource,
    Page,
    TranscriptSegmentOut,
)

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("", response_model=Page[ArticleOut])
async def list_articles(
    s: AsyncSession = Depends(get_session),
    q: str | None = None,
    creator_id: int | None = None,
    tag: str | None = None,
    since: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,  # noqa: ARG001
) -> Page[ArticleOut]:
    stmt = select(Article)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Article.title.ilike(like) | Article.content_md.ilike(like))
    if creator_id:
        stmt = stmt.where(Article.creator_id == creator_id)
    if tag:
        stmt = stmt.where(Article.tags.any(tag))
    if since == "30d":
        stmt = stmt.where(Article.published_at >= datetime.now(tz=timezone.utc) - timedelta(days=30))
    stmt = stmt.order_by(Article.published_at.desc()).limit(limit)

    items = (await s.scalars(stmt)).all()
    total = await s.scalar(select(func.count()).select_from(Article))
    return Page(
        items=[ArticleOut.model_validate(a) for a in items],
        cursor=None,
        total=total or 0,
    )


@router.get("/{article_id}", response_model=ArticleDetailOut)
async def get_article(article_id: UUID, s: AsyncSession = Depends(get_session)) -> ArticleDetailOut:
    stmt = (
        select(Article)
        .where(Article.id == article_id)
        .options(selectinload(Article.segments))
    )
    art = await s.scalar(stmt)
    if not art:
        raise NotFound(f"article {article_id} not found")

    creator = await s.get(Creator, art.creator_id)
    video = await s.get(Video, art.video_id)
    if not creator or not video:
        raise NotFound("article references missing creator/video")

    source = ArticleSource(
        platform="douyin",
        source_url=video.source_url,
        duration_sec=video.duration_sec,
        metrics={
            "likes": video.likes,
            "comments": video.comments,
            "shares": video.shares,
            "collects": video.collects,
            "plays": video.plays,
        },
        topics=list(art.tags),
        creator_snapshot={
            "name": creator.name,
            "handle": creator.handle,
            "followers": creator.followers,
            "verified": creator.verified,
            "region": creator.region,
        },
    )
    base = ArticleOut.model_validate(art).model_dump()
    return ArticleDetailOut(
        **base,
        source=source,
        segments=[TranscriptSegmentOut(ts_sec=seg.ts_sec, text=seg.text) for seg in art.segments],
    )


@router.patch("/{article_id}", response_model=ArticleOut)
async def patch_article(
    article_id: UUID,
    payload: ArticlePatch,
    s: AsyncSession = Depends(get_session),
) -> ArticleOut:
    art = await s.get(Article, article_id)
    if not art:
        raise NotFound(f"article {article_id} not found")
    if payload.title is not None:
        art.title = payload.title
    if payload.tags is not None:
        art.tags = payload.tags
    if payload.content_md is not None:
        art.content_md = payload.content_md
        art.content_html = md_to_html(payload.content_md)
        art.word_count = word_count_cn(payload.content_md)
    await s.commit()
    return ArticleOut.model_validate(art)


@router.delete("/{article_id}", status_code=204)
async def delete_article(article_id: UUID, s: AsyncSession = Depends(get_session)) -> Response:
    art = await s.get(Article, article_id)
    if not art:
        raise NotFound(f"article {article_id} not found")
    await s.delete(art)
    await s.commit()
    return Response(status_code=204)


@router.post("/{article_id}/rebuild")
async def rebuild_article(article_id: UUID, s: AsyncSession = Depends(get_session)) -> dict:
    from voxpress.pipeline import runner

    art = await s.get(Article, article_id)
    if not art:
        raise NotFound(f"article {article_id} not found")
    video = await s.get(Video, art.video_id)
    if not video:
        raise NotFound("source video missing")
    task = Task(source_url=video.source_url, title_guess=art.title, creator_id=art.creator_id)
    s.add(task)
    await s.commit()
    await s.refresh(task)
    creator = await s.get(Creator, task.creator_id) if task.creator_id else None
    await runner.enqueue(task, creator)
    return {"task_id": str(task.id)}


@router.get("/{article_id}/export.md")
async def export_markdown(article_id: UUID, s: AsyncSession = Depends(get_session)) -> Response:
    art = await s.get(Article, article_id)
    if not art:
        raise NotFound(f"article {article_id} not found")
    body = art.content_md or ""
    return Response(
        content=body,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{art.id}.md"'},
    )
