from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from voxpress.db import get_session
from voxpress.errors import CreatorNotFound
from voxpress.models import Article, Creator
from voxpress.schemas import CreatorOut, Page, ResolveCreatorIn
from voxpress.url_resolve import normalize_douyin_input

router = APIRouter(prefix="/api/creators", tags=["creators"])


def _creator_list_stmt():
    """Base SELECT of (Creator, article_count) via LEFT JOIN GROUP BY.

    One round-trip, no N+1 when the list grows."""
    return (
        select(Creator, func.count(Article.id).label("article_count"))
        .outerjoin(Article, Article.creator_id == Creator.id)
        .group_by(Creator.id)
    )


@router.get("", response_model=Page[CreatorOut])
async def list_creators(
    s: AsyncSession = Depends(get_session),
    sort: str = Query("followers:desc"),
    q: str | None = None,
    verified: int | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(1000, ge=1, le=1000),
    offset: int | None = Query(None, ge=0),
    cursor: str | None = None,  # noqa: ARG001  (cursor reserved for future keyset pagination)
) -> Page[CreatorOut]:
    stmt = _creator_list_stmt()
    total_stmt = select(func.count()).select_from(Creator)
    if q:
        like = f"%{q}%"
        predicate = Creator.name.ilike(like) | Creator.handle.ilike(like) | Creator.bio.ilike(like)
        stmt = stmt.where(predicate)
        total_stmt = total_stmt.where(predicate)
    if verified == 1:
        predicate = Creator.verified.is_(True)
        stmt = stmt.where(predicate)
        total_stmt = total_stmt.where(predicate)
    if sort == "followers:desc":
        stmt = stmt.order_by(Creator.followers.desc())
    resolved_offset = offset if offset is not None else max(0, (page - 1) * limit)
    stmt = stmt.offset(resolved_offset).limit(limit)

    rows = (await s.execute(stmt)).all()
    items = [CreatorOut.from_model(c, article_count=int(count)) for c, count in rows]
    total = await s.scalar(total_stmt)
    return Page(items=items, cursor=None, total=total or 0)


@router.get("/{creator_id}", response_model=CreatorOut)
async def get_creator(creator_id: int, s: AsyncSession = Depends(get_session)) -> CreatorOut:
    row = (
        await s.execute(_creator_list_stmt().where(Creator.id == creator_id))
    ).one_or_none()
    if row is None:
        raise CreatorNotFound(f"creator {creator_id} not found")
    creator, count = row
    return CreatorOut.from_model(creator, article_count=int(count))


@router.post("/resolve", response_model=CreatorOut)
async def resolve_creator(
    payload: ResolveCreatorIn, s: AsyncSession = Depends(get_session)
) -> CreatorOut:
    """MVP: if any creator matches handle fragment in URL, return it; else pick first creator as stub."""
    url = normalize_douyin_input(payload.url)
    matched_id: int | None = None
    if "/user/" in url:
        suffix = url.rsplit("/user/", 1)[-1].split("?")[0][:32]
        if suffix:
            matched_id = await s.scalar(
                select(Creator.id).where(Creator.external_id == suffix)
            )
    if matched_id is None:
        matched_id = await s.scalar(select(Creator.id).order_by(Creator.id.asc()).limit(1))
    if matched_id is None:
        raise CreatorNotFound("尚无任何来源,请先导入")
    return await get_creator(matched_id, s)
