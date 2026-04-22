"""Ollama organizer backend."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from voxpress.config import settings
from voxpress.pipeline.protocols import LLMBackend
from voxpress.prompts import DEFAULT_BACKGROUND_NOTES_TEMPLATE, DEFAULT_ORGANIZER_TEMPLATE

logger = logging.getLogger(__name__)


class OllamaLLM(LLMBackend):
    def __init__(self, model: str = "qwen2.5:72b", base_url: str | None = None) -> None:
        self.model = model
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")

    async def organize(
        self,
        *,
        transcript: str,
        title_hint: str,
        creator_hint: str,
        prompt_template: str,
    ) -> dict[str, Any]:
        system = prompt_template or DEFAULT_ORGANIZER_TEMPLATE
        user = (
            f"视频平台标题(参考用,不是最终标题):{title_hint}\n"
            f"作者:{creator_hint}\n\n"
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

        async with httpx.AsyncClient(timeout=600.0, trust_env=False) as client:
            r = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0.3, "num_ctx": 8192},
                },
            )
            r.raise_for_status()
            payload = r.json()

        raw = payload.get("message", {}).get("content", "").strip()
        data = _loose_json(raw)
        title = (data.get("title") or title_hint).strip()
        summary = (data.get("summary") or "").strip()
        content_md = (data.get("content_md") or "").strip()
        tags = data.get("tags") or []
        if not isinstance(tags, list):
            tags = []

        return {
            "title": title,
            "summary": summary,
            "content_md": content_md or f"# {title}\n\n> {summary}",
            "tags": [str(t)[:16] for t in tags[:4]],
        }

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
        async with httpx.AsyncClient(timeout=180.0, trust_env=False) as client:
            r = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": DEFAULT_BACKGROUND_NOTES_TEMPLATE},
                        {"role": "user", "content": user},
                    ],
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0.1, "num_ctx": 8192},
                },
            )
            r.raise_for_status()
            payload = r.json()

        raw = payload.get("message", {}).get("content", "").strip()
        data = _loose_json(raw)
        return _normalize_background_notes(data)


# ─── helpers ────────────────────────────────────────


def _loose_json(raw: str) -> dict[str, Any]:
    """Ollama `format:"json"` should give us strict JSON, but we keep one
    defensive fallback for when the model slips a code fence in."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Find the widest balanced {...} span. Simple brace counter beats a greedy regex.
    start = raw.find("{")
    if start == -1:
        logger.warning("Ollama returned no JSON (first 200 chars): %s", raw[:200])
        return {}
    depth = 0
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(raw[start : i + 1])
                except json.JSONDecodeError:
                    break
    logger.warning("Ollama returned non-JSON content (first 200 chars): %s", raw[:200])
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
