from __future__ import annotations

import json
from typing import Any


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
