from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse, Response

from voxpress.errors import ApiError, InvalidUrl
from voxpress.media_store import MediaStoreError, media_store

router = APIRouter(prefix="/api/media", tags=["media"])
logger = logging.getLogger(__name__)

_ALLOWED_IMAGE_HOSTS = ("douyinpic.com",)


class MediaFetchFailed(ApiError):
    status_code = 502
    code = "media_fetch_failed"


def _is_allowed_host(hostname: str) -> bool:
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in _ALLOWED_IMAGE_HOSTS)


@router.get("")
async def proxy_media(url: str = Query(min_length=1)) -> Response:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise InvalidUrl("不支持的媒体地址")
    if not _is_allowed_host(parsed.hostname.lower()):
        raise InvalidUrl("当前只支持抖音图片地址")

    if await media_store.is_enabled():
        try:
            object_key = await media_store.cache_remote_image(url)
            if object_key:
                signed = await media_store.sign_url(object_key)
                return RedirectResponse(signed, status_code=307)
        except MediaStoreError:
            logger.warning("media cache to oss failed for %s", url, exc_info=True)

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
            res = await client.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Referer": "https://www.douyin.com/",
                },
            )
            res.raise_for_status()
    except httpx.HTTPError as e:
        raise MediaFetchFailed("拉取远程图片失败") from e

    media_type = (res.headers.get("content-type") or "image/jpeg").split(";", 1)[0]
    return Response(
        content=res.content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )
