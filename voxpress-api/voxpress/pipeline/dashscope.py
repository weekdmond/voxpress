from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from voxpress.config import settings
from voxpress.media_store import MediaStoreError, audio_object_key, media_store
from voxpress.pipeline.corrector import (
    split_correction_chunks,
    validate_correction_result,
)
from voxpress.pipeline.protocols import LLMBackend, TranscriptResult, Transcriber
from voxpress.prompts import (
    DEFAULT_BACKGROUND_NOTES_TEMPLATE,
    DEFAULT_CORRECTOR_TEMPLATE,
    DEFAULT_ORGANIZER_TEMPLATE,
)
from voxpress.task_metrics import llm_usage_from_dashscope, merge_usage

logger = logging.getLogger(__name__)

DEFAULT_LLM_MODELS = settings.dashscope_llm_models_list
DEFAULT_CORRECTOR_MODELS = settings.dashscope_corrector_models_list
DEFAULT_ASR_MODELS = settings.dashscope_asr_models_list


class DashScopeError(RuntimeError):
    pass


@dataclass(slots=True)
class DashScopeChatResult:
    data: dict[str, Any]
    usage: dict[str, int | float]


class DashScopeChatClient:
    def __init__(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = (api_key or settings.dashscope_api_key or "").strip()
        self.base_url = (base_url or settings.dashscope_chat_base_url).rstrip("/")
        if not self.api_key:
            raise DashScopeError("DashScope API Key 未配置")

    async def chat_json_result(
        self,
        *,
        model: str,
        system: str,
        user: str,
        temperature: float,
        timeout_sec: float,
    ) -> DashScopeChatResult:
        async with httpx.AsyncClient(timeout=timeout_sec, trust_env=False) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "response_format": {"type": "json_object"},
                    "enable_thinking": False,
                    "temperature": temperature,
                    "stream": False,
                },
            )
            _raise_dashscope_http_error(response, prefix="DashScope 对话请求失败")
            payload = response.json()
        raw = str(((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        data = _loose_json(raw)
        if not data:
            logger.warning("DashScope returned empty/non-JSON payload (first 200 chars): %s", raw[:200])
        usage = llm_usage_from_dashscope(model, payload.get("usage"))
        return DashScopeChatResult(data=data, usage=usage)

    async def chat_json(
        self,
        *,
        model: str,
        system: str,
        user: str,
        temperature: float,
        timeout_sec: float,
    ) -> dict[str, Any]:
        result = await self.chat_json_result(
            model=model,
            system=system,
            user=user,
            temperature=temperature,
            timeout_sec=timeout_sec,
        )
        return result.data


class DashScopeLLM(LLMBackend):
    def __init__(self, *, model: str | None = None) -> None:
        self.model = model or settings.dashscope_default_llm_model
        self.client = DashScopeChatClient()

    async def organize(
        self,
        *,
        transcript: str,
        title_hint: str,
        creator_hint: str,
        prompt_template: str,
        duration_sec: int | None = None,
    ) -> dict[str, Any]:
        system = prompt_template or DEFAULT_ORGANIZER_TEMPLATE
        min_output_chars = _min_organized_chars(transcript, duration_sec=duration_sec)
        result = await self.client.chat_json_result(
            model=self.model,
            system=system,
            user=_organize_user_prompt(
                transcript=transcript,
                title_hint=title_hint,
                creator_hint=creator_hint,
                min_output_chars=min_output_chars,
                duration_sec=duration_sec,
            ),
            temperature=0.3,
            timeout_sec=600.0,
        )
        organized = _normalize_organized_payload(result.data, title_hint=title_hint)
        usage = result.usage
        if _is_overcompressed_article(
            transcript=transcript,
            content_md=organized["content_md"],
            duration_sec=duration_sec,
        ):
            retry = await self.client.chat_json_result(
                model=self.model,
                system=system,
                user=_organize_user_prompt(
                    transcript=transcript,
                    title_hint=title_hint,
                    creator_hint=creator_hint,
                    min_output_chars=min_output_chars,
                    duration_sec=duration_sec,
                    retry=True,
                ),
                temperature=0.2,
                timeout_sec=600.0,
            )
            usage = merge_usage(usage, retry.usage)
            retry_organized = _normalize_organized_payload(retry.data, title_hint=title_hint)
            if _organized_score(retry_organized["content_md"]) >= _organized_score(organized["content_md"]):
                organized = retry_organized
        organized["_usage"] = usage
        organized["_primary_model"] = self.model
        return organized

    async def annotate_background(
        self,
        *,
        transcript: str,
        title_hint: str,
        creator_hint: str,
        article_title: str,
        article_summary: str,
    ) -> dict[str, Any] | None:
        user = (
            f"视频平台标题:{title_hint}\n"
            f"作者:{creator_hint}\n"
            f"整理后文章标题:{article_title}\n"
            f"整理后文章摘要:{article_summary}\n\n"
            "【原始逐字稿】\n"
            f"{transcript}\n\n"
            "请只输出背景注 JSON。若没有高把握内容，可输出 {\"aliases\": []}。"
        )
        result = await self.client.chat_json_result(
            model=self.model,
            system=DEFAULT_BACKGROUND_NOTES_TEMPLATE,
            user=user,
            temperature=0.1,
            timeout_sec=180.0,
        )
        notes = _normalize_background_notes(result.data)
        if notes is not None:
            notes["_usage"] = result.usage
            notes["_primary_model"] = self.model
        return notes


class DashScopeCorrector:
    def __init__(
        self,
        *,
        model: str,
        template: str = "",
        max_attempts: int = 3,
        retry_base_delay_sec: float = 1.0,
    ) -> None:
        self.model = model
        self.template = template or DEFAULT_CORRECTOR_TEMPLATE
        self.client = DashScopeChatClient()
        self.max_attempts = max(1, max_attempts)
        self.retry_base_delay_sec = max(0.0, retry_base_delay_sec)

    async def correct(
        self,
        *,
        text: str,
        title_hint: str,
        creator_hint: str,
    ) -> dict[str, Any]:
        chunks = split_correction_chunks(text)
        corrected_parts: list[str] = []
        merged_changes: list[dict[str, str]] = []
        usages: list[dict[str, int | float]] = []
        for chunk in chunks:
            payload = await self._correct_chunk(chunk, title_hint=title_hint, creator_hint=creator_hint)
            corrected, changes = validate_correction_result(
                chunk,
                str(payload.get("corrected") or chunk),
                payload.get("changes") or [],
            )
            corrected_parts.append(corrected)
            merged_changes.extend(changes)
            if payload.get("_usage"):
                usages.append(payload["_usage"])
        usage = merge_usage(*usages)
        return {
            "corrected_text": "\n".join(part for part in corrected_parts if part).strip(),
            "corrections": merged_changes,
            "correction_status": "ok",
            "corrector_model": self.model,
            "_usage": usage,
        }

    async def _correct_chunk(self, chunk: str, *, title_hint: str, creator_hint: str) -> dict[str, Any]:
        user = (
            "视频上下文（仅供理解语境，不要抄进输出）：\n"
            f"标题：{title_hint}\n"
            f"博主：{creator_hint}\n\n"
            "需要校对的转写文本：\n"
            f"{chunk}\n\n"
            "只输出 JSON，不要任何解释。"
        )
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = await self.client.chat_json_result(
                    model=self.model,
                    system=self.template,
                    user=user,
                    temperature=0.1,
                    timeout_sec=300.0,
                )
            except Exception as exc:
                if attempt >= self.max_attempts or not _is_retryable_corrector_error(exc):
                    raise
                delay = self.retry_base_delay_sec * (2 ** (attempt - 1))
                logger.warning(
                    "corrector request failed (attempt %s/%s), retrying in %.1fs: %s",
                    attempt,
                    self.max_attempts,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
                continue
            payload = dict(result.data)
            payload["_usage"] = result.usage
            return payload
        raise AssertionError("unreachable")


class DashScopeFileTranscriber(Transcriber):
    def __init__(self, *, model: str | None = None) -> None:
        self.model = model or settings.dashscope_default_asr_model
        self.api_key = (settings.dashscope_api_key or "").strip()
        self.api_base_url = settings.dashscope_api_base_url.rstrip("/")
        if not self.api_key:
            raise DashScopeError("DashScope API Key 未配置")

    async def transcribe(
        self,
        audio_path: Path,
        language: str = "zh",
        initial_prompt: str | None = None,
    ) -> TranscriptResult:
        if not media_store.enabled:
            raise DashScopeError("Qwen3-ASR-Flash-Filetrans 需要已配置 OSS 才能提交音频文件 URL")
        if not audio_path.exists():
            raise DashScopeError(f"音频文件不存在: {audio_path}")

        try:
            object_key = await media_store.upload_file(
                audio_path,
                object_key=audio_object_key(audio_path.stem, audio_path),
            )
        except MediaStoreError as exc:
            raise DashScopeError(f"上传转写音频到 OSS 失败: {exc}") from exc
        if not object_key:
            raise DashScopeError("OSS 音频对象键为空，无法提交 ASR 任务")
        file_url = await media_store.sign_url(object_key)

        task_id = await self._submit(file_url=file_url, language=language, initial_prompt=initial_prompt)
        result_url = await self._wait_result_url(task_id)
        async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
            response = await client.get(result_url)
            _raise_dashscope_http_error(response, prefix="下载 ASR 结果失败")
            payload = response.json()
        return _parse_asr_result(payload)

    async def _submit(
        self,
        *,
        file_url: str,
        language: str,
        initial_prompt: str | None,
    ) -> str:
        parameters: dict[str, Any] = {
            "channel_id": [0],
            "enable_itn": False,
            "enable_words": False,
        }
        if language and language != "auto":
            parameters["language"] = language
        if initial_prompt:
            parameters["corpus"] = {"text": initial_prompt[:200]}

        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            response = await client.post(
                f"{self.api_base_url}/services/audio/asr/transcription",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "X-DashScope-Async": "enable",
                },
                json={
                    "model": self.model,
                    "input": {"file_url": file_url},
                    "parameters": parameters,
                },
            )
            _raise_dashscope_http_error(response, prefix="提交 ASR 任务失败")
            payload = response.json()
        task_id = str(((payload.get("output") or {}).get("task_id")) or "").strip()
        if not task_id:
            raise DashScopeError(f"ASR 提交成功但未返回 task_id: {payload}")
        return task_id

    async def _wait_result_url(self, task_id: str) -> str:
        deadline = asyncio.get_running_loop().time() + settings.dashscope_asr_timeout_sec
        last_status = "PENDING"
        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            while True:
                response = await client.get(
                    f"{self.api_base_url}/tasks/{task_id}",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "X-DashScope-Async": "enable",
                    },
                )
                _raise_dashscope_http_error(response, prefix="查询 ASR 任务失败")
                payload = response.json()
                output = payload.get("output") or {}
                status = str(output.get("task_status") or "UNKNOWN")
                last_status = status
                if status == "SUCCEEDED":
                    result_url = str(((output.get("result") or {}).get("transcription_url")) or "").strip()
                    if not result_url:
                        raise DashScopeError(f"ASR 成功但缺少 transcription_url: {payload}")
                    return result_url
                if status == "FAILED":
                    code = str(output.get("code") or "").strip()
                    message = str(output.get("message") or "未知错误").strip()
                    raise DashScopeError(f"ASR 任务失败: {code or message}")
                if asyncio.get_running_loop().time() >= deadline:
                    raise DashScopeError(f"ASR 任务超时: {task_id} ({last_status})")
                await asyncio.sleep(settings.dashscope_asr_poll_interval_sec)


def _loose_json(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    if start == -1:
        return {}
    depth = 0
    for index in range(start, len(raw)):
        char = raw[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(raw[start : index + 1])
                except json.JSONDecodeError:
                    return {}
                return parsed if isinstance(parsed, dict) else {}
    return {}


def _normalize_background_notes(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    aliases_raw = raw.get("aliases") or []
    aliases: list[dict[str, str]] = []
    seen_terms: set[str] = set()
    if isinstance(aliases_raw, list):
        for item in aliases_raw:
            if not isinstance(item, dict):
                continue
            term = str(item.get("term") or "").strip()
            refers_to = str(item.get("refers_to") or "").strip()
            confidence = str(item.get("confidence") or "").strip().lower()
            if not term or not refers_to:
                continue
            normalized_confidence = confidence if confidence in {"high", "medium", "low"} else "medium"
            if normalized_confidence == "low":
                continue
            term_key = term.casefold()
            if term_key in seen_terms:
                continue
            seen_terms.add(term_key)
            aliases.append(
                {
                    "term": term,
                    "refers_to": refers_to,
                    "confidence": normalized_confidence,
                }
            )
    context = str(raw.get("context") or "").strip()
    if _looks_like_meta_context(context):
        context = ""
    if not aliases and not context:
        return None
    result: dict[str, Any] = {"aliases": aliases}
    if context:
        result["context"] = context
    return result


def _looks_like_meta_context(text: str) -> bool:
    if not text:
        return False
    lowered = text.strip()
    if len(lowered) > 90:
        return True
    if any(sep in lowered for sep in ("；", ";", "\n")):
        return True
    markers = (
        "全文",
        "通篇",
        "本文",
        "实则",
        "聚焦",
        "方法论",
        "引子",
        "类比",
        "服务于",
        "并非",
        "不是在",
        "作者借",
        "借此",
    )
    score = sum(1 for marker in markers if marker in lowered)
    return score >= 2


def _visible_text_len(text: str) -> int:
    if not text:
        return 0
    normalized = re.sub(r"[#>*`_\-\n\r\t ]+", "", text)
    return len(normalized)


def _min_organized_chars(transcript: str, *, duration_sec: int | None = None) -> int:
    transcript_len = _visible_text_len(transcript)
    if duration_sec and duration_sec >= 3600:
        ratio = 0.18
        floor = 3200
    elif duration_sec and duration_sec >= 1800:
        ratio = 0.16
        floor = 2400
    elif duration_sec and duration_sec >= 600:
        ratio = 0.14
        floor = 1600
    else:
        ratio = 0.12
        floor = 900
    return max(floor, int(transcript_len * ratio))


def _is_overcompressed_article(
    *,
    transcript: str,
    content_md: str,
    duration_sec: int | None = None,
) -> bool:
    content_len = _visible_text_len(content_md)
    min_required = _min_organized_chars(transcript, duration_sec=duration_sec)
    return content_len < min_required


def _organized_score(content_md: str) -> tuple[int, int]:
    content_len = _visible_text_len(content_md)
    section_count = content_md.count("\n## ")
    return (content_len, section_count)


def _organize_user_prompt(
    *,
    transcript: str,
    title_hint: str,
    creator_hint: str,
    min_output_chars: int,
    duration_sec: int | None,
    retry: bool = False,
) -> str:
    duration_line = ""
    if duration_sec:
        minutes = max(1, round(duration_sec / 60))
        duration_line = f"视频时长约:{minutes} 分钟\n"
    retry_line = ""
    if retry:
        retry_line = (
            "上一次输出被判定为压缩过头: 只保留了主干,丢失了不少论据、例子和推导。\n"
            "这一次请显著写长,补回关键例证、展开过程和作者的重要原话,不要再输出摘要稿。\n"
        )
    return (
        f"视频平台标题(参考用,不是最终标题):{title_hint}\n"
        f"作者:{creator_hint}\n"
        f"{duration_line}"
        f"逐字稿长度(去空白后):约 {_visible_text_len(transcript)} 字\n"
        f"正文目标:至少写到 {min_output_chars} 字,这不是摘要任务,而是保留原观点和原内容的整理稿。\n"
        "必须保留作者的重要论点、论据、案例、反问、结论;允许适度润色,但不要改变作者原意。\n"
        "如果原文是长直播/长表达,请写成完整长文,不要只保留观点骨架。\n"
        f"{retry_line}\n"
        "【原始逐字稿】\n"
        f"{transcript}\n\n"
        "━━━━━━━━\n"
        "请按系统指令整理成文章,严格以 JSON 返回下面字段:\n"
        "{\n"
        '  "title": "≤30 字。忠于作者实际讨论的内容,陈述式标题。不要问句、不要营销式。",\n'
        '  "summary": "≤60 字,一句话概括作者的核心立场,保留作者语气强度与锋芒,不是中性摘要。",\n'
        '  "content_md": "Markdown 正文。遵循系统指令里的原则、禁止项、结构规范。",\n'
        '  "tags": ["2-4 个中文标签,具体到行业/话题/方法论,不要\'思考\'\'分享\'这种泛词"]'
        "\n"
        "}\n\n"
        "只输出 JSON,不要任何解释或代码围栏。"
    )


def _normalize_organized_payload(data: dict[str, Any], *, title_hint: str) -> dict[str, Any]:
    title = (data.get("title") or title_hint).strip()
    summary = (data.get("summary") or "").strip()
    content_md = _normalize_markdown_output((data.get("content_md") or "").strip())
    tags = data.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    return {
        "title": title,
        "summary": summary,
        "content_md": content_md or f"# {title}\n\n> {summary}",
        "tags": [str(tag)[:16] for tag in tags[:4]],
    }


def _normalize_markdown_output(content: str) -> str:
    if not content:
        return ""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    # Some models return markdown content with literal escape sequences like "\\n"
    # inside JSON strings. Restore them before markdown rendering.
    normalized = (
        normalized.replace("\\\\n", "\n")
        .replace("\\\\t", "    ")
        .replace("\\n", "\n")
        .replace("\\t", "    ")
    )
    normalized = (
        normalized.replace("\\(", "(")
        .replace("\\)", ")")
        .replace("\\[", "[")
        .replace("\\]", "]")
    )
    normalized = re.sub(r"(?m)^\\>\s*", "> ", normalized)
    normalized = re.sub(r"(?m)(^> .+)\n(?!\n|> )", r"\1\n\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _raise_dashscope_http_error(response: httpx.Response, *, prefix: str) -> None:
    if response.is_error:
        detail = response.text.strip().replace("\n", " ")
        raise DashScopeError(f"{prefix}: HTTP {response.status_code} {detail[:400]}")


def _is_retryable_corrector_error(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError)):
        return True
    if isinstance(exc, DashScopeError):
        message = str(exc)
        return any(
            code in message
            for code in (
                "HTTP 408",
                "HTTP 429",
                "HTTP 500",
                "HTTP 502",
                "HTTP 503",
                "HTTP 504",
            )
        )
    return False


def _parse_asr_result(payload: dict[str, Any]) -> TranscriptResult:
    transcripts = payload.get("transcripts") or []
    if not isinstance(transcripts, list) or not transcripts:
        raise DashScopeError("ASR 返回结果缺少 transcripts")
    primary = transcripts[0] if isinstance(transcripts[0], dict) else {}
    raw_text = str(primary.get("text") or "").strip()
    sentences = primary.get("sentences") or []
    segments: list[tuple[int, str]] = []
    if isinstance(sentences, list):
        for item in sentences:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            begin_ms = int(item.get("begin_time") or 0)
            segments.append((max(0, begin_ms // 1000), text))
    if not raw_text:
        raw_text = "\n".join(text for _ts, text in segments).strip()
    if raw_text and not segments:
        segments = [(0, raw_text)]
    return TranscriptResult(segments=segments, raw_text=raw_text)
