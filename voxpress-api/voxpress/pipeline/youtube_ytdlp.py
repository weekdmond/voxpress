from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from voxpress.config import settings
from voxpress.pipeline.protocols import Extractor, ExtractorResult, TranscriptResult
from voxpress.pipeline.youtube_oembed import fetch_oembed_video
from voxpress.pipeline.youtube_url import (
    resolve_youtube_url,
    strip_youtube_video_pk,
    youtube_video_pk,
)


class YouTubeExtractError(RuntimeError):
    pass


@dataclass(frozen=True)
class YouTubeChannelInfo:
    channel_id: str
    handle: str
    name: str
    avatar_url: str | None = None
    followers: int = 0
    video_count: int = 0


@dataclass(frozen=True)
class YouTubeVideoInfo:
    id: str
    external_id: str
    title: str
    duration_sec: int
    plays: int
    likes: int
    comments: int
    cover_url: str | None
    source_url: str
    published_at: datetime
    channel: YouTubeChannelInfo


class YouTubeExtractor(Extractor):
    async def extract(self, url: str) -> ExtractorResult:
        return await asyncio.to_thread(_extract_audio_sync, url)


async def probe_video(url: str) -> YouTubeVideoInfo:
    return await asyncio.to_thread(_probe_video_sync, url)


async def resolve_channel(url: str) -> YouTubeChannelInfo:
    return await asyncio.to_thread(_resolve_channel_sync, url)


async def fetch_channel_videos(url: str, *, max_videos: int | None) -> tuple[YouTubeChannelInfo, list[YouTubeVideoInfo]]:
    return await asyncio.to_thread(_fetch_channel_videos_sync, url, max_videos)


async def fetch_transcript(url: str) -> TranscriptResult | None:
    return await asyncio.to_thread(_fetch_transcript_sync, url)


def _base_ytdlp_opts() -> dict[str, Any]:
    return {
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }


def _probe_video_sync(url: str) -> YouTubeVideoInfo:
    import yt_dlp

    opts = {**_base_ytdlp_opts(), "skip_download": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as exc:  # noqa: BLE001
            try:
                oembed = asyncio.run(fetch_oembed_video(url))
            except Exception:
                raise YouTubeExtractError(f"YouTube 视频元数据读取失败:{str(exc)[:200]}") from exc
            return YouTubeVideoInfo(
                id=oembed.video_id,
                external_id=strip_youtube_video_pk(oembed.video_id),
                title=oembed.title,
                duration_sec=0,
                plays=0,
                likes=0,
                comments=0,
                cover_url=oembed.thumbnail_url,
                source_url=oembed.source_url,
                published_at=datetime.now(tz=timezone.utc),
                channel=YouTubeChannelInfo(
                    channel_id=oembed.author_url or oembed.author_name,
                    handle=_derive_handle(oembed.author_url, oembed.author_name),
                    name=oembed.author_name,
                ),
            )
    if not isinstance(info, dict):
        raise YouTubeExtractError("YouTube 返回空元数据")
    return _video_from_info(info)


def _resolve_channel_sync(url: str) -> YouTubeChannelInfo:
    import yt_dlp

    opts = {**_base_ytdlp_opts(), "skip_download": True, "extract_flat": "in_playlist", "playlistend": 1}
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False, process=False)
        except Exception as exc:  # noqa: BLE001
            raise YouTubeExtractError(f"YouTube 频道解析失败:{str(exc)[:200]}") from exc
    if not isinstance(info, dict):
        raise YouTubeExtractError("YouTube 频道返回空元数据")
    return _channel_from_info(info)


def _fetch_channel_videos_sync(url: str, max_videos: int | None) -> tuple[YouTubeChannelInfo, list[YouTubeVideoInfo]]:
    import yt_dlp

    url = _channel_videos_url(url)
    opts = {
        **_base_ytdlp_opts(),
        "skip_download": True,
        "extract_flat": "in_playlist",
        "playlistend": max_videos,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False, process=False)
        except Exception as exc:  # noqa: BLE001
            raise YouTubeExtractError(f"YouTube 频道作品读取失败:{str(exc)[:200]}") from exc
    if not isinstance(info, dict):
        raise YouTubeExtractError("YouTube 频道返回空元数据")
    channel = _channel_from_info(info)
    videos: list[YouTubeVideoInfo] = []
    entries = info.get("entries") or []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        video_id = str(entry.get("id") or "").strip()
        if not _looks_like_video_id(video_id):
            continue
        videos.append(_video_from_info(entry, channel=channel))
        if max_videos is not None and len(videos) >= max_videos:
            break
    return channel, videos


