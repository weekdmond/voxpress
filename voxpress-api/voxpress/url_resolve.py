"""Douyin URL classifier.

Handles the three shapes Douyin actually hands out:

- `https://v.douyin.com/xxxxxxx/`       — short link (needs redirect follow)
- `https://www.douyin.com/video/<id>`   — canonical video page
- `https://www.iesdouyin.com/share/user/<sec_uid>` — creator profile
- `https://www.douyin.com/user/<sec_uid>` — creator profile (alt host)

The short-link resolver follows redirects with plain httpx (no cookie, no JS).
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

Kind = Literal["video", "creator"]

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_DOUYIN_HOSTS = {
    "v.douyin.com",
    "douyin.com",
    "www.douyin.com",
    "iesdouyin.com",
    "www.iesdouyin.com",
}
_TRAILING_URL_PUNCT = "。；，、！？）》】」』'\""


@dataclass
class ResolvedUrl:
    kind: Kind
    canonical_url: str
    # for video: platform video id; for creator: sec_uid
    external_id: str | None


class UnknownDouyinLink(RuntimeError):
    pass


def extract_douyin_url(text: str) -> str | None:
    """Extract the first Douyin URL from a pasted share snippet.

    Users often paste the whole Douyin share text, for example:
    `长按复制此条消息，打开抖音搜索，查看TA的更多作品。 https://v.douyin.com/xxxx/`
    """
    raw = text.strip()
    if not raw:
        return None
    for candidate in re.findall(r"https?://[^\s]+", raw):
        cleaned = candidate.rstrip(_TRAILING_URL_PUNCT)
        host = (urlparse(cleaned).netloc or "").lower()
        if host in _DOUYIN_HOSTS:
            return cleaned
    return None


def normalize_douyin_input(text: str) -> str:
    raw = text.strip()
    if not raw:
        return raw
    return extract_douyin_url(raw) or raw


async def resolve(url: str, *, timeout: float = 10.0) -> ResolvedUrl:
    """Follow redirects if needed, then classify."""
    url = normalize_douyin_input(url)
    final = await _unshorten(url, timeout=timeout) if _is_short_link(url) else url
    return _classify(final)


async def fetch_creator_name(url: str, *, timeout: float = 10.0) -> str | None:
    """Cheap name extraction from the HTML `<title>` of a user page. Douyin
    titles look like `老钱说AI的抖音 - 抖音` or similar."""
    headers = {"User-Agent": _USER_AGENT}
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=timeout, headers=headers, trust_env=False
        ) as client:
            r = await client.get(url)
        m = re.search(r"<title[^>]*>([^<]+)</title>", r.text, re.IGNORECASE)
        if not m:
            return None
        title = m.group(1).strip()
        # Strip common Douyin title suffixes
        for suffix in ("的抖音 - 抖音", " - 抖音", "的抖音", "_抖音"):
            if title.endswith(suffix):
                title = title[: -len(suffix)].strip()
                break
        return title or None
    except Exception as e:
        logger.warning("fetch_creator_name failed: %s", e)
        return None


def _is_short_link(url: str) -> bool:
    return "v.douyin.com/" in url


async def _unshorten(url: str, timeout: float) -> str:
    headers = {"User-Agent": _USER_AGENT}
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=timeout, headers=headers, trust_env=False
    ) as client:
        # HEAD is lighter; some endpoints 405 so fall back to GET.
        try:
            r = await client.head(url)
            if r.status_code >= 400:
                raise httpx.HTTPStatusError("head failed", request=r.request, response=r)
        except (httpx.HTTPStatusError, httpx.RequestError):
            r = await client.get(url)
        return str(r.url)


def _classify(url: str) -> ResolvedUrl:
    # Creator profile. Accept both hosts (iesdouyin share page and douyin user
    # page), but always normalize to `https://www.douyin.com/user/<sec_uid>` —
    # that's the only form yt-dlp's Douyin extractor knows.
    m = re.search(r"/(?:share/)?user/([^/?#]+)", url)
    if m:
        sec_uid = m.group(1)
        canonical = f"https://www.douyin.com/user/{sec_uid}"
        return ResolvedUrl(kind="creator", canonical_url=canonical, external_id=sec_uid)
    # Video (note is the 图文 mixed variant; treat as video for MVP)
    m = re.search(r"/(?:video|note)/([^/?#]+)", url)
    if m:
        return ResolvedUrl(kind="video", canonical_url=url, external_id=m.group(1))
    raise UnknownDouyinLink(f"无法识别的抖音链接:{url}")


def classify_local(url: str) -> ResolvedUrl | None:
    """Best-effort classification without touching network. Returns None for
    short links (which require redirect follow)."""
    if _is_short_link(url):
        return None
    try:
        return _classify(url)
    except UnknownDouyinLink:
        return None


async def _smoke_test() -> None:  # pragma: no cover — manual helper
    for u in (
        "https://v.douyin.com/KNafzhoYOiE/",
        "https://www.douyin.com/video/7291234567890000001",
        "https://www.douyin.com/user/MS4wLjABAAAA_xxx",
    ):
        try:
            r = await resolve(u)
            print(u, "->", r)
        except Exception as e:
            print(u, "->", repr(e))


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_smoke_test())
