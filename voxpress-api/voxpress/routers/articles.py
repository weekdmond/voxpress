from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from voxpress.config import settings
from voxpress.db import get_session
from voxpress.errors import NotFound
from voxpress.markdown import md_to_html, strip_background_notes_md, word_count_cn
from voxpress.models import Article, Creator, Task, Transcript, Video
from voxpress.schemas import (
    ArticleBatchIn,
    ArticleBatchOut,
    ArticleDetailOut,
    ArticleClaudeShareOut,
    ArticleClaudeWritebackIn,
    ArticleClaudeWritebackOut,
    ArticleFacetItemOut,
    ArticleFacetsOut,
    ArticleOut,
    ArticlePatch,
    ArticleRebuildIn,
    ArticleShareIn,
    ArticleShareItemOut,
    ArticleSource,
    Page,
    TranscriptSegmentOut,
)

router = APIRouter(prefix="/api/articles", tags=["articles"])


def _latest_task_id_subquery(article_id_expr, video_id_expr):
    article_match_score = case((Task.article_id == article_id_expr, 1), else_=0)
    return (
        select(Task.id)
        .where(or_(Task.article_id == article_id_expr, Task.video_id == video_id_expr))
        .order_by(
            article_match_score.desc(),
            Task.started_at.desc().nulls_last(),
            Task.updated_at.desc().nulls_last(),
            Task.id.desc(),
        )
        .limit(1)
        .scalar_subquery()
    )


def _article_sort_order(sort: str) -> list[Any]:
    sort = sort or "published_at:desc"
    field, _, direction = sort.partition(":")
    desc = direction != "asc"
    expr = {
        "published_at": Article.published_at,
        "updated_at": Article.updated_at,
        "word_count": Article.word_count,
        "likes_snapshot": Article.likes_snapshot,
    }.get(field, Article.published_at)
    primary = expr.desc().nulls_last() if desc else expr.asc().nulls_last()
    tie_breaker = Article.id.desc() if desc else Article.id.asc()
    return [primary, tie_breaker]


def _article_filter_predicates(
    *,
    q: str | None = None,
    creator_id: int | None = None,
    tag: str | None = None,
    topic: str | None = None,
    since: str | None = None,
    include_tag: bool = True,
    include_topic: bool = True,
) -> list[Any]:
    predicates: list[Any] = []
    if q:
        like = f"%{q}%"
        predicates.append(
            Article.title.ilike(like) | Article.summary.ilike(like) | Article.content_md.ilike(like)
        )
    if creator_id:
        predicates.append(Article.creator_id == creator_id)
    if include_tag and tag:
        predicates.append(Article.tags.any(tag))
    if include_topic and topic:
        predicates.append(Article.topics.any(topic))
    if since and since.endswith("d"):
        try:
            days = int(since[:-1])
        except ValueError:
            days = 0
        if days > 0:
            predicates.append(Article.published_at >= datetime.now(tz=timezone.utc) - timedelta(days=days))
    return predicates


async def _array_facets(
    s: AsyncSession,
    column,
    *,
    predicates: list[Any],
    limit: int,
) -> list[ArticleFacetItemOut]:
    value = func.unnest(column).label("value")
    count = func.count().label("count")
    stmt = (
        select(value, count)
        .select_from(Article)
        .where(*predicates)
        .group_by(value)
        .order_by(count.desc(), value.asc())
        .limit(limit)
    )
    rows = (await s.execute(stmt)).all()
    return [ArticleFacetItemOut(value=str(item), count=int(item_count)) for item, item_count in rows if item]


def _share_dir() -> Path:
    path = settings.audio_dir.parent / "shares"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cleanup_old_shares(path: Path) -> None:
    cutoff = datetime.now(tz=timezone.utc).timestamp() - 7 * 86_400
    for item in path.iterdir():
        if item.suffix not in {".md", ".json"}:
            continue
        try:
            if item.stat().st_mtime < cutoff:
                item.unlink()
        except OSError:
            continue


def _share_md_path(share_id: str) -> Path:
    return _share_dir() / f"{share_id}.md"


def _share_meta_path(share_id: str) -> Path:
    return _share_dir() / f"{share_id}.json"


