from __future__ import annotations

from dataclasses import dataclass

import httpx

from voxpress.pipeline.youtube_url import resolve_youtube_url, youtube_video_pk

_OEMBED_URL = "https://www.youtube.com/oembed"


class YouTubeOEmbedError(RuntimeError):
    pass


@dataclass(frozen=True)
class YouTubeOEmbedVideo:
    video_id: str
    title: str
    author_name: str
    author_url: str | None
    thumbnail_url: str | None
    source_url: str


async def fetch_oembed_video(url: str, *, timeout: float = 10.0) -> YouTubeOEmbedVideo:
    info = resolve_youtube_url(url)
    if info.kind != "video" or not info.external_id:
        raise YouTubeOEmbedError("oEmbed 仅支持 YouTube 单条视频链接")
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            r = await client.get(_OEMBED_URL, params={"url": info.canonical_url, "format": "json"})
            r.raise_for_status()
    except httpx.HTTPError as exc:
        raise YouTubeOEmbedError(f"YouTube oEmbed 请求失败:{exc}") from exc
    data = r.json()
    return YouTubeOEmbedVideo(
        video_id=youtube_video_pk(info.external_id),
        title=str(data.get("title") or info.external_id),
        author_name=str(data.get("author_name") or "YouTube"),
        author_url=data.get("author_url"),
        thumbnail_url=data.get("thumbnail_url"),
        source_url=info.canonical_url,
    )
