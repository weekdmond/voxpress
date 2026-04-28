from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from voxpress.config import settings
from voxpress.pipeline.douyin_scraper import (
    _f2_conf,
    _format_f2_error,
    _normalize_cookie,
    _fallback_aweme_title,
    _parse_f2_create_time,
    _pick_aweme_title,
    _pick_cover,
)
from voxpress.pipeline.protocols import Extractor, ExtractorResult

logger = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.douyin.com/",
}
_VIDEO_ID_RE = re.compile(r"/video/(\d+)")


async def probe_video_access(
    url: str,
    *,
    cookie_text: str | None,
) -> dict[str, Any]:
    video_id, canonical_url = await _resolve_video_identity(url)
    detail = await _fetch_video_detail(video_id, cookie_text)
    aweme = _aweme_from_detail(detail)
    title = _pick_aweme_title(aweme, fallback=_fallback_aweme_title(aweme, video_id))
    media_urls = _candidate_media_urls(detail, aweme)
    if not media_urls:
        raise RuntimeError("抖音返回了视频详情，但没有可用的播放地址。")
    await _probe_media_url(media_urls, cookie_text)
    return {
        "video_id": video_id,
        "title": title,
        "source_url": canonical_url,
    }


class DouyinWebExtractor(Extractor):
    def __init__(self, cookie_text: str | None = None) -> None:
        self.cookie_text = cookie_text

    async def extract(self, url: str) -> ExtractorResult:
        video_id, canonical_url = await _resolve_video_identity(url)
        detail = await _fetch_video_detail(video_id, self.cookie_text)
        aweme = _aweme_from_detail(detail)
        media_urls = _candidate_media_urls(detail, aweme)
        if not media_urls:
            raise RuntimeError("抖音返回了视频详情，但没有可用的播放地址。")

        settings.video_dir.mkdir(parents=True, exist_ok=True)
        settings.audio_dir.mkdir(parents=True, exist_ok=True)

        video_path = settings.video_dir / f"{video_id}.mp4"
        audio_path = settings.audio_dir / f"{video_id}.m4a"

        await _download_video(media_urls, video_path, self.cookie_text)
        await _extract_audio(video_path, audio_path)

        return _build_result(
            video_id=video_id,
            canonical_url=canonical_url,
            aweme=aweme,
            audio_path=audio_path,
            video_path=video_path,
        )


async def _resolve_video_identity(url: str) -> tuple[str, str]:
    matched = _VIDEO_ID_RE.search(url)
    if matched:
        video_id = matched.group(1)
        return video_id, f"https://www.douyin.com/video/{video_id}"

    async with httpx.AsyncClient(
        follow_redirects=True,
        headers=_DEFAULT_HEADERS,
        timeout=httpx.Timeout(20.0, connect=10.0),
        trust_env=False,
    ) as client:
        resp = await client.get(url)
    final_url = str(resp.url)
    matched = _VIDEO_ID_RE.search(final_url)
    if matched:
        video_id = matched.group(1)
        return video_id, f"https://www.douyin.com/video/{video_id}"
    raise RuntimeError(
        "这是创作者主页链接,不是视频。请改用「来源库 → 导入来源」,"
        "或把短链换成某一条具体视频的链接(douyin.com/video/...)。"
    )


async def _fetch_video_detail(video_id: str, cookie_text: str | None) -> Any:
    if not cookie_text or not cookie_text.strip():
        raise RuntimeError("Cookie 无效或已过期,请在 /settings 重新上传 cookies.txt。")

    from f2.apps.douyin.handler import DouyinHandler

    handler = DouyinHandler(_f2_conf(cookie_text.strip()))
    try:
        detail = await handler.fetch_one_video(video_id)
    except Exception as exc:
        message = _format_f2_error("拉取视频详情失败", exc)
        low = message.lower()
        if "cookie" in low or "过期" in message or "未登录" in message:
            raise RuntimeError("Cookie 无效或已过期,请在 /settings 重新上传 cookies.txt。") from exc
        raise RuntimeError(message) from exc

    aweme = _aweme_from_detail(detail)
    if not aweme:
        raise RuntimeError("抖音视频详情返回空，请稍后重试。")
    return detail


def _aweme_from_detail(detail: Any) -> dict[str, Any]:
    raw = getattr(detail, "_to_raw", None)
    data = raw() if callable(raw) else {}
    if not isinstance(data, dict):
        return {}
    aweme = data.get("aweme_detail")
    return aweme if isinstance(aweme, dict) else {}