def _fetch_transcript_sync(url: str) -> TranscriptResult | None:
    import yt_dlp

    info = resolve_youtube_url(url)
    video_id = info.external_id or "youtube"
    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    subtitle_template = str(settings.audio_dir / f"youtube_{video_id}.%(ext)s")
    opts = {
        **_base_ytdlp_opts(),
        "skip_download": True,
        "noplaylist": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["zh-Hans", "zh-CN", "zh", "en"],
        "subtitlesformat": "json3/vtt/best",
        "outtmpl": {"default": subtitle_template},
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            ydl.extract_info(url, download=True)
        except Exception:
            return None

    candidates = sorted(settings.audio_dir.glob(f"youtube_{video_id}.*"))
    for candidate in candidates:
        if candidate.suffix == ".json3":
            result = _parse_json3(candidate)
            if result is not None:
                return result
        if candidate.suffix == ".vtt":
            result = _parse_vtt(candidate)
            if result is not None:
                return result
    return None


def _extract_audio_sync(url: str) -> ExtractorResult:
    import yt_dlp

    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    settings.video_dir.mkdir(parents=True, exist_ok=True)
    info = resolve_youtube_url(url)
    external_id = info.external_id or "%(id)s"
    out_template = str(settings.video_dir / f"youtube_{external_id}.%(ext)s")
    opts = {
        **_base_ytdlp_opts(),
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "m4a", "preferredquality": "0"},
        ],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            raw = ydl.extract_info(url, download=True)
        except Exception as exc:  # noqa: BLE001
            raise YouTubeExtractError(f"YouTube 音频下载失败:{str(exc)[:200]}") from exc
    if not isinstance(raw, dict):
        raise YouTubeExtractError("YouTube 音频下载返回空元数据")
    video = _video_from_info(raw)
    downloaded = settings.video_dir / f"youtube_{video.external_id}.m4a"
    audio_path = settings.audio_dir / f"{video.id}.m4a"
    if downloaded.exists():
        if audio_path.exists():
            audio_path.unlink()
        downloaded.replace(audio_path)
    elif not audio_path.exists():
        matches = list(settings.video_dir.glob(f"youtube_{video.external_id}.*"))
        if matches:
            matches[0].replace(audio_path)
    return ExtractorResult(
        video_id=video.id,
        creator_external_id=video.channel.channel_id,
        creator_handle=video.channel.handle,
        creator_name=video.channel.name,
        creator_region=None,
        creator_verified=False,
        creator_followers=video.channel.followers,
        creator_total_likes=0,
        title=video.title,
        duration_sec=video.duration_sec,
        likes=video.likes,
        plays=video.plays,
        comments=video.comments,
        shares=0,
        collects=0,
        published_at_iso=video.published_at.isoformat(),
        cover_url=video.cover_url,
        source_url=video.source_url,
        audio_path=audio_path,
        platform="youtube",
    )


def _video_from_info(info: dict[str, Any], *, channel: YouTubeChannelInfo | None = None) -> YouTubeVideoInfo:
    external_id = str(info.get("id") or info.get("display_id") or "").strip()
    if external_id.startswith("youtube:"):
        external_id = strip_youtube_video_pk(external_id)
    if not external_id:
        external_id = str(info.get("url") or "").rsplit("v=", 1)[-1][:32] or "unknown"
    channel_info = channel or _channel_from_info(info)
    return YouTubeVideoInfo(
        id=youtube_video_pk(external_id),
        external_id=external_id,
        title=str(info.get("title") or f"YouTube 视频 {external_id}"),
        duration_sec=int(info.get("duration") or 0),
        plays=int(info.get("view_count") or 0),
        likes=int(info.get("like_count") or 0),
        comments=int(info.get("comment_count") or 0),
        cover_url=info.get("thumbnail"),
        source_url=str(info.get("webpage_url") or info.get("url") or f"https://www.youtube.com/watch?v={external_id}"),
        published_at=_coerce_published_at(info),
        channel=channel_info,
    )


