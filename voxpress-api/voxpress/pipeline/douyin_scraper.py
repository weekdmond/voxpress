"""Douyin web-API scraper via f2.

Pulls creator profile + posted videos. yt-dlp's Douyin extractor only handles
single-video URLs (no user page), so we use f2 which implements the required
`a_bogus` / `ms_token` signing against the public web API.

Requires a real browser cookie — Douyin rejects unsigned-in requests (empty
200 body). User pastes cookie at /settings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ScrapedCreator:
    sec_uid: str
    name: str
    handle: str  # "@unique_id"
    bio: str | None
    region: str | None
    verified: bool
    followers: int
    total_likes: int
    avatar_url: str | None


@dataclass
class ScrapedVideo:
    id: str  # aweme_id
    title: str
    duration_sec: int
    likes: int
    plays: int
    comments: int
    shares: int
    collects: int
    published_at_ts: int
    cover_url: str | None
    source_url: str


@dataclass
class ScrapedUserPage:
    creator: ScrapedCreator
    videos: list[ScrapedVideo]


class ScrapeError(RuntimeError):
    pass


def _normalize_cookie(text: str) -> str:
    """Accept either a raw Cookie header (`a=1; b=2`) or a Netscape format
    file (what `Get cookies.txt LOCALLY` exports). f2 only understands the
    header form — if we give it Netscape content with tabs and newlines, the
    library splices those into the HTTP Cookie header and Douyin rejects it
    with a protocol error."""
    text = text.strip()
    if not (text.startswith("# Netscape") or "\t" in text):
        return text
    pairs: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        # Netscape columns: domain, include_subdomains, path, secure, expiry, name, value
        if len(parts) >= 7 and parts[5]:
            pairs.append(f"{parts[5]}={parts[6]}")
    return "; ".join(pairs)


def _f2_conf(cookie: str) -> dict[str, Any]:
    return {
        "headers": {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.douyin.com/",
        },
        "cookie": _normalize_cookie(cookie),
        "proxies": {"http://": None, "https://": None},
        "timeout": 20,
        "max_retries": 2,
    }


async def scrape_user_page(
    sec_uid: str,
    *,
    cookie: str | None,
    max_videos: int = 20,
) -> ScrapedUserPage:
    if not cookie or not cookie.strip():
        raise ScrapeError(
            "抖音博主主页需要登录 Cookie。请在 /settings 导入一份真实浏览器 Cookie。"
        )

    from f2.apps.douyin.handler import DouyinHandler

    handler = DouyinHandler(_f2_conf(cookie.strip()))

    # Profile
    try:
        prof = await handler.fetch_user_profile(sec_uid)
        pdict = _to_dict(prof)
    except Exception as e:
        raise ScrapeError(_format_f2_error("拉取博主资料失败", e)) from e
    if not pdict or not pdict.get("nickname"):
        raise ScrapeError(
            "博主资料返回空 — 多半是 Cookie 无效 / 过期 / 未登录。"
            "请到 /settings 重新粘一份从已登录浏览器导出的 Cookie。"
        )

    creator = ScrapedCreator(
        sec_uid=sec_uid,
        name=str(pdict.get("nickname") or "未命名博主"),
        handle=f"@{pdict.get('unique_id') or pdict.get('short_id') or sec_uid[:12]}",
        bio=(pdict.get("signature") or "").strip() or None,
        region=pdict.get("ip_location") or pdict.get("country") or None,
        verified=bool(pdict.get("custom_verify") or pdict.get("enterprise_verify_reason")),
        followers=int(pdict.get("follower_count") or 0),
        total_likes=int(pdict.get("total_favorited") or 0),
        avatar_url=_pick_avatar(pdict),
    )

    # Videos (paginated async generator). `_iter_awemes` already returns
    # ScrapedVideo objects shaped from f2's column-oriented filter — they
    # carry title/duration/cover/timestamp but NO engagement stats (that
    # endpoint doesn't expose them).
    videos: list[ScrapedVideo] = []
    try:
        async for page in handler.fetch_user_post_videos(
            sec_user_id=sec_uid,
            max_counts=max_videos,
            page_counts=20,
        ):
            for sv in _iter_awemes(page):
                videos.append(sv)
                if len(videos) >= max_videos:
                    break
            if len(videos) >= max_videos:
                break
    except Exception as e:
        logger.warning("fetch_user_post_videos partial failure: %s", e)

    # Enrich stats in parallel via fetch_one_video (likes/comments/shares/
    # collects). play_count is not exposed by the Douyin web API.
    if videos:
        await _enrich_stats(handler, videos, concurrency=5)

    return ScrapedUserPage(creator=creator, videos=videos)


async def _enrich_stats(handler, videos: list[ScrapedVideo], *, concurrency: int) -> None:
    import asyncio

    sem = asyncio.Semaphore(concurrency)

    async def one(v: ScrapedVideo) -> None:
        async with sem:
            try:
                det = await handler.fetch_one_video(aweme_id=v.id)
                d = _to_dict(det)
            except Exception as e:  # noqa: BLE001
                logger.debug("fetch_one_video %s failed: %s", v.id, e)
                return
            if not isinstance(d, dict):
                return
            v.likes = int(d.get("digg_count") or 0)
            v.comments = int(d.get("comment_count") or 0)
            v.shares = int(d.get("share_count") or 0)
            v.collects = int(d.get("collect_count") or 0)
            # Douyin web doesn't return play_count; leave as 0.

    await asyncio.gather(*(one(v) for v in videos), return_exceptions=True)


# ─── helpers ────────────────────────────────────────


def _to_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    for attr in ("_to_dict", "to_dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            d = fn()
            if isinstance(d, dict):
                return d
    if isinstance(obj, dict):
        return obj
    # Fall back to vars() for simple dataclass-like objects
    try:
        return vars(obj)
    except TypeError:
        return {}


def _iter_awemes(page: Any) -> list[ScrapedVideo]:
    """f2's UserPostFilter is COLUMN-oriented: every public attr (`aweme_id`,
    `desc`, `video_duration`, `cover`, `create_time`, ...) is a parallel list
    of length N. We zip the columns back into row-shaped ScrapedVideo.

    Note: fetch_user_post_videos doesn't expose engagement stats
    (like/play/comment counts) — those get filled later when an individual
    task processes the video via yt-dlp."""
    d = _to_dict(page)
    if not isinstance(d, dict):
        return []
    ids = d.get("aweme_id") or []
    if not isinstance(ids, list):
        return []

    def col(name: str) -> list[Any]:
        v = d.get(name)
        return v if isinstance(v, list) else []

    descs = col("desc")
    durations = col("video_duration")  # milliseconds
    covers = col("cover")
    created = col("create_time")
    out: list[ScrapedVideo] = []
    for i, aid in enumerate(ids):
        aid_s = str(aid or "").strip()
        if not aid_s:
            continue
        title = (str(descs[i]) if i < len(descs) else "").strip() or f"视频 {aid_s[-8:]}"
        dur_ms = durations[i] if i < len(durations) else 0
        try:
            dur_sec = int(int(dur_ms or 0) // 1000)
        except (TypeError, ValueError):
            dur_sec = 0
        cover = covers[i] if i < len(covers) else None
        if isinstance(cover, list):
            cover = cover[0] if cover else None
        ts = _parse_f2_create_time(created[i] if i < len(created) else None)
        out.append(
            ScrapedVideo(
                id=aid_s,
                title=title,
                duration_sec=dur_sec,
                likes=0,
                plays=0,
                comments=0,
                shares=0,
                collects=0,
                published_at_ts=ts,
                cover_url=str(cover) if cover else None,
                source_url=f"https://www.douyin.com/video/{aid_s}",
            )
        )
    return out


def _parse_f2_create_time(v: Any) -> int:
    """f2 pre-formats create_time as `YYYY-MM-DD HH-MM-SS`. Convert back to
    a Unix timestamp; accept ints/floats too in case future versions change."""
    if v is None or v == "":
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        from datetime import datetime

        for fmt in ("%Y-%m-%d %H-%M-%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return int(datetime.strptime(v, fmt).timestamp())
            except ValueError:
                continue
    return 0


def _pick_avatar(pdict: dict[str, Any]) -> str | None:
    for key in ("avatar_larger", "avatar_medium", "avatar_thumb"):
        av = pdict.get(key)
        if isinstance(av, dict):
            urls = av.get("url_list")
            if isinstance(urls, list) and urls:
                return urls[0]
    return None


def _format_f2_error(prefix: str, e: Exception) -> str:
    cls = type(e).__name__
    msg = str(e)[:200]
    if "APIRetryExhausted" in cls:
        return (
            f"{prefix}:请求连续失败 — 多为 Cookie 无效/过期 或 代理/网络问题。"
            f"请到 /settings 重粘一份最新 Cookie。原始:{msg}"
        )
    return f"{prefix}:{cls} {msg}"
