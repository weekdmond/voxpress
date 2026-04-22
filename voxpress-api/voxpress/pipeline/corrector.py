from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from voxpress.config import settings
from voxpress.prompts import DEFAULT_CORRECTOR_TEMPLATE

logger = logging.getLogger(__name__)


class CorrectionTooAggressive(ValueError):
    pass


def split_correction_chunks(text: str, *, max_chars: int = 3500) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [normalized]

    paragraphs = [part.strip() for part in normalized.split("\n") if part.strip()]
    if not paragraphs:
        return [normalized]

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n{paragraph}"
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = paragraph
            continue
        if not current and len(paragraph) > max_chars:
            for i in range(0, len(paragraph), max_chars):
                chunks.append(paragraph[i : i + max_chars])
            current = ""
            continue
        current = candidate
    if current:
        chunks.append(current)
    return chunks or [normalized]


def normalize_correction_changes(raw: Any, *, original: str) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return normalized
    for item in raw:
        if not isinstance(item, dict):
            continue
        source = str(item.get("from") or "").strip()
        target = str(item.get("to") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if not source or not target or source == target:
            continue
        if source not in original:
            continue
        normalized.append({"from": source, "to": target, "reason": reason})
    return normalized


def validate_correction_result(
    original: str,
    corrected: str,
    changes: list[dict[str, str]],
) -> tuple[str, list[dict[str, str]]]:
    source = original.strip()
    target = corrected.strip()
    if not source:
        return target, []
    if not target:
        raise CorrectionTooAggressive("empty corrected text")

    ratio = len(target) / max(len(source), 1)
    if not (0.85 <= ratio <= 1.15):
        raise CorrectionTooAggressive(f"ratio={ratio:.3f}")

    return target, normalize_correction_changes(changes, original=original)


class OllamaCorrector:
    def __init__(self, *, model: str, template: str = "", base_url: str | None = None) -> None:
        self.model = model
        self.template = template or DEFAULT_CORRECTOR_TEMPLATE
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")

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

        for chunk in chunks:
            payload = await self._correct_chunk(chunk, title_hint=title_hint, creator_hint=creator_hint)
            corrected, changes = validate_correction_result(
                chunk,
                str(payload.get("corrected") or chunk),
                payload.get("changes") or [],
            )
            corrected_parts.append(corrected)
            merged_changes.extend(changes)

        return {
            "corrected_text": "\n".join(part for part in corrected_parts if part).strip(),
            "corrections": merged_changes,
            "correction_status": "ok",
            "corrector_model": self.model,
        }

    async def _correct_chunk(
        self,
        chunk: str,
        *,
        title_hint: str,
        creator_hint: str,
    ) -> dict[str, Any]:
        user = (
            "视频上下文（仅供理解语境，不要抄进输出）：\n"
            f"标题：{title_hint}\n"
            f"博主：{creator_hint}\n\n"
            "需要校对的转写文本：\n"
            f"{chunk}\n\n"
            "只输出 JSON，不要任何解释。"
        )
        async with httpx.AsyncClient(timeout=300.0, trust_env=False) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": self.template},
                        {"role": "user", "content": user},
                    ],
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0.1, "num_ctx": 8192},
                },
            )
            response.raise_for_status()
            payload = response.json()

        raw = str(payload.get("message", {}).get("content", "")).strip()
        data = _loose_json(raw)
        if not data:
            logger.warning("corrector returned empty payload (first 200 chars): %s", raw[:200])
        return data


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
    for idx in range(start, len(raw)):
        if raw[idx] == "{":
            depth += 1
        elif raw[idx] == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(raw[start : idx + 1])
                except json.JSONDecodeError:
                    return {}
                return parsed if isinstance(parsed, dict) else {}
    return {}
