"""Douyin web-API scraper via f2.

Pulls creator profile + posted videos. yt-dlp's Douyin extractor only handles
single-video URLs (no user page), so we use f2 which implements the required
`a_bogus` / `ms_token` signing against the public web API.

Requires a real browser cookie — Douyin rejects unsigned-in requests (empty
200 body). User pastes cookie at /settings.
"""

from __future__ import annotations

import logging
import re
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
    video_count: int
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
    complete: bool = True


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
        # f2 reuses `timeout` as both request timeout and inter-page sleep.
        # Keep it low enough that creator-page pagination doesn't stall for
        # 20s between every page.
        "timeout": 2,
        "max_retries": 2,
    }


async def scrape_user_page(
    sec_uid: str,
    *,
    cookie: str | None,
    max_videos: int | None = None,
) -> ScrapedUserPage:
    if not cookie or not cookie.strip():
        raise ScrapeError(
            "抖音创作者主页需要登录 Cookie。请在 /settings 导入一份真实浏览器 Cookie。"
        )

    from f2.apps.douyin.handler import DouyinHandler

    handler = DouyinHandler(_f2_conf(cookie.strip()))

    # Profile
    try:
        prof = await handler.fetch_user_profile(sec_uid)
        pdict = _to_dict(prof)
    except Exception as e:
        raise ScrapeError(_format_f2_error("拉取创作者资料失败", e)) from e
    if not pdict or not pdict.get("nickname"):
        raise ScrapeError(
            "创作者资料返回空 — 多半是 Cookie 无效 / 过期 / 未登录。"
            "请到 /settings 重新粘一份从已登录浏览器导出的 Cookie。"
        )

    creator = ScrapedCreator(
        sec_uid=sec_uid,
        name=str(pdict.get("nickname") or "未命名创作者"),
        handle=f"@{pdict.get('unique_id') or pdict.get('short_id') or sec_uid[:12]}",
        bio=(pdict.get("signature") or "").strip() or None,
        region=pdict.get("ip_location") or pdict.get("country") or None,
        verified=bool(pdict.get("custom_verify") or pdict.get("enterprise_verify_reason")),
        followers=_pick_followers(pdict),
        total_likes=int(pdict.get("total_favorited") or 0),
        video_count=int(pdict.get("aweme_count") or 0),
        avatar_url=_pick_avatar(pdict),
    )

    # Videos (paginated async generator). The raw aweme list already carries
    # title, duration, cover, timestamps, and engagement stats, so we can
    # shape metadata directly from the list endpoint without N extra detail
    # requests.
    videos: list[ScrapedVideo] = []
    complete = True
    try:
        async for page in handler.fetch_user_post_videos(
            sec_user_id=sec_uid,
            max_counts=max_videos,
            page_counts=50,
        ):
            for sv in _iter_awemes(page):
                videos.append(sv)
                if max_videos is not None and len(videos) >= max_videos:
                    break
            if max_videos is not None and len(videos) >= max_videos:
                break
    except Exception as e:
        logger.warning("fetch_user_post_videos partial failure: %s", e)
        complete = False

    return ScrapedUserPage(creator=creator, videos=videos, complete=complete)


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
    """Shape row-oriented video metadata from f2's raw aweme list."""
    raw = getattr(page, "_to_raw", None)
    data = raw() if callable(raw) else {}
    if not isinstance(data, dict):
        return []

    awemes = data.get("aweme_list")
    if not isinstance(awemes, list):
        return []
    out: list[ScrapedVideo] = []
    for aweme in awemes:
        if not isinstance(aweme, dict):
            continue
        aid_s = str(aweme.get("aweme_id") or "").strip()
        if not aid_s:
            continue
        if aweme.get("images") or aweme.get("image_post_info") is not None:
            continue
        video = aweme.get("video") or {}
        if not isinstance(video, dict) or not video:
            # Douyin creator feeds may include image posts / other non-video
            # work types. Skip them here so the import list only contains real
            # playable videos that the downstream audio pipeline can handle.
            continue
        title = _pick_aweme_title(aweme, fallback=_fallback_aweme_title(aweme, aid_s))
        stats = aweme.get("statistics") or {}
        dur_ms = video.get("duration") or aweme.get("duration") or 0
        try:
            dur_sec = int(int(dur_ms or 0) // 1000)
        except (TypeError, ValueError):
            dur_sec = 0
        cover = _pick_cover(video)
        ts = _parse_f2_create_time(aweme.get("create_time"))
        out.append(
            ScrapedVideo(
                id=aid_s,
                title=title,
                duration_sec=dur_sec,
                likes=int(stats.get("digg_count") or 0),
                plays=int(stats.get("play_count") or 0),
                comments=int(stats.get("comment_count") or 0),
                shares=int(stats.get("share_count") or 0),
                collects=int(stats.get("collect_count") or 0),
                published_at_ts=ts,
                cover_url=str(cover) if cover else None,
                source_url=f"https://www.douyin.com/video/{aid_s}",
            )
        )
    return out


_TITLE_KEYS = ("desc", "caption", "item_title", "preview_title")
_GENERIC_CHAPTER_TITLES = {"引言", "开场", "片头", "结语", "总结", "片尾"}


def _pick_aweme_title(aweme: dict[str, Any], *, fallback: str) -> str:
    for key in _TITLE_KEYS:
        title = _clean_title_text(aweme.get(key))
        if title:
            return _truncate_title(title)

    chapter_info = aweme.get("recommend_chapter_info")
    if isinstance(chapter_info, dict):
        abstract = _clean_title_text(chapter_info.get("chapter_abstract"))
        if abstract:
            return _truncate_title(_first_sentence(abstract))

        chapters = chapter_info.get("recommend_chapter_list")
        if isinstance(chapters, list):
            for chapter in chapters:
                if not isinstance(chapter, dict):
                    continue
                title = _clean_title_text(chapter.get("desc"))
                if title and title not in _GENERIC_CHAPTER_TITLES:
                    return _truncate_title(title)

    suggested_title = _pick_suggested_title(aweme)
    if suggested_title:
        return _truncate_title(suggested_title)

    return fallback


def _fallback_aweme_title(aweme: dict[str, Any], aweme_id: str) -> str:
    published_ts = _parse_f2_create_time(aweme.get("create_time"))
    if published_ts:
        from datetime import datetime

        published_day = datetime.fromtimestamp(published_ts).strftime("%Y-%m-%d")
        return f"{published_day} 作品 {aweme_id[-4:]}"
    return f"视频 {aweme_id[-8:]}"


def _pick_suggested_title(aweme: dict[str, Any]) -> str:
    suggest_words = aweme.get("suggest_words")
    if not isinstance(suggest_words, dict):
        return ""
    groups = suggest_words.get("suggest_words")
    if not isinstance(groups, list):
        return ""
    seen: set[str] = set()
    for group in groups:
        if not isinstance(group, dict):
            continue
        words = group.get("words")
        if not isinstance(words, list):
            continue
        for item in words:
            if not isinstance(item, dict):
                continue
            word = _clean_suggested_word(item.get("word"))
            if not word or word in seen:
                continue
            seen.add(word)
            return word
    return ""


def _clean_suggested_word(value: Any) -> str:
    word = _clean_title_text(value)
    if len(word) <= 1 or not re.search(r"[\w\u4e00-\u9fff]", word):
        return ""
    return word


def _clean_title_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"\s+", " ", value).strip().strip("#＃")
    if not re.search(r"[\w\u4e00-\u9fff]", text):
        return ""
    return text


