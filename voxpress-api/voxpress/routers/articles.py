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
from voxpress.markdown import md_to_html, strip_background_notes_md, word_count_cn
from voxpress.models import Article, Creator, Task, Transcript, Video
from voxpress.schemas import (
    ArticleBatchIn,
    ArticleBatchOut,
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
    total_stmt = select(func.count()).select_from(Article)
    if q:
        like = f"%{q}%"
        predicate = Article.title.ilike(like) | Article.summary.ilike(like) | Article.content_md.ilike(like)
        stmt = stmt.where(predicate)
        total_stmt = total_stmt.where(predicate)
    if creator_id:
        predicate = Article.creator_id == creator_id
        stmt = stmt.where(predicate)
        total_stmt = total_stmt.where(predicate)
    if tag:
        predicate = Article.tags.any(tag)
        stmt = stmt.where(predicate)
        total_stmt = total_stmt.where(predicate)
    if since and since.endswith("d"):
        try:
            days = int(since[:-1])
        except ValueError:
            days = 0
        if days > 0:
            predicate = Article.published_at >= datetime.now(tz=timezone.utc) - timedelta(days=days)
            stmt = stmt.where(predicate)
            total_stmt = total_stmt.where(predicate)
    stmt = stmt.order_by(Article.published_at.desc()).limit(limit)

    items = (await s.scalars(stmt)).all()
    videos = (
        await s.scalars(select(Video).where(Video.id.in_([article.video_id for article in items])))
        if items
        else []
    )
    video_map = {video.id: video for video in videos}
    total = await s.scalar(total_stmt)
    return Page(
        items=[
            ArticleOut.model_validate(a).model_copy(
                update={"cover_url": video_map.get(a.video_id).cover_url if video_map.get(a.video_id) else None}
            )
            for a in items
        ],
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
    transcript = await s.get(Transcript, art.video_id)
    if not creator or not video:
        raise NotFound("article references missing creator/video")

    source = ArticleSource(
        platform="douyin",
        source_url=video.source_url,
        media_url=f"/api/videos/{video.id}/media" if video.media_object_key else None,
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
            "avatar_url": creator.avatar_url,
            "followers": creator.followers,
            "verified": creator.verified,
            "region": creator.region,
        },
    )
    base = ArticleOut.model_validate(art).model_dump()
    base["cover_url"] = video.cover_url
    clean_md = strip_background_notes_md(base.get("content_md") or "")
    base["content_md"] = clean_md
    base["content_html"] = md_to_html(clean_md)
    base["word_count"] = word_count_cn(clean_md)
    return ArticleDetailOut(
        **base,
        source=source,
        segments=[TranscriptSegmentOut(ts_sec=seg.ts_sec, text=seg.text) for seg in art.segments],
        raw_text=transcript.raw_text if transcript else None,
        corrected_text=transcript.corrected_text if transcript else None,
        correction_status=transcript.correction_status if transcript else None,
        corrections=list(transcript.corrections or []) if transcript and transcript.corrections else [],
        whisper_model=transcript.whisper_model if transcript else None,
        whisper_language=transcript.whisper_language if transcript else None,
        corrector_model=transcript.corrector_model if transcript else None,
        initial_prompt_used=transcript.initial_prompt_used if transcript else None,
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
        final_md = strip_background_notes_md(payload.content_md)
        art.content_md = final_md
        art.content_html = md_to_html(final_md)
        art.word_count = word_count_cn(final_md)
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


@router.post("/batch/rebuild", response_model=ArticleBatchOut)
async def rebuild_articles_batch(
    payload: ArticleBatchIn,
    s: AsyncSession = Depends(get_session),
) -> ArticleBatchOut:
    from voxpress.task_store import emit_task_create

    ids = payload.article_ids
    rows = (
        await s.scalars(select(Article).where(Article.id.in_(ids)).order_by(Article.published_at.desc()))
    ).all()
    article_map = {article.id: article for article in rows}
    matched = list(article_map.values())
    task_ids: list[UUID] = []

    for article in matched:
        video = await s.get(Video, article.video_id)
        if not video:
            continue
        task = Task(
            source_url=video.source_url,
            title_guess=article.title,
            creator_id=article.creator_id,
            video_id=video.id,
            trigger_kind="rerun",
            rerun_of_task_id=None,
            resume_from_stage="organize",
            stage="organize",
            progress=72,
            detail="等待重跑 · 从整理开始",
        )
        s.add(task)
        await s.flush()
        task_ids.append(task.id)

    await s.commit()
    for task_id in task_ids:
        await emit_task_create(task_id)

    missing_ids = [article_id for article_id in ids if article_id not in article_map]
    return ArticleBatchOut(
        requested=len(ids),
        matched=len(matched),
        processed=len(task_ids),
        task_ids=task_ids,
        missing_ids=missing_ids,
    )


@router.post("/batch/delete", response_model=ArticleBatchOut)
async def delete_articles_batch(
    payload: ArticleBatchIn,
    s: AsyncSession = Depends(get_session),
) -> ArticleBatchOut:
    ids = payload.article_ids
    rows = (await s.scalars(select(Article).where(Article.id.in_(ids)))).all()
    article_map = {article.id: article for article in rows}

    for article in article_map.values():
        await s.delete(article)

    await s.commit()

    missing_ids = [article_id for article_id in ids if article_id not in article_map]
    return ArticleBatchOut(
        requested=len(ids),
        matched=len(article_map),
        processed=len(article_map),
        missing_ids=missing_ids,
    )


@router.post("/{article_id}/rebuild")
async def rebuild_article(article_id: UUID, s: AsyncSession = Depends(get_session)) -> dict:
    from voxpress.task_store import emit_task_create

    art = await s.get(Article, article_id)
    if not art:
        raise NotFound(f"article {article_id} not found")
    video = await s.get(Video, art.video_id)
    if not video:
        raise NotFound("source video missing")
    task = Task(
        source_url=video.source_url,
        title_guess=art.title,
        creator_id=art.creator_id,
        video_id=video.id,
        trigger_kind="rerun",
        rerun_of_task_id=None,
        resume_from_stage="organize",
        stage="organize",
        progress=72,
        detail="等待重跑 · 从整理开始",
    )
    s.add(task)
    await s.commit()
    await s.refresh(task)
    await emit_task_create(task.id)
    return {"task_id": str(task.id)}


@router.get("/{article_id}/export.md")
async def export_markdown(article_id: UUID, s: AsyncSession = Depends(get_session)) -> Response:
    art = await s.get(Article, article_id)
    if not art:
        raise NotFound(f"article {article_id} not found")
    body = strip_background_notes_md(art.content_md or "")
    return Response(
        content=body,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{art.id}.md"'},
    )
