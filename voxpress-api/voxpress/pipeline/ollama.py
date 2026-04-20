"""Ollama LLMBackend.

Uses the `/api/chat` JSON-mode endpoint; we ask the model to produce a strict
JSON object {title, summary, content_md, tags} and sanitize it before handing
back to the runner (the runner/DB expects `content_html` too, which we
generate via a tiny markdown-ish converter to keep the dependency graph flat).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from voxpress.config import settings
from voxpress.markdown import md_to_html, word_count_cn
from voxpress.pipeline.protocols import LLMBackend

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
        system = (
            prompt_template
            or "你是一位严谨的中文编辑。把下面这段口播转写整理成一篇结构化的文章,保留原作者的语气,消除口头禅和重复。"
        )
        user = (
            f"视频标题提示:{title_hint}\n"
            f"作者:{creator_hint}\n\n"
            f"【原始转写】\n{transcript}\n\n"
            "请输出严格 JSON,字段:title(≤30字)、summary(1句话50字内)、content_md(Markdown 正文,用 ## 分小节,若有名言用 blockquote)、tags(2-4 个中文标签数组)。"
            "不要输出 JSON 以外的任何内容。"
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

        content_html = md_to_html(content_md or summary)
        word_count = word_count_cn(content_md or summary)

        return {
            "title": title,
            "summary": summary,
            "content_md": content_md or f"# {title}\n\n> {summary}",
            "content_html": content_html,
            "word_count": word_count,
            "tags": [str(t)[:16] for t in tags[:4]],
        }


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