def _first_sentence(text: str) -> str:
    sentence = re.split(r"[。！？!?；;]", text, maxsplit=1)[0].strip()
    return sentence or text


def _truncate_title(text: str, limit: int = 56) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip("，、,;；。.!！?？ ") + "..."


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
    avatar_url = pdict.get("avatar_url")
    if isinstance(avatar_url, str) and avatar_url.strip():
        return avatar_url.strip()
    for key in ("avatar_larger", "avatar_medium", "avatar_thumb"):
        av = pdict.get(key)
        if isinstance(av, dict):
            urls = av.get("url_list")
            if isinstance(urls, list) and urls:
                return urls[0]
    return None


def _pick_followers(pdict: dict[str, Any]) -> int:
    # Douyin profile payload can expose both follower_count and
    # mplatform_followers_count; the page UI aligns with the latter.
    for key in ("mplatform_followers_count", "follower_count"):
        try:
            return int(pdict.get(key) or 0)
        except (TypeError, ValueError):
            continue
    return 0


def _pick_cover(video: dict[str, Any]) -> str | None:
    for key in ("origin_cover", "cover", "dynamic_cover", "animated_cover"):
        block = video.get(key)
        if isinstance(block, dict):
            urls = block.get("url_list")
            if isinstance(urls, list) and urls:
                return str(urls[0])
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
