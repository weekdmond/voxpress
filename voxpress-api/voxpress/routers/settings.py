from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voxpress.db import get_session
from voxpress.errors import CookieInvalid, CookieMissing, InvalidCookieFile
from voxpress.creator_sync import fetch_creator_page
from voxpress.models import Creator, SettingEntry, Video
from voxpress.pipeline.douyin_video import probe_video_access
from voxpress.pipeline.youtube_ytdlp import YouTubeExtractError, probe_video_metadata_for_cookie_test
from voxpress.prompts import DEFAULT_CORRECTOR_TEMPLATE
from voxpress.runtime_settings import (
    build_dashscope_runtime_settings,
    build_oss_runtime_settings,
    build_prompt_runtime_settings,
    build_topic_taxonomy_runtime_settings,
)
from voxpress.schemas import (
    ArticleSettings,
    CookieSettings,
    CorrectorSettings,
    DashScopeSettingsOut,
    LlmSettings,
    OssSettingsOut,
    PromptSettings,
    SettingsOut,
    SettingsPatch,
    StorageSettings,
    TopicTaxonomySettings,
    WhisperSettings,
    YouTubeProxySettings,
)

router = APIRouter(prefix="/api", tags=["settings"])
_COOKIE_TEST_FALLBACK_SEC_UID = "MS4wLjABAAAAT4iFvoTOtlJCDuUMyovtft5NLQOnQZ-HECl7EGe-rT0"
_YOUTUBE_COOKIE_TEST_FALLBACK_VIDEO = "https://www.youtube.com/watch?v=KJ-efTR7WxM"
_RECOMMENDED_LLM_MODELS = (
    "qwen3.6-plus",
    "qwen3.6-plus-2026-04-02",
    "qwen-plus",
    "qwen-plus-latest",
    "qwen-turbo",
    "qwen-flash",
    "qwen-max",
    "qwen-max-latest",
)
_RECOMMENDED_CORRECTOR_MODELS = (
    "qwen-turbo-latest",
    "qwen-turbo",
    "qwen-flash",
    "qwen3.6-plus",
    "qwen3.6-plus-2026-04-02",
    "qwen-plus",
)
_RECOMMENDED_ASR_MODELS = (
    "qwen3-asr-flash-filetrans",
)


_DEFAULTS: SettingsOut = SettingsOut(
    llm=LlmSettings(),
    whisper=WhisperSettings(),
    corrector=CorrectorSettings(template=DEFAULT_CORRECTOR_TEMPLATE),
    article=ArticleSettings(),
    prompt=PromptSettings(),
    topic_taxonomy=TopicTaxonomySettings(),
    cookie=CookieSettings(),
    youtube_cookie=CookieSettings(),
    youtube_proxy=YouTubeProxySettings(),
    dashscope=DashScopeSettingsOut(),
    oss=OssSettingsOut(),
    storage=StorageSettings(),
)


async def _load(s: AsyncSession) -> SettingsOut:
    rows = (await s.scalars(select(SettingEntry))).all()
    data: dict = _DEFAULTS.model_dump()
    for row in rows:
        if row.key in data:
            data[row.key] = {**data[row.key], **dict(row.value)}
    return SettingsOut.model_validate(_normalize_settings_dict(data))


async def _save(s: AsyncSession, key: str, value: dict) -> None:
    value = _prepare_settings_value_for_storage(key, value)
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
    merged = current.model_dump(mode="json")  # datetimes -> ISO strings for JSONB
    updates = payload.model_dump(exclude_none=True, mode="json")
    for key, value in updates.items():
        merged[key] = {**merged[key], **value}
    merged = _normalize_settings_dict(merged)
    for k in updates:
        v = dict(merged[k])
        # Preserve secret fields that SettingsOut intentionally omits.
        existing = await s.get(SettingEntry, k)
        if existing:
            preserved = {pk: pv for pk, pv in existing.value.items() if pk not in v}
            v = {**v, **preserved}
        merged[k] = v
        await _save(s, k, v)
    await s.commit()
    return await _load(s)


