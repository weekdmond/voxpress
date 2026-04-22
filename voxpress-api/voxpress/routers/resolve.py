"""Single-entry URL dispatcher used by the home-page submit box.

Frontend POSTs any douyin URL — short, video, or creator profile — and we
decide what to do with it server-side. Returns either a kicked-off task
(`kind: "video"`) or a creator id the UI should navigate to (`kind:
"creator"`).

Creator flow: f2 (signed web-API scraper) pulls real profile + video list.
Video flow: yt-dlp handles the download when the task runs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from voxpress.creator_sync import fetch_creator_page, load_cookie_text, upsert_scraped_page
from voxpress.db import get_session
from voxpress.errors import ApiError, InvalidUrl
from voxpress.models import Task
from voxpress.pipeline.douyin_scraper import ScrapeError
from voxpress.schemas import ResolveIn
from voxpress.task_store import emit_task_create
from voxpress.url_resolve import UnknownDouyinLink, resolve


class ScrapeFailed(ApiError):
    status_code = 502
    code = "scrape_failed"


router = APIRouter(prefix="/api", tags=["resolve"])


@router.post("/resolve")
async def resolve_link(
    payload: ResolveIn, s: AsyncSession = Depends(get_session)
) -> dict:
    url = payload.url.strip()
    if not url:
        raise InvalidUrl("链接不能为空")
    try:
        info = await resolve(url)
    except UnknownDouyinLink as e:
        raise InvalidUrl(str(e)) from e

    if info.kind == "video":
        task = Task(source_url=info.canonical_url, trigger_kind="manual")
        s.add(task)
        await s.commit()
        await s.refresh(task)
        await emit_task_create(task.id)
        return {"kind": "video", "task_id": str(task.id)}

    # Creator: scrape via f2 (signs Douyin's web API with ms_token/a_bogus).
    assert info.external_id, "classifier should always produce sec_uid for creators"
    cookie = await _load_cookie_text(s)
    try:
        scraped = await fetch_creator_page(info.external_id, cookie_text=cookie)
    except ScrapeError as e:
        raise ScrapeFailed(str(e)) from e

    creator = await upsert_scraped_page(s, scraped, prune_missing=True)
    await s.commit()
    return {
        "kind": "creator",
        "creator_id": creator.id,
        "name": creator.name,
        "video_count": creator.video_count,
        "fetched_video_count": len(scraped.videos),
    }


async def _load_cookie_text(s: AsyncSession) -> str | None:
    return await load_cookie_text(s)
