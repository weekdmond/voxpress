from __future__ import annotations

import asyncio
import hashlib
import logging
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

import httpx
import oss2

from voxpress.runtime_settings import (
    OssRuntimeSettings,
    build_oss_runtime_settings,
    load_oss_runtime_settings,
)

logger = logging.getLogger(__name__)

DOUYIN_MEDIA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.douyin.com/",
}

_CONTENT_TYPE_BY_SUFFIX = {
    ".avif": "image/avif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


class MediaStoreError(RuntimeError):
    pass


def _guess_content_type(path: Path) -> str:
    content_type, _ = mimetypes.guess_type(path.name)
    return content_type or "application/octet-stream"


def _suffix_for_remote(url: str, content_type: str | None = None) -> str:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix:
        return suffix
    if content_type:
        for known_suffix, known_type in _CONTENT_TYPE_BY_SUFFIX.items():
            if content_type.startswith(known_type):
                return known_suffix
    return ""
class OssMediaStore:
    def __init__(self) -> None:
        self._config = build_oss_runtime_settings(None)
        self._config_signature = self._signature_for(self._config)
        self._bucket: oss2.Bucket | None = None

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @staticmethod
    def _signature_for(config: OssRuntimeSettings) -> tuple[str, str, str, str]:
        return (
            config.endpoint,
            config.bucket,
            config.access_key_id,
            config.access_key_secret,
        )

    def _apply_config(self, config: OssRuntimeSettings) -> None:
        signature = self._signature_for(config)
        if signature != self._config_signature:
            self._bucket = None
            self._config_signature = signature
        self._config = config

    async def refresh(self) -> OssRuntimeSettings:
        config = await load_oss_runtime_settings()
        self._apply_config(config)
        return config

    async def is_enabled(self) -> bool:
        return (await self.refresh()).enabled

    def _client(self) -> oss2.Bucket:
        if not self.enabled:
            raise MediaStoreError("OSS 未配置")
        if self._bucket is None:
            auth = oss2.Auth(self._config.access_key_id, self._config.access_key_secret)
            self._bucket = oss2.Bucket(auth, self._config.endpoint, self._config.bucket)
        return self._bucket

    async def sign_url(self, object_key: str) -> str:
        await self.refresh()
        bucket = self._client()
        return await asyncio.to_thread(
            bucket.sign_url,
            "GET",
            object_key,
            self._config.sign_expires_sec,
            slash_safe=True,
        )

    async def upload_file(self, path: Path, *, object_key: str) -> str | None:
        await self.refresh()
        if not self.enabled or not path.exists():
            return None
        bucket = self._client()
        exists = await asyncio.to_thread(bucket.object_exists, object_key)
        if not exists:
            headers = {
                "Content-Type": _guess_content_type(path),
                "Cache-Control": "private, max-age=31536000, immutable",
            }
            await asyncio.to_thread(
                bucket.put_object_from_file,
                object_key,
                str(path),
                headers=headers,
            )
        return object_key

    async def download_file(self, object_key: str, *, path: Path) -> Path:
        await self.refresh()
        bucket = self._client()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        try:
            await asyncio.to_thread(bucket.get_object_to_file, object_key, str(path))
        except Exception as e:  # noqa: BLE001
            raise MediaStoreError(f"下载 OSS 文件失败: {object_key}") from e
        return path

    async def cache_remote_image(self, source_url: str) -> str | None:
        await self.refresh()
        if not self.enabled:
            return None
        bucket = self._client()
        parsed = urlparse(source_url)
        host = (parsed.hostname or "unknown").lower()
        digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()
        suffix = _suffix_for_remote(source_url)
        object_key = f"douyin/images/{host}/{digest}{suffix}"
        exists = await asyncio.to_thread(bucket.object_exists, object_key)
        if exists:
            return object_key

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
                res = await client.get(source_url, headers=DOUYIN_MEDIA_HEADERS)
                res.raise_for_status()
        except httpx.HTTPError as e:
            raise MediaStoreError("拉取远程图片失败") from e

        content_type = (res.headers.get("content-type") or "image/jpeg").split(";", 1)[0]
        if not suffix:
            suffix = _suffix_for_remote(source_url, content_type)
            object_key = f"douyin/images/{host}/{digest}{suffix}"
        headers = {
            "Content-Type": content_type,
            "Cache-Control": "private, max-age=31536000, immutable",
        }
        await asyncio.to_thread(bucket.put_object, object_key, res.content, headers=headers)
        return object_key


def video_object_key(video_id: str, path: Path) -> str:
    suffix = path.suffix.lower() or ".mp4"
    return f"douyin/videos/{video_id}{suffix}"


def audio_object_key(video_id: str, path: Path) -> str:
    suffix = path.suffix.lower() or ".m4a"
    return f"douyin/audio/{video_id}{suffix}"


media_store = OssMediaStore()
