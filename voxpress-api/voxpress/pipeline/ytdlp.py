"""yt-dlp Extractor for Douyin.

Downloads audio-only m4a + pulls metadata. Cookie file (Netscape format or
raw cookie string written as file) is optional but strongly recommended for
Douyin — most creator pages are cookie-gated.
"""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from voxpress.config import settings
from voxpress.pipeline.protocols import Extractor, ExtractorResult

logger = logging.getLogger(__name__)


def _write_cookie_file(cookie_text: str) -> Path:
    """yt-dlp accepts either Netscape format or a raw `Cookie:` header when you
    pre-load it. We write whatever the user pasted to a tempfile; if it doesn't
    already look like Netscape format, we convert the `k=v; k=v` line into one.
    """
    path = Path(tempfile.mkstemp(prefix="vp_cookies_", suffix=".txt")[1])
    cookie_text = cookie_text.strip()
    if cookie_text.startswith("# Netscape"):
        path.write_text(cookie_text)
        return path

    # Convert "a=1; b=2; ..." → Netscape format for .douyin.com
    lines = ["# Netscape HTTP Cookie File"]
    for pair in cookie_text.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        lines.append(f".douyin.com\tTRUE\t/\tFALSE\t0\t{k.strip()}\t{v.strip()}")
    path.write_text("\n".join(lines))
    return path


async def scrape_creator_page(
    url: str,
    *,
    cookie_text: str | None,
    max_videos: int = 60,
) -> dict[str, Any]:
    """Fetch a Douyin user page and return {creator: {...}, videos: [{...}]}.

    Uses yt-dlp playlist extraction with `extract_flat="in_playlist"` — one
    round trip instead of N per-video calls. Metrics come out incomplete;
    they get filled when a real task processes the video."""
    return await asyncio.to_thread(_scrape_creator_sync, url, cookie_text, max_videos)


async def probe_video_access(
    url: str,
    *,
    cookie_text: str | None,
) -> dict[str, Any]:
    """Validate that yt-dlp can read a single video's metadata with the given
    cookie, without downloading the actual media file."""
    return await asyncio.to_thread(_probe_video_access_sync, url, cookie_text)


def _scrape_creator_sync(url: str, cookie_text: str | None, max_videos: int) -> dict[str, Any]:
    import yt_dlp

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "playlistend": max_videos,
    }
    cookie_path: Path | None = None
    if cookie_text:
        cookie_path = _write_cookie_file(cookie_text)
        ydl_opts["cookiefile"] = str(cookie_path)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False, process=False)
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                low = msg.lower()
                if "fresh cookies" in low or "login required" in low:
                    raise RuntimeError(
                        "抖音要求登录 Cookie 才能查看创作者主页,请在 /settings 导入 Cookie。"
                    ) from e
                if "unsupported url" in low:
                    raise RuntimeError(f"yt-dlp 不识别这个创作者主页:{msg[:200]}") from e
                raise RuntimeError(f"抓取创作者主页失败:{msg[:200]}") from e
    finally:
        if cookie_path and cookie_path.exists():
            try:
                cookie_path.unlink()
            except OSError:
                pass

    if info is None:
        raise RuntimeError("yt-dlp 返回空")

    # process=False returns a lazy generator for entries; force materialize.
    raw_entries = info.get("entries")
    entries: list[dict[str, Any]] = []
    if raw_entries is not None:
        for e in raw_entries:
            if isinstance(e, dict):
                entries.append(e)
            if len(entries) >= max_videos:
                break

    uploader = info.get("uploader") or info.get("channel") or ""
    uploader_id = info.get("uploader_id") or info.get("channel_id") or info.get("id") or ""

    videos: list[dict[str, Any]] = []
    for e in entries:
        vid = str(e.get("id") or "")
        if not vid:
            continue
        videos.append(
            {
                "id": vid,
                "title": e.get("title") or f"视频 {vid[-8:]}",
                "duration_sec": int(e.get("duration") or 0),
                "likes": int(e.get("like_count") or 0),
                "plays": int(e.get("view_count") or 0),
                "comments": int(e.get("comment_count") or 0),
                "shares": int(e.get("repost_count") or 0),
                "collects": 0,
                "cover_url": e.get("thumbnail"),
                "source_url": e.get("url") or f"https://www.douyin.com/video/{vid}",
                "published_at_ts": e.get("timestamp") or e.get("release_timestamp"),
            }
        )

    creator = {
        "external_id": str(uploader_id) or info.get("id") or url,
        "name": uploader or "未知创作者",
        "handle": _derive_handle(uploader_id, uploader),
        "region": None,
        "verified": bool(info.get("channel_is_verified") or info.get("uploader_verified") or False),
        "followers": int(info.get("channel_follower_count") or 0),
        "total_likes": 0,
        "video_count": len(videos),
    }
    return {"creator": creator, "videos": videos}


def _probe_video_access_sync(url: str, cookie_text: str | None) -> dict[str, Any]:
    import yt_dlp

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }
    cookie_path: Path | None = None
    if cookie_text:
        cookie_path = _write_cookie_file(cookie_text)
        ydl_opts["cookiefile"] = str(cookie_path)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
            except Exception as e:
                raise _translate_video_extract_error(e, action="读取视频元数据") from e
    finally:
        if cookie_path and cookie_path.exists():
            try:
                cookie_path.unlink()
            except OSError:
                pass

    if info is None:
        raise RuntimeError("yt-dlp 返回空")

    video_id = str(info.get("id") or info.get("display_id") or "")
    return {
        "video_id": video_id,
        "title": info.get("title") or video_id,
        "source_url": info.get("webpage_url") or url,
    }