@router.post("/cookie")
async def post_cookie(
    file: UploadFile = File(...), s: AsyncSession = Depends(get_session)
) -> dict:
    filename = (file.filename or "").strip()
    if not filename:
        raise InvalidCookieFile("请选择要导入的 cookies.txt 文件")
    if not filename.lower().endswith(".txt"):
        raise InvalidCookieFile("仅支持导入 cookies.txt / .txt 文件")

    text = _sanitize_cookie_payload(
        _decode_cookie_file(await file.read()),
        domains=("douyin.com",),
        missing_message="上传的 cookies.txt 里没有检测到 douyin.com 的 Cookie。",
    ).strip()
    if not text:
        raise InvalidCookieFile("cookies.txt 文件为空")
    if not _looks_like_cookie_payload(text):
        raise InvalidCookieFile("请上传浏览器导出的 cookies.txt 文件")

    existing = await s.get(SettingEntry, "cookie")
    current = dict(existing.value) if existing else {}
    await _save(
        s,
        "cookie",
        {
            **current,
            "text": text,
            "source_name": filename,
        },
    )
    await s.commit()
    return {"status": "ok", "source_name": filename}


@router.post("/youtube-cookie")
async def post_youtube_cookie(
    file: UploadFile = File(...), s: AsyncSession = Depends(get_session)
) -> dict:
    filename = (file.filename or "").strip()
    if not filename:
        raise InvalidCookieFile("请选择要导入的 YouTube cookies.txt 文件")
    if not filename.lower().endswith(".txt"):
        raise InvalidCookieFile("仅支持导入 cookies.txt / .txt 文件")

    text = _sanitize_cookie_payload(
        _decode_cookie_file(await file.read()),
        domains=("youtube.com", "google.com"),
        missing_message="上传的 cookies.txt 里没有检测到 youtube.com / google.com 的 Cookie。",
    ).strip()
    if not text:
        raise InvalidCookieFile("cookies.txt 文件为空")
    if not _looks_like_cookie_payload(text):
        raise InvalidCookieFile("请上传浏览器导出的 cookies.txt 文件")

    existing = await s.get(SettingEntry, "youtube_cookie")
    current = dict(existing.value) if existing else {}
    await _save(
        s,
        "youtube_cookie",
        {
            **current,
            "text": text,
            "source_name": filename,
            "status": "missing",
            "last_tested_at": None,
        },
    )
    await s.commit()
    return {"status": "ok", "source_name": filename}


@router.post("/youtube-cookie/test")
async def test_youtube_cookie(s: AsyncSession = Depends(get_session)) -> dict:
    row = await s.get(SettingEntry, "youtube_cookie")
    current = dict(row.value) if row else {}
    cookie_text = str(current.get("text") or "").strip()
    if not cookie_text:
        raise CookieMissing("未导入 YouTube Cookie")

    checked_at = datetime.now(tz=timezone.utc)
    sample_video_url = await _pick_youtube_cookie_test_video(s) or _YOUTUBE_COOKIE_TEST_FALLBACK_VIDEO
    try:
        video = await probe_video_metadata_for_cookie_test(sample_video_url, cookie_text=cookie_text)
    except YouTubeExtractError as e:
        status = "expired" if _looks_like_youtube_auth_error(str(e)) else "ok"
        await _save_cookie_test_result(s, current, key="youtube_cookie", status=status, checked_at=checked_at)
        await s.commit()
        if status == "expired":
            raise CookieInvalid(str(e)) from e
        return {
            "status": "ok",
            "detail": f"YouTube Cookie 已保存；样本元信息探测遇到非登录错误: {str(e)[:160]}",
        }
    except Exception as e:
        status = "expired" if _looks_like_youtube_auth_error(str(e)) else "ok"
        await _save_cookie_test_result(s, current, key="youtube_cookie", status=status, checked_at=checked_at)
        await s.commit()
        if status == "expired":
            raise CookieInvalid(str(e)) from e
        return {
            "status": "ok",
            "detail": f"YouTube Cookie 已保存；样本元信息探测遇到非登录错误: {str(e)[:160]}",
        }

    await _save_cookie_test_result(s, current, key="youtube_cookie", status="ok", checked_at=checked_at)
    await s.commit()
    return {
        "status": "ok",
        "detail": "YouTube 登录 Cookie 可用于读取视频元数据",
        "video_sample": video.title,
    }