def _looks_like_video_id(value: str) -> bool:
    if value.startswith("UC"):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{11}", value))


def _channel_videos_url(url: str) -> str:
    stripped = url.rstrip("/")
    if re.search(r"/(videos|streams|shorts)$", stripped):
        return stripped
    return f"{stripped}/videos"


def _channel_from_info(info: dict[str, Any]) -> YouTubeChannelInfo:
    channel_id = str(
        info.get("channel_id")
        or info.get("uploader_id")
        or info.get("id")
        or info.get("channel_url")
        or ""
    )
    name = str(info.get("channel") or info.get("uploader") or info.get("title") or "YouTube")
    handle = _derive_handle(
        str(info.get("channel_url") or info.get("uploader_url") or channel_id),
        str(info.get("channel") or info.get("uploader") or name),
    )
    return YouTubeChannelInfo(
        channel_id=channel_id or handle.lstrip("@"),
        handle=handle,
        name=name,
        avatar_url=info.get("thumbnail"),
        followers=int(info.get("channel_follower_count") or 0),
        video_count=int(info.get("playlist_count") or info.get("n_entries") or 0),
    )


def _derive_handle(url_or_id: str | None, name: str) -> str:
    raw = str(url_or_id or "")
    m = re.search(r"/(@[^/?#]+)", raw)
    if m:
        return m.group(1)
    if raw.startswith("@"):
        return raw
    if raw.startswith("UC"):
        return f"@{raw[:24]}"
    clean = re.sub(r"\s+", "", name.strip())[:24]
    return f"@{clean or 'youtube'}"


def _coerce_published_at(info: dict[str, Any]) -> datetime:
    ts = info.get("timestamp") or info.get("release_timestamp")
    if ts:
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except (TypeError, ValueError):
            pass
    upload_date = info.get("upload_date")
    if isinstance(upload_date, str) and len(upload_date) == 8:
        try:
            return datetime(int(upload_date[:4]), int(upload_date[4:6]), int(upload_date[6:8]), tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(tz=timezone.utc)


def _parse_json3(path: Path) -> TranscriptResult | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    segments: list[tuple[int, str]] = []
    for event in data.get("events") or []:
        if not isinstance(event, dict):
            continue
        parts = event.get("segs") or []
        text = "".join(str(part.get("utf8") or "") for part in parts if isinstance(part, dict)).strip()
        if not text:
            continue
        ts = int((event.get("tStartMs") or 0) / 1000)
        segments.append((ts, text))
    return TranscriptResult(segments=segments) if segments else None


def _parse_vtt(path: Path) -> TranscriptResult | None:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return None
    segments: list[tuple[int, str]] = []
    current_ts = 0
    current_text: list[str] = []
    for line in lines:
        line = line.strip()
        if not line or line == "WEBVTT" or line.startswith("Kind:") or line.startswith("Language:"):
            if current_text:
                segments.append((current_ts, " ".join(current_text).strip()))
                current_text = []
            continue
        if "-->" in line:
            if current_text:
                segments.append((current_ts, " ".join(current_text).strip()))
                current_text = []
            current_ts = _parse_vtt_ts(line.split("-->", 1)[0].strip())
            continue
        if line.isdigit():
            continue
        cleaned = re.sub(r"<[^>]+>", "", line).strip()
        if cleaned:
            current_text.append(cleaned)
    if current_text:
        segments.append((current_ts, " ".join(current_text).strip()))
    return TranscriptResult(segments=segments) if segments else None


def _parse_vtt_ts(raw: str) -> int:
    parts = raw.replace(",", ".").split(":")
    try:
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + int(float(s))
        if len(parts) == 2:
            m, s = parts
            return int(m) * 60 + int(float(s))
    except ValueError:
        return 0
    return 0
