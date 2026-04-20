from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voxpress.db import get_session
from voxpress.errors import CookieMissing
from voxpress.models import SettingEntry
from voxpress.schemas import (
    CookiePostIn,
    CookieSettings,
    LlmSettings,
    PromptSettings,
    SettingsOut,
    SettingsPatch,
    StorageSettings,
    WhisperSettings,
)

router = APIRouter(prefix="/api", tags=["settings"])

_DEFAULTS: SettingsOut = SettingsOut(
    llm=LlmSettings(),
    whisper=WhisperSettings(),
    prompt=PromptSettings(
        template="你是一位严谨的中文编辑。把下面这段口播转写整理成一篇结构化的文章,保留原作者的语气,消除口头禅和重复。"
    ),
    cookie=CookieSettings(),
    storage=StorageSettings(),
)


async def _load(s: AsyncSession) -> SettingsOut:
    rows = (await s.scalars(select(SettingEntry))).all()
    data: dict = _DEFAULTS.model_dump()
    for row in rows:
        if row.key in data:
            data[row.key] = {**data[row.key], **row.value}
    return SettingsOut.model_validate(data)


async def _save(s: AsyncSession, key: str, value: dict) -> None:
    row = await s.get(SettingEntry, key)
    if row:
        row.value = value
    else:
        s.add(SettingEntry(key=key, value=value))


@router.get("/settings", response_model=SettingsOut)
async def get_settings(s: AsyncSession = Depends(get_session)) -> SettingsOut:
    return await _load(s)


@router.patch("/settings", response_model=SettingsOut)
async def patch_settings(
    payload: SettingsPatch, s: AsyncSession = Depends(get_session)
) -> SettingsOut:
    current = await _load(s)
    merged = current.model_dump(mode="json")  # datetimes → ISO strings for JSONB
    for key, value in payload.model_dump(exclude_none=True, mode="json").items():
        merged[key] = {**merged[key], **value}
    for k, v in merged.items():
        # preserve any private fields (e.g. cookie.text) that _load() stripped
        existing = await s.get(SettingEntry, k)
        if existing:
            preserved = {pk: pv for pk, pv in existing.value.items() if pk not in v}
            v = {**v, **preserved}
        await _save(s, k, v)
    await s.commit()
    if payload.llm is not None:
        from voxpress.pipeline import runner

        await runner.set_concurrency(merged["llm"]["concurrency"])
    return SettingsOut.model_validate(merged)


@router.post("/cookie")
async def post_cookie(
    payload: CookiePostIn, s: AsyncSession = Depends(get_session)
) -> dict:
    text = (payload.text or "").strip()
    if not text:
        raise CookieMissing("cookie 文本不能为空")

    await _save(
        s,
        "cookie",
        {
            "status": "ok",
            "last_tested_at": datetime.now(tz=timezone.utc).isoformat(),
            # persisted but never returned via GET (see _load)
            "text": text,
        },
    )
    await s.commit()
    return {"status": "ok"}


@router.post("/cookie/test")
async def test_cookie(s: AsyncSession = Depends(get_session)) -> dict:
    current = await _load(s)
    if current.cookie.status != "ok":
        raise CookieMissing("未导入 Cookie")
    return {"status": "ok", "handle_sample": "@example-handle"}


@router.get("/models")
async def list_models() -> dict:
    import httpx

    from voxpress.config import settings as app_settings

    try:
        async with httpx.AsyncClient(timeout=3.0, trust_env=False) as client:
            r = await client.get(f"{app_settings.llm_base_url.rstrip('/')}/api/tags")
            r.raise_for_status()
            data = r.json()
        names = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        return {"ollama": names}
    except Exception:
        # Fall back so the UI doesn't break when Ollama isn't running
        return {"ollama": []}