def _candidate_media_urls(detail: Any, aweme: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for candidate in getattr(detail, "video_play_addr", []) or []:
        if isinstance(candidate, str) and candidate:
            urls.append(candidate)

    video = aweme.get("video")
    if isinstance(video, dict):
        for key in ("play_addr", "play_addr_h264", "play_addr_265", "download_addr"):
            block = video.get(key)
            if not isinstance(block, dict):
                continue
            url_list = block.get("url_list")
            if not isinstance(url_list, list):
                continue
            for candidate in url_list:
                if isinstance(candidate, str) and candidate:
                    urls.append(candidate)

    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    return deduped


async def _probe_media_url(urls: list[str], cookie_text: str | None) -> None:
    headers = dict(_DEFAULT_HEADERS)
    normalized = _normalize_cookie(cookie_text or "")
    if normalized:
        headers["Cookie"] = normalized
    headers["Range"] = "bytes=0-1023"

    async with httpx.AsyncClient(
        follow_redirects=True,
        headers=headers,
        timeout=httpx.Timeout(20.0, connect=10.0),
        trust_env=False,
    ) as client:
        last_error: Exception | None = None
        for url in urls:
            try:
                resp = await client.get(url)
                if resp.status_code not in (200, 206):
                    raise RuntimeError(f"HTTP {resp.status_code}")
                if not resp.content.startswith(b"\x00\x00\x00"):
                    raise RuntimeError("响应不是有效的 mp4 头")
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        if last_error:
            raise RuntimeError(f"视频下载探测失败:{last_error}") from last_error
    raise RuntimeError("视频下载探测失败:没有可用的播放地址。")


async def _download_video(urls: list[str], target_path: Path, cookie_text: str | None) -> None:
    headers = dict(_DEFAULT_HEADERS)
    normalized = _normalize_cookie(cookie_text or "")
    if normalized:
        headers["Cookie"] = normalized

    part_path = target_path.with_suffix(target_path.suffix + ".part")
    if target_path.exists():
        target_path.unlink()
    if part_path.exists():
        part_path.unlink()

    async with httpx.AsyncClient(
        follow_redirects=True,
        headers=headers,
        timeout=httpx.Timeout(120.0, connect=15.0, read=120.0, write=120.0),
        trust_env=False,
    ) as client:
        last_error: Exception | None = None
        for url in urls:
            try:
                async with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    with part_path.open("wb") as fh:
                        async for chunk in resp.aiter_bytes():
                            if chunk:
                                fh.write(chunk)
                part_path.replace(target_path)
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if part_path.exists():
                    part_path.unlink()
        if last_error:
            raise RuntimeError(f"下载失败:{last_error}") from last_error
    raise RuntimeError("下载失败:没有可用的播放地址。")


async def _extract_audio(video_path: Path, audio_path: Path) -> None:
    if audio_path.exists():
        audio_path.unlink()

    copied = await _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-c:a",
            "copy",
            str(audio_path),
        ]
    )
    if copied == 0 and audio_path.exists():
        return

    if audio_path.exists():
        audio_path.unlink()
    encoded = await _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(audio_path),
        ]
    )
    if encoded != 0 or not audio_path.exists():
        raise RuntimeError("ffmpeg 抽取音频失败。")


async def _run_ffmpeg(cmd: list[str]) -> int:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning("ffmpeg failed (%s): %s", proc.returncode, stderr.decode("utf-8", "ignore"))
    return proc.returncode


def _build_result(
    *,
    video_id: str,
    canonical_url: str,
    aweme: dict[str, Any],
    audio_path: Path,
    video_path: Path,
) -> ExtractorResult:
    author = aweme.get("author") or {}
    stats = aweme.get("statistics") or {}
    video = aweme.get("video") or {}
    title = _pick_aweme_title(aweme, fallback=_fallback_aweme_title(aweme, video_id))
    handle = _derive_handle(author)
    duration_ms = video.get("duration") or aweme.get("duration") or 0
    try:
        duration_sec = int(int(duration_ms) // 1000)
    except (TypeError, ValueError):
        duration_sec = 0

    published_ts = _parse_f2_create_time(aweme.get("create_time"))
    if published_ts:
        published_at_iso = datetime.fromtimestamp(published_ts, tz=timezone.utc).isoformat()
    else:
        published_at_iso = datetime.now(tz=timezone.utc).isoformat()

    return ExtractorResult(
        video_id=video_id,
        creator_external_id=str(author.get("sec_uid") or author.get("uid") or video_id),
        creator_handle=handle,
        creator_name=str(author.get("nickname") or handle.lstrip("@") or "未知作者"),
        creator_region=(author.get("ip_location") or None),
        creator_verified=bool(author.get("custom_verify") or author.get("enterprise_verify_reason")),
        creator_followers=int(author.get("follower_count") or 0),
        creator_total_likes=int(author.get("total_favorited") or 0),
        title=title,
        duration_sec=duration_sec,
        likes=int(stats.get("digg_count") or 0),
        plays=int(stats.get("play_count") or 0),
        comments=int(stats.get("comment_count") or 0),
        shares=int(stats.get("share_count") or 0),
        collects=int(stats.get("collect_count") or 0),
        published_at_iso=published_at_iso,
        cover_url=_pick_cover(video),
        source_url=canonical_url,
        audio_path=audio_path,
        video_path=video_path,
    )


def _derive_handle(author: dict[str, Any]) -> str:
    unique_id = str(author.get("unique_id") or "").strip()
    if unique_id:
        return unique_id if unique_id.startswith("@") else f"@{unique_id}"
    short_id = str(author.get("short_id") or "").strip()
    if short_id:
        return f"@{short_id}"
    sec_uid = str(author.get("sec_uid") or "").strip()
    if sec_uid:
        return f"@{sec_uid[:24]}"
    return "@unknown"