@router.post("/cookie/test")
async def test_cookie(s: AsyncSession = Depends(get_session)) -> dict:
    row = await s.get(SettingEntry, "cookie")
    current = dict(row.value) if row else {}
    cookie_text = str(current.get("text") or "").strip()
    if not cookie_text:
        raise CookieMissing("未导入 Cookie")

    checked_at = datetime.now(tz=timezone.utc)
    sample_sec_uid = await _pick_cookie_test_creator(s)
    sample_video_url = await _pick_cookie_test_video(s)

    try:
        page = await fetch_creator_page(sample_sec_uid, cookie_text=cookie_text, max_videos=1)
        if page.videos:
            sample_video_url = page.videos[0].source_url
        if not sample_video_url:
            raise CookieInvalid("Cookie 已通过创作者主页抓取，但当前没有可用于验证的视频样本。")
        video_probe = await probe_video_access(sample_video_url, cookie_text=cookie_text)
    except CookieInvalid:
        await _save_cookie_test_result(s, current, status="expired", checked_at=checked_at)
        await s.commit()
        raise
    except Exception as e:
        await _save_cookie_test_result(s, current, status="expired", checked_at=checked_at)
        await s.commit()
        raise CookieInvalid(str(e)) from e

    await _save_cookie_test_result(s, current, status="ok", checked_at=checked_at)
    await s.commit()
    return {
        "status": "ok",
        "detail": "创作者主页抓取和视频下载探测都通过",
        "creator_sample": page.creator.name,
        "video_sample": video_probe["title"],
    }


@router.get("/models")
async def list_models() -> dict:
    return {
        "llm": list(_RECOMMENDED_LLM_MODELS),
        "corrector": list(_RECOMMENDED_CORRECTOR_MODELS),
        "transcribe": list(_RECOMMENDED_ASR_MODELS),
    }


def _normalize_settings_dict(data: dict) -> dict:
    normalized = dict(data)

    llm = {**_DEFAULTS.llm.model_dump(), **dict(normalized.get("llm") or {})}
    llm["backend"] = "dashscope"
    llm_model = str(llm.get("model") or "").strip()
    if not llm_model:
        llm["model"] = _DEFAULTS.llm.model
    else:
        llm["model"] = llm_model
    normalized["llm"] = llm

    whisper = {**_DEFAULTS.whisper.model_dump(), **dict(normalized.get("whisper") or {})}
    whisper_model = str(whisper.get("model") or "").strip()
    if not whisper_model:
        whisper["model"] = _DEFAULTS.whisper.model
    else:
        whisper["model"] = whisper_model
    if whisper.get("language") not in {"zh", "auto"}:
        whisper["language"] = _DEFAULTS.whisper.language
    whisper["enable_initial_prompt"] = bool(whisper.get("enable_initial_prompt", True))
    normalized["whisper"] = whisper

    corrector = {**_DEFAULTS.corrector.model_dump(), **dict(normalized.get("corrector") or {})}
    corrector_model = str(corrector.get("model") or "").strip()
    if not corrector_model:
        corrector["model"] = _DEFAULTS.corrector.model
    else:
        corrector["model"] = corrector_model
    normalized["corrector"] = corrector

    article = {**_DEFAULTS.article.model_dump(), **dict(normalized.get("article") or {})}
    normalized["article"] = article

    prompt = {**_DEFAULTS.prompt.model_dump(), **dict(normalized.get("prompt") or {})}
    prompt_runtime = build_prompt_runtime_settings(prompt)
    prompt["version"] = prompt_runtime.version
    prompt["template"] = prompt_runtime.organizer_template
    prompt["background_notes_template"] = prompt_runtime.background_notes_template
    normalized["prompt"] = prompt

    topic_taxonomy = {
        **_DEFAULTS.topic_taxonomy.model_dump(),
        **dict(normalized.get("topic_taxonomy") or {}),
    }
    topic_taxonomy_runtime = build_topic_taxonomy_runtime_settings(topic_taxonomy)
    topic_taxonomy["version"] = topic_taxonomy_runtime.version
    topic_taxonomy["taxonomy"] = topic_taxonomy_runtime.taxonomy
    topic_taxonomy["synonyms"] = topic_taxonomy_runtime.synonyms
    normalized["topic_taxonomy"] = topic_taxonomy

    cookie = {**_DEFAULTS.cookie.model_dump(mode="json"), **dict(normalized.get("cookie") or {})}
    normalized["cookie"] = cookie

    youtube_cookie = {
        **_DEFAULTS.youtube_cookie.model_dump(mode="json"),
        **dict(normalized.get("youtube_cookie") or {}),
    }
    normalized["youtube_cookie"] = youtube_cookie

    youtube_proxy = {
        **_DEFAULTS.youtube_proxy.model_dump(mode="json"),
        **dict(normalized.get("youtube_proxy") or {}),
    }
    youtube_proxy["url"] = str(youtube_proxy.get("url") or "").strip()
    normalized["youtube_proxy"] = youtube_proxy

    dashscope = {**_DEFAULTS.dashscope.model_dump(), **dict(normalized.get("dashscope") or {})}
    dashscope_runtime = build_dashscope_runtime_settings(dashscope)
    dashscope["base_url"] = dashscope_runtime.chat_base_url
    dashscope["configured"] = dashscope_runtime.enabled
    normalized["dashscope"] = dashscope

    oss = {**_DEFAULTS.oss.model_dump(), **dict(normalized.get("oss") or {})}
    oss_runtime = build_oss_runtime_settings(oss)
    oss["configured"] = oss_runtime.enabled
    oss["region"] = oss_runtime.region or None
    oss["endpoint"] = oss_runtime.endpoint or None
    oss["bucket"] = oss_runtime.bucket or None
    normalized["oss"] = oss

    storage = {**_DEFAULTS.storage.model_dump(), **dict(normalized.get("storage") or {})}
    normalized["storage"] = storage
    return normalized