def _write_share_metadata(share_id: str, *, file_name: str, article_ids: list[UUID]) -> None:
    _share_meta_path(share_id).write_text(
        json.dumps(
            {
                "file_name": file_name,
                "article_ids": [str(article_id) for article_id in article_ids],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _read_share_metadata(share_id: str) -> dict[str, Any] | None:
    meta_path = _share_meta_path(share_id)
    if not meta_path.exists() or not meta_path.is_file():
        return None
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_share_file_name(share_id: str) -> str | None:
    payload = _read_share_metadata(share_id)
    if payload is None:
        return None
    file_name = payload.get("file_name")
    return str(file_name) if isinstance(file_name, str) and file_name.endswith(".md") else None


def _extract_title_from_markdown(content_md: str) -> str | None:
    for raw_line in content_md.splitlines():
        line = raw_line.strip()
        if line.startswith("# "):
            title = line[2:].strip()
            return title or None
    return None


def _extract_summary_from_markdown(content_md: str) -> str | None:
    quote_lines: list[str] = []
    for raw_line in content_md.splitlines():
        line = raw_line.strip()
        if line.startswith(">"):
            quote_lines.append(line.lstrip(">").strip())
        elif quote_lines:
            break
    summary = " ".join(part for part in quote_lines if part).strip()
    return summary[:120] if summary else None


def _filename_slug(title: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", title.strip()).strip("-_")
    return (slug or "articles")[:48]


def _md_scalar(value: object | None) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _transcript_text(transcript: Transcript | None) -> tuple[str, str]:
    if not transcript:
        return "", "逐字稿"
    if transcript.corrected_text and transcript.corrected_text.strip():
        return transcript.corrected_text.strip(), "校正逐字稿"
    if transcript.raw_text and transcript.raw_text.strip():
        return transcript.raw_text.strip(), "原始逐字稿"
    segments = transcript.segments or []
    parts = [str(seg.get("text", "")).strip() for seg in segments if isinstance(seg, dict)]
    return "\n".join(part for part in parts if part), "逐字稿分段"


def _build_claude_bundle(
    rows: list[tuple[Article, Creator, Video, Transcript | None]],
    *,
    created_at: datetime,
) -> str:
    lines = [
        "# SpeechFolio Source Pack",
        "",
        f"- 导出时间: {created_at.isoformat()}",
        f"- 文章数量: {len(rows)}",
        "",
        "这份文件由 SpeechFolio 生成，供 Claude 读取多篇文章的原稿、来源和整理参考。",
        "",
    ]
    for idx, (article, creator, video, transcript) in enumerate(rows, start=1):
        transcript_body, transcript_label = _transcript_text(transcript)
        content_md = strip_background_notes_md(article.content_md or "").strip()
        lines.extend(
            [
                f"## {idx}. {article.title}",
                "",
                f"- 文章 ID: `{article.id}`",
                f"- 创作者: {creator.name} ({creator.handle})",
                f"- 来源链接: {video.source_url}",
                f"- 发布时间: {_md_scalar(article.published_at)}",
                f"- 主题: {', '.join(article.topics) if article.topics else '—'}",
                f"- 标签: {', '.join(article.tags) if article.tags else '—'}",
                f"- 摘要: {_md_scalar(article.summary)}",
                "",
            ]
        )
        if transcript_body:
            lines.extend([f"### {transcript_label}", "", transcript_body, ""])
        else:
            lines.extend(["### 逐字稿", "", "（当前文章暂无逐字稿，下面提供整理稿作为参考。）", ""])
        if content_md:
            lines.extend(["### SpeechFolio 当前整理稿（参考）", "", content_md, ""])
        lines.append("---")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


@router.post("/share/claude", response_model=ArticleClaudeShareOut)
async def create_claude_article_share(
    payload: ArticleShareIn,
    s: AsyncSession = Depends(get_session),
) -> ArticleClaudeShareOut:
    requested_ids = list(dict.fromkeys(payload.article_ids))
    rows = (
        await s.execute(
            select(Article, Creator, Video, Transcript)
            .join(Creator, Creator.id == Article.creator_id)
            .join(Video, Video.id == Article.video_id)
            .outerjoin(Transcript, Transcript.video_id == Article.video_id)
            .where(Article.id.in_(requested_ids))
        )
    ).all()
    row_map = {
        article.id: (article, creator, video, transcript)
        for article, creator, video, transcript in rows
    }
    ordered_rows = [row_map[article_id] for article_id in requested_ids if article_id in row_map]
    if not ordered_rows:
        raise NotFound("selected articles not found")

    created_at = datetime.now(tz=timezone.utc)
    share_id = uuid.uuid4().hex[:12]
    file_name = (
        f"speechfolio-source-pack-{created_at.strftime('%Y%m%d-%H%M%S')}-"
        f"{_filename_slug(ordered_rows[0][0].title)}-{share_id[:8]}.md"
    )
    share_path = _share_md_path(share_id)
    _cleanup_old_shares(share_path.parent)
    share_path.write_text(
        _build_claude_bundle(ordered_rows, created_at=created_at),
        encoding="utf-8",
    )
    _write_share_metadata(
        share_id,
        file_name=file_name,
        article_ids=[article.id for article, _, _, _ in ordered_rows],
    )
    missing_ids = [article_id for article_id in requested_ids if article_id not in row_map]
    return ArticleClaudeShareOut(
        share_id=share_id,
        file_name=file_name,
        article_count=len(ordered_rows),
        download_url=f"/api/articles/share/s/{share_id}",
        writeback_url=f"/api/articles/share/s/{share_id}/writeback",
        local_file_path=str(share_path),
        created_at=created_at,
        articles=[
            ArticleShareItemOut(id=article.id, title=article.title, creator_name=creator.name)
            for article, creator, _, _ in ordered_rows
        ],
        missing_ids=missing_ids,
    )


@router.get("/share/s/{share_id}")
async def download_claude_article_share_short(share_id: str) -> FileResponse:
    if not re.fullmatch(r"[0-9a-f]{12}", share_id):
        raise NotFound("share file not found")
    path = _share_md_path(share_id)
    if not path.exists() or not path.is_file():
        raise NotFound("share file not found")
    file_name = _read_share_file_name(share_id) or f"{share_id}.md"
    return FileResponse(
        path,
        media_type="text/markdown; charset=utf-8",
        filename=file_name,
    )


@router.post("/share/s/{share_id}/writeback", response_model=ArticleClaudeWritebackOut)
async def writeback_claude_article_share(
    share_id: str,
    payload: ArticleClaudeWritebackIn,
    s: AsyncSession = Depends(get_session),
) -> ArticleClaudeWritebackOut:
    if not re.fullmatch(r"[0-9a-f]{12}", share_id):
        raise NotFound("share file not found")
    meta = _read_share_metadata(share_id)
    if meta is None:
        raise NotFound("share file not found")
    allowed_ids = {
        UUID(raw_id)
        for raw_id in (meta.get("article_ids") or [])
        if isinstance(raw_id, str)
    }
    if not allowed_ids:
        raise NotFound("share file not found")

    requested_items = list(payload.articles)
    requested_ids = [item.id for item in requested_items]
    rows = (
        await s.execute(select(Article).where(Article.id.in_(requested_ids)))
    ).scalars().all()
    row_map = {article.id: article for article in rows if article.id in allowed_ids}

    updated_ids: list[UUID] = []
    missing_ids: list[UUID] = []
    for item in requested_items:
        article = row_map.get(item.id)
        if article is None:
            missing_ids.append(item.id)
            continue
        final_md = strip_background_notes_md(item.content_md).strip()
        if not final_md:
            missing_ids.append(item.id)
            continue
        title = (item.title or _extract_title_from_markdown(final_md) or article.title).strip()
        summary = (item.summary or _extract_summary_from_markdown(final_md) or article.summary).strip()
        tags = item.tags if item.tags is not None else article.tags
        article.title = title or article.title
        article.summary = summary
        article.content_md = final_md
        article.content_html = md_to_html(final_md)
        article.word_count = word_count_cn(final_md)
        article.tags = [str(tag)[:16] for tag in (tags or [])[:4]]
        updated_ids.append(article.id)

    await s.commit()
    return ArticleClaudeWritebackOut(
        share_id=share_id,
        requested=len(requested_items),
        updated=len(updated_ids),
        updated_ids=updated_ids,
        missing_ids=missing_ids,
    )


@router.get("/share/{file_name}")
async def download_claude_article_share(file_name: str) -> FileResponse:
    if "/" in file_name or "\\" in file_name or not file_name.endswith(".md"):
        raise NotFound("share file not found")
    path = _share_dir() / file_name
    if not path.exists() or not path.is_file():
        raise NotFound("share file not found")
    return FileResponse(
        path,
        media_type="text/markdown; charset=utf-8",
        filename=file_name,
    )


@router.get("/facets", response_model=ArticleFacetsOut)
async def article_facets(
    s: AsyncSession = Depends(get_session),
    q: str | None = None,
    creator_id: int | None = None,
    tag: str | None = None,
    topic: str | None = None,
    since: str | None = None,
    limit: int = Query(100, ge=1, le=200),
) -> ArticleFacetsOut:
    topic_predicates = _article_filter_predicates(
        q=q,
        creator_id=creator_id,
        tag=tag,
        topic=topic,
        since=since,
        include_topic=False,
    )
    tag_predicates = _article_filter_predicates(
        q=q,
        creator_id=creator_id,
        tag=tag,
        topic=topic,
        since=since,
        include_tag=False,
    )
    return ArticleFacetsOut(
        topics=await _array_facets(s, Article.topics, predicates=topic_predicates, limit=limit),
        tags=await _array_facets(s, Article.tags, predicates=tag_predicates, limit=limit),
    )


@router.get("", response_model=Page[ArticleOut])
async def list_articles(
    s: AsyncSession = Depends(get_session),
    sort: str = Query("published_at:desc"),
    q: str | None = None,
    creator_id: int | None = None,
    tag: str | None = None,
    topic: str | None = None,
    since: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Page[ArticleOut]:
    latest_task_id = _latest_task_id_subquery(Article.id, Article.video_id).label("latest_task_id")
    stmt = select(Article, latest_task_id)
    total_stmt = select(func.count()).select_from(Article)
    predicates = _article_filter_predicates(q=q, creator_id=creator_id, tag=tag, topic=topic, since=since)
    stmt = stmt.where(*predicates)
    total_stmt = total_stmt.where(*predicates)
    stmt = stmt.order_by(*_article_sort_order(sort)).offset(offset).limit(limit)

    rows = (await s.execute(stmt)).all()
    items = [article for article, _ in rows]
    latest_task_map = {article.id: task_id for article, task_id in rows}
    video_ids = [article.video_id for article in items]
    article_ids = [article.id for article in items]
    if items:
        videos = (await s.scalars(select(Video).where(Video.id.in_(video_ids)))).all()
        cost_rows = (
            await s.execute(
                select(Task.article_id, Task.cost_cny)
                .where(Task.article_id.in_(article_ids), Task.status == "done")
                .order_by(Task.article_id, Task.finished_at.desc().nulls_last())
                .distinct(Task.article_id)
            )
        ).all()
    else:
        videos = []
        cost_rows = []
    video_map = {video.id: video for video in videos}
    cost_map = {aid: float(cost or 0) for aid, cost in cost_rows}
    total = await s.scalar(total_stmt)
    return Page(
        items=[
            ArticleOut.model_validate(a).model_copy(
                update={
                    "latest_task_id": latest_task_map.get(a.id),
                    "cover_url": video_map[a.video_id].cover_url if a.video_id in video_map else None,
                    "duration_sec": video_map[a.video_id].duration_sec if a.video_id in video_map else 0,
                    "cost_cny": cost_map.get(a.id, 0.0),
                }
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
    latest_task_id = await s.scalar(
        select(Task.id)
        .where(or_(Task.article_id == art.id, Task.video_id == art.video_id))
        .order_by(
            case((Task.article_id == art.id, 1), else_=0).desc(),
            Task.started_at.desc().nulls_last(),
            Task.updated_at.desc().nulls_last(),
            Task.id.desc(),
        )
        .limit(1)
    )
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
        topics=list(art.topics or []),
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
    base["latest_task_id"] = latest_task_id
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
    if payload.topics is not None:
        art.topics = payload.topics
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


@router.post("/batch", response_model=ArticleBatchOut, deprecated=True)
async def create_articles_batch_compat(
    payload: dict,
    s: AsyncSession = Depends(get_session),
) -> ArticleBatchOut:
    """Backward-compatible video processing entrypoint.

    Older frontend code still posts selected `video_ids` to `/api/articles/batch`.
    The canonical route is now `/api/tasks/batch`, but keeping this alias avoids
    405s for stale clients and local cached bundles.
    """
    from voxpress.task_store import emit_task_create

    video_ids = list(payload.get("video_ids") or [])
    creator_id = payload.get("creator_id")
    rows_stmt = select(Video).where(Video.id.in_(video_ids))
    if creator_id is not None:
        rows_stmt = rows_stmt.where(Video.creator_id == creator_id)
    rows = (await s.scalars(rows_stmt)).all()
    video_map = {video.id: video for video in rows}
    task_ids: list[UUID] = []

    for video_id in video_ids:
        video = video_map.get(video_id)
        if not video:
            continue
        task = Task(
            source_url=video.source_url,
            title_guess=video.title,
            creator_id=video.creator_id,
            video_id=video.id,
            trigger_kind="batch",
            stage="download",
            progress=0,
            detail="等待调度",
        )
        s.add(task)
        await s.flush()
        task_ids.append(task.id)

    await s.commit()
    for task_id in task_ids:
        await emit_task_create(task_id)

    missing_ids = [video_id for video_id in video_ids if video_id not in video_map]
    return ArticleBatchOut(
        requested=len(video_ids),
        matched=len(video_map),
        processed=len(task_ids),
        task_ids=task_ids,
        missing_ids=missing_ids,
    )


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
            **(await _rebuild_start_kwargs(s, video, payload.from_stage)),
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
async def rebuild_article(
    article_id: UUID,
    payload: ArticleRebuildIn = Body(default_factory=ArticleRebuildIn),
    s: AsyncSession = Depends(get_session),
) -> dict:
    from voxpress.task_store import emit_task_create

    art = await s.get(Article, article_id)
    if not art:
        raise NotFound(f"article {article_id} not found")
    video = await s.get(Video, art.video_id)
    if not video:
        raise NotFound("source video missing")
    requested_stage = payload.from_stage
    task = Task(
        source_url=video.source_url,
        title_guess=art.title,
        creator_id=art.creator_id,
        video_id=video.id,
        trigger_kind="rerun",
        rerun_of_task_id=None,
        **(await _rebuild_start_kwargs(s, video, requested_stage)),
    )
    s.add(task)
    await s.commit()
    await s.refresh(task)
    await emit_task_create(task.id)
    return {"task_id": str(task.id)}


_REBUILD_STAGE_ORDER = ("download", "transcribe", "correct", "organize")
_REBUILD_STAGE_PROGRESS = {"download": 0, "transcribe": 20, "correct": 58, "organize": 72}
_REBUILD_STAGE_LABEL = {
    "download": "下载",
    "transcribe": "转写",
    "correct": "校对",
    "organize": "整理",
}


async def _rebuild_start_kwargs(
    s: AsyncSession,
    video: Video,
    requested: str | None = None,
) -> dict[str, object]:
    """Pick the starting stage for a rebuild, honoring the user's request when possible.

    - requested=None → auto: 有缓存从 transcribe,没缓存从 download
    - requested 明确给定 → 用它;若前置素材缺失,回退到最早能跑的阶段
    - 回退规则:organize/correct 需要已有 transcript.raw_text,transcribe 需要已缓存音视频
    整理质量依赖转写质量,所以 auto 仍然从 transcribe 起,而不是 organize。
    """
    has_media = bool(video.audio_object_key or video.media_object_key)
    transcript = await s.get(Transcript, video.id)
    has_raw = bool(transcript and transcript.raw_text)

    auto_stage = "transcribe" if has_media else "download"
    stage = requested if requested in _REBUILD_STAGE_ORDER else auto_stage

    if stage in {"organize", "correct"} and not has_raw:
        stage = auto_stage
    elif stage == "transcribe" and not has_media:
        stage = "download"

    fell_back = requested in _REBUILD_STAGE_ORDER and stage != requested
    base_detail = {
        "download": "等待重跑 · 从下载开始",
        "transcribe": "等待重跑 · 从转写开始(复用已缓存音视频)",
        "correct": "等待重跑 · 从校对开始(复用已有转写)",
        "organize": "等待重跑 · 从整理开始(复用已有转写)",
    }[stage]
    if fell_back:
        base_detail = f"{base_detail} · 回退自{_REBUILD_STAGE_LABEL[requested]}(素材不足)"

    return {
        "resume_from_stage": None if stage == "download" else stage,
        "stage": stage,
        "progress": _REBUILD_STAGE_PROGRESS[stage],
        "detail": base_detail,
    }


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
