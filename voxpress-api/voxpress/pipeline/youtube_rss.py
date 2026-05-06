from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from xml.etree import ElementTree

import httpx

from voxpress.pipeline.youtube_url import youtube_video_pk

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}


class YouTubeRssError(RuntimeError):
    pass


@dataclass(frozen=True)
class YouTubeRssVideo:
    id: str
    external_id: str
    title: str
    source_url: str
    published_at: datetime


async def fetch_channel_feed(
    channel_id: str,
    *,
    timeout: float = 12.0,
    max_videos: int | None = None,
) -> list[YouTubeRssVideo]:
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            r = await client.get(
                "https://www.youtube.com/feeds/videos.xml",
                params={"channel_id": channel_id},
            )
            r.raise_for_status()
    except httpx.HTTPError as exc:
        raise YouTubeRssError(f"YouTube RSS 请求失败:{exc}") from exc

    try:
        root = ElementTree.fromstring(r.text)
    except ElementTree.ParseError as exc:
        raise YouTubeRssError("YouTube RSS 解析失败") from exc

    videos: list[YouTubeRssVideo] = []
    for entry in root.findall("atom:entry", _ATOM_NS):
        video_id = _text(entry, "yt:videoId")
        if not video_id:
            continue
        title = _text(entry, "atom:title") or f"YouTube 视频 {video_id}"
        link = entry.find("atom:link", _ATOM_NS)
        href = link.attrib.get("href") if link is not None else None
        published_raw = _text(entry, "atom:published") or _text(entry, "atom:updated")
        published_at = _parse_datetime(published_raw)
        videos.append(
            YouTubeRssVideo(
                id=youtube_video_pk(video_id),
                external_id=video_id,
                title=title,
                source_url=href or f"https://www.youtube.com/watch?v={video_id}",
                published_at=published_at,
            )
        )
        if max_videos is not None and len(videos) >= max_videos:
            break
    return videos


def _text(node: ElementTree.Element, path: str) -> str | None:
    found = node.find(path, _ATOM_NS)
    if found is None or found.text is None:
        return None
    value = found.text.strip()
    return value or None


def _parse_datetime(value: str | None) -> datetime:
    if value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(tz=timezone.utc)
