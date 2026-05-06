from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, urlparse

Kind = Literal["video", "channel", "playlist"]

_TRAILING_URL_PUNCT = "。；，、！？）》】」』'\""
_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,}$")


class UnknownYouTubeLink(RuntimeError):
    pass


@dataclass(frozen=True)
class ResolvedYouTubeUrl:
    kind: Kind
    canonical_url: str
    external_id: str | None
    handle: str | None = None


def extract_youtube_url(text: str) -> str | None:
    raw = text.strip()
    if not raw:
        return None
    for candidate in re.findall(r"https?://[^\s]+", raw):
        cleaned = candidate.rstrip(_TRAILING_URL_PUNCT)
        if _is_youtube_host(urlparse(cleaned).netloc):
            return cleaned
    return None


def normalize_youtube_input(text: str) -> str:
    raw = text.strip()
    if not raw:
        return raw
    return extract_youtube_url(raw) or raw


def is_youtube_url(text: str) -> bool:
    url = normalize_youtube_input(text)
    return _is_youtube_host(urlparse(url).netloc)


def resolve_youtube_url(text: str) -> ResolvedYouTubeUrl:
    url = normalize_youtube_input(text)
    parsed = urlparse(url)
    if not _is_youtube_host(parsed.netloc):
        raise UnknownYouTubeLink(f"无法识别的 YouTube 链接:{text}")

    host = parsed.netloc.lower()
    path = parsed.path.strip("/")
    qs = parse_qs(parsed.query)

    if host == "youtu.be":
        video_id = path.split("/", 1)[0]
        return _video(video_id)

    if path == "watch":
        video_id = (qs.get("v") or [""])[0]
        return _video(video_id)

    if path.startswith("shorts/"):
        video_id = path.split("/", 2)[1]
        return _video(video_id)

    if path.startswith("embed/"):
        video_id = path.split("/", 2)[1]
        return _video(video_id)

    if path.startswith("@"):
        handle = path.split("/", 1)[0]
        if len(handle) <= 1:
            raise UnknownYouTubeLink(f"无法识别的 YouTube handle:{url}")
        return ResolvedYouTubeUrl(
            kind="channel",
            canonical_url=f"https://www.youtube.com/{handle}",
            external_id=None,
            handle=handle,
        )

    if path.startswith("channel/"):
        channel_id = path.split("/", 2)[1]
        if not channel_id:
            raise UnknownYouTubeLink(f"无法识别的 YouTube channel:{url}")
        return ResolvedYouTubeUrl(
            kind="channel",
            canonical_url=f"https://www.youtube.com/channel/{channel_id}",
            external_id=channel_id,
        )

    if path == "playlist":
        playlist_id = (qs.get("list") or [""])[0]
        if not playlist_id:
            raise UnknownYouTubeLink(f"无法识别的 YouTube playlist:{url}")
        return ResolvedYouTubeUrl(
            kind="playlist",
            canonical_url=f"https://www.youtube.com/playlist?list={playlist_id}",
            external_id=playlist_id,
        )

    raise UnknownYouTubeLink(f"无法识别的 YouTube 链接:{url}")


def youtube_video_pk(video_id: str) -> str:
    return f"youtube:{video_id}"


def strip_youtube_video_pk(video_id: str) -> str:
    return video_id.removeprefix("youtube:")


def _video(video_id: str) -> ResolvedYouTubeUrl:
    if not _VIDEO_ID_RE.match(video_id or ""):
        raise UnknownYouTubeLink(f"无法识别的 YouTube 视频 ID:{video_id}")
    return ResolvedYouTubeUrl(
        kind="video",
        canonical_url=f"https://www.youtube.com/watch?v={video_id}",
        external_id=video_id,
    )


def _is_youtube_host(host: str) -> bool:
    return host.lower() in _YOUTUBE_HOSTS