class YtDlpExtractor(Extractor):
    def __init__(self, cookie_text: str | None = None) -> None:
        self.cookie_text = cookie_text

    async def extract(self, url: str) -> ExtractorResult:
        return await asyncio.to_thread(self._extract_sync, url)

    def _extract_sync(self, url: str) -> ExtractorResult:
        import yt_dlp

        settings.audio_dir.mkdir(parents=True, exist_ok=True)
        settings.video_dir.mkdir(parents=True, exist_ok=True)
        out_template = str(settings.video_dir / "%(id)s.%(ext)s")

        ydl_opts: dict[str, Any] = {
            "format": "best[ext=mp4]/best",
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "keepvideo": True,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "m4a", "preferredquality": "0"},
            ],
        }
        cookie_path: Path | None = None
        if self.cookie_text:
            cookie_path = _write_cookie_file(self.cookie_text)
            ydl_opts["cookiefile"] = str(cookie_path)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=True)
                except Exception as e:
                    raise _translate_video_extract_error(e, action="下载") from e
        finally:
            if cookie_path and cookie_path.exists():
                try:
                    cookie_path.unlink()
                except OSError:
                    pass

        if info is None:
            raise RuntimeError("yt-dlp returned no info")

        video_id = str(info.get("id") or info.get("display_id") or "")
        raw_audio_path = settings.video_dir / f"{video_id}.m4a"
        audio_path = settings.audio_dir / f"{video_id}.m4a"
        if raw_audio_path.exists():
            if audio_path.exists():
                audio_path.unlink()
            raw_audio_path.replace(audio_path)
        video_path = _find_downloaded_video_path(video_id)

        # Creator fields — yt-dlp "uploader" is the display name
        uploader = info.get("uploader") or info.get("creator") or info.get("channel") or ""
        uploader_id = (
            info.get("uploader_id") or info.get("channel_id") or info.get("uploader_url") or ""
        )

        published_iso = _coerce_published_at(info)

        return ExtractorResult(
            video_id=video_id,
            creator_external_id=str(uploader_id) or video_id,
            creator_handle=_derive_handle(uploader_id, uploader),
            creator_name=uploader,
            creator_region=None,
            creator_verified=bool(info.get("uploader_verified", False)),
            creator_followers=int(info.get("channel_follower_count") or 0),
            creator_total_likes=0,  # not exposed by yt-dlp douyin
            title=info.get("title") or video_id,
            duration_sec=int(info.get("duration") or 0),
            likes=int(info.get("like_count") or 0),
            plays=int(info.get("view_count") or 0),
            comments=int(info.get("comment_count") or 0),
            shares=int(info.get("repost_count") or 0),
            collects=0,  # not exposed
            published_at_iso=published_iso,
            cover_url=info.get("thumbnail"),
            source_url=info.get("webpage_url") or url,
            audio_path=audio_path,
            video_path=video_path,
        )


def _derive_handle(uploader_id: Any, uploader_name: str) -> str:
    if isinstance(uploader_id, str) and uploader_id:
        if uploader_id.startswith("http"):
            m = re.search(r"/user/([^/?#]+)", uploader_id)
            if m:
                return f"@{m.group(1)[:24]}"
        return f"@{uploader_id[:24]}" if not uploader_id.startswith("@") else uploader_id
    return f"@{uploader_name[:24]}" if uploader_name else "@unknown"


def _coerce_published_at(info: dict[str, Any]) -> str:
    ts = info.get("timestamp") or info.get("release_timestamp")
    if ts:
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
        except (TypeError, ValueError):
            pass
    ds = info.get("upload_date")  # YYYYMMDD
    if isinstance(ds, str) and len(ds) == 8:
        try:
            return datetime(int(ds[:4]), int(ds[4:6]), int(ds[6:8]), tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    return datetime.now(tz=timezone.utc).isoformat()


def _find_downloaded_video_path(video_id: str) -> Path | None:
    preferred_suffixes = (".mp4", ".mov", ".mkv", ".webm", ".m4v", ".flv")
    for suffix in preferred_suffixes:
        candidate = settings.video_dir / f"{video_id}{suffix}"
        if candidate.exists():
            return candidate
    for candidate in settings.video_dir.glob(f"{video_id}.*"):
        if candidate.suffix.lower() in {".m4a", ".part", ".ytdl"}:
            continue
        if candidate.is_file():
            return candidate
    return None


def _translate_video_extract_error(exc: Exception, *, action: str) -> RuntimeError:
    # yt-dlp wraps UnsupportedError inside DownloadError when raised from the
    # top-level extract_info, so we match on the string rather than the class.
    msg = str(exc)
    low = msg.lower()
    if "/share/user/" in msg or "/user/" in msg and "unsupported url" in low:
        return RuntimeError(
            "这是创作者主页链接,不是视频。请改用「来源库 → 导入来源」,"
            "或把短链换成某一条具体视频的链接(douyin.com/video/...)。"
        )
    if "unsupported url" in low:
        return RuntimeError(f"yt-dlp 不支持这个链接类型。原始错误:{msg[:200]}")
    if "fresh cookies" in low or "login required" in low:
        return RuntimeError("Cookie 无效或已过期,请在 /settings 重新上传 cookies.txt。")
    return RuntimeError(f"{action}失败:{msg[:200]}")