def _prepare_settings_value_for_storage(key: str, value: dict) -> dict:
    raw = dict(value or {})
    if key == "dashscope":
        allowed = ("api_key", "base_url")
        return {field: raw[field] for field in allowed if field in raw}
    if key == "oss":
        allowed = ("region", "endpoint", "bucket", "access_key_id", "access_key_secret")
        return {field: raw[field] for field in allowed if field in raw}
    if key == "prompt":
        runtime = build_prompt_runtime_settings(raw)
        return {
            "version": runtime.version,
            "template": runtime.organizer_template,
            "background_notes_template": runtime.background_notes_template,
        }
    if key == "topic_taxonomy":
        runtime = build_topic_taxonomy_runtime_settings(raw)
        return {
            "version": runtime.version,
            "taxonomy": runtime.taxonomy,
            "synonyms": runtime.synonyms,
        }
    return raw


async def _pick_cookie_test_creator(s: AsyncSession) -> str:
    sec_uid = await s.scalar(
        select(Creator.external_id)
        .where(Creator.platform == "douyin")
        .order_by(Creator.followers.desc(), Creator.id.asc())
        .limit(1)
    )
    return str(sec_uid or _COOKIE_TEST_FALLBACK_SEC_UID)


async def _pick_cookie_test_video(s: AsyncSession) -> str | None:
    source_url = await s.scalar(
        select(Video.source_url)
        .join(Creator, Creator.id == Video.creator_id)
        .where(Creator.platform == "douyin")
        .order_by(Video.published_at.desc(), Video.id.asc())
        .limit(1)
    )
    if source_url is None:
        return None
    return str(source_url)


async def _pick_youtube_cookie_test_video(s: AsyncSession) -> str | None:
    source_url = await s.scalar(
        select(Video.source_url)
        .join(Creator, Creator.id == Video.creator_id)
        .where(Creator.platform == "youtube")
        .order_by(Video.published_at.desc(), Video.id.asc())
        .limit(1)
    )
    if source_url is None:
        return None
    return str(source_url)


async def _save_cookie_test_result(
    s: AsyncSession,
    current: dict,
    *,
    key: str = "cookie",
    status: str,
    checked_at: datetime,
) -> None:
    await _save(
        s,
        key,
        {
            **current,
            "status": status,
            "last_tested_at": checked_at.isoformat(),
        },
    )


def _decode_cookie_file(raw: bytes) -> str:
    if not raw:
        return ""
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise InvalidCookieFile("cookies.txt 文件编码无法识别，请重新导出后再试。")


def _looks_like_cookie_payload(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    if normalized.startswith("# Netscape"):
        return True
    if "\t" in normalized:
        return True
    low = normalized.lower()
    return "=" in normalized and (";" in normalized or "sessionid" in low or "ttwid" in low)


def _looks_like_youtube_auth_error(message: str) -> bool:
    low = message.lower()
    return any(
        marker in low
        for marker in (
            "sign in",
            "not a bot",
            "cookies",
            "cookie",
            "login",
            "authentication",
            "private video",
            "members-only",
            "age-restricted",
        )
    )


def _sanitize_cookie_payload(
    text: str,
    *,
    domains: tuple[str, ...] = ("douyin.com",),
    missing_message: str = "上传的 cookies.txt 里没有检测到 douyin.com 的 Cookie。",
) -> str:
    normalized = text.strip()
    if not normalized:
        return ""
    if not (normalized.startswith("# Netscape") or "\t" in normalized):
        return normalized

    kept: list[str] = []
    saw_cookie_row = False
    for raw in normalized.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            kept.append(raw)
            continue
        parts = raw.split("\t")
        if len(parts) < 7:
            continue
        domain = parts[0].strip().lower()
        if not any(item in domain for item in domains):
            continue
        kept.append(raw)
        saw_cookie_row = True

    if not saw_cookie_row:
        raise InvalidCookieFile(missing_message)
    return "\n".join(kept).strip() + "\n"
