from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from voxpress.config import settings as app_settings
from voxpress.db import session_scope
from voxpress.models import SettingEntry


def _clean_str(value: Any) -> str:
    return str(value or "").strip()


def _coalesce_str(primary: Any, fallback: Any) -> str:
    return _clean_str(primary) or _clean_str(fallback)


def _normalize_oss_endpoint(*, endpoint: str, region: str) -> str:
    if not endpoint and region:
        endpoint = f"oss-{region}.aliyuncs.com"
    if not endpoint:
        return ""
    if endpoint.startswith(("http://", "https://")):
        return endpoint.rstrip("/")
    return f"https://{endpoint.rstrip('/')}"


@dataclass(slots=True)
class DashScopeRuntimeSettings:
    api_key: str
    base_url: str

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.base_url)

    @property
    def chat_base_url(self) -> str:
        return self.base_url.rstrip("/")

    @property
    def api_base_url(self) -> str:
        base = self.chat_base_url
        if base.endswith("/compatible-mode/v1"):
            return f"{base[:-len('/compatible-mode/v1')]}/api/v1"
        if "/compatible-mode/" in base:
            return base.replace("/compatible-mode/", "/api/", 1)
        return f"{base}/api/v1"


@dataclass(slots=True)
class OssRuntimeSettings:
    region: str
    endpoint: str
    bucket: str
    access_key_id: str
    access_key_secret: str
    sign_expires_sec: int

    @property
    def enabled(self) -> bool:
        return bool(
            self.bucket and self.endpoint and self.access_key_id and self.access_key_secret
        )


def build_dashscope_runtime_settings(
    value: Mapping[str, Any] | None,
) -> DashScopeRuntimeSettings:
    raw = dict(value or {})
    return DashScopeRuntimeSettings(
        api_key=_coalesce_str(raw.get("api_key"), app_settings.dashscope_api_key),
        base_url=_coalesce_str(raw.get("base_url"), app_settings.dashscope_compatible_base_url),
    )


def build_oss_runtime_settings(
    value: Mapping[str, Any] | None,
) -> OssRuntimeSettings:
    raw = dict(value or {})
    region = _coalesce_str(raw.get("region"), app_settings.oss_region)
    raw_endpoint = _coalesce_str(raw.get("endpoint"), app_settings.oss_endpoint)
    return OssRuntimeSettings(
        region=region,
        endpoint=_normalize_oss_endpoint(endpoint=raw_endpoint, region=region),
        bucket=_coalesce_str(raw.get("bucket"), app_settings.oss_bucket),
        access_key_id=_coalesce_str(raw.get("access_key_id"), app_settings.oss_access_key_id),
        access_key_secret=_coalesce_str(
            raw.get("access_key_secret"), app_settings.oss_access_key_secret
        ),
        sign_expires_sec=app_settings.oss_sign_expires_sec,
    )


async def load_setting_value(
    key: str,
    *,
    session: AsyncSession | None = None,
) -> dict[str, Any] | None:
    if session is not None:
        row = await session.get(SettingEntry, key)
        return dict(row.value) if row else None

    async with session_scope() as s:
        row = await s.get(SettingEntry, key)
        return dict(row.value) if row else None


async def load_dashscope_runtime_settings(
    *,
    session: AsyncSession | None = None,
) -> DashScopeRuntimeSettings:
    return build_dashscope_runtime_settings(await load_setting_value("dashscope", session=session))


async def load_oss_runtime_settings(
    *,
    session: AsyncSession | None = None,
) -> OssRuntimeSettings:
    return build_oss_runtime_settings(await load_setting_value("oss", session=session))
