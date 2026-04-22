"""Markdown → HTML helper. One converter, used by pipeline and routers.

We keep this tiny wrapper instead of calling mistune directly so if we ever
swap renderers (e.g. to add sanitization or classes matching the frontend
reader's CSS) it's a single point of change.
"""

from __future__ import annotations

from typing import Any

import mistune


_markdown = mistune.create_markdown(
    escape=True,
    plugins=["strikethrough", "footnotes", "table"],
)

BACKGROUND_NOTES_TITLE = "## 背景注"
BACKGROUND_NOTES_INTRO = "> 以下为编辑根据上下文补充，非博主原话。"
BACKGROUND_NOTES_BLOCK = f"{BACKGROUND_NOTES_TITLE}\n\n{BACKGROUND_NOTES_INTRO}"


def md_to_html(md: str) -> str:
    if not md:
        return ""
    html = _markdown(md)
    return html if isinstance(html, str) else str(html)


def word_count_cn(text: str) -> int:
    """Count Han characters (approximate Chinese '字' count); fall back to
    whitespace tokens when there are none."""
    cn = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return cn or len(text.split())


def render_background_notes_md(notes: dict[str, Any] | None) -> str:
    if not notes:
        return ""
    aliases = list(notes.get("aliases") or [])
    context = str(notes.get("context") or "").strip()
    if not aliases and not context:
        return ""

    lines = [
        BACKGROUND_NOTES_TITLE,
        "",
        BACKGROUND_NOTES_INTRO,
    ]

    if aliases:
        lines.extend(["", "**代称说明**"])
        for alias in aliases:
            if not isinstance(alias, dict):
                continue
            term = str(alias.get("term") or "").strip()
            refers_to = str(alias.get("refers_to") or "").strip()
            confidence = str(alias.get("confidence") or "").strip().lower()
            if not term or not refers_to:
                continue
            if confidence == "low":
                continue
            suffix = "（中置信度）" if confidence == "medium" else ""
            lines.append(f"- **{term}** = {refers_to}{suffix}")

    if context:
        lines.extend(["", "**事件背景**", context])

    return "\n".join(lines).strip()


def append_background_notes_md(content_md: str, notes: dict[str, Any] | None) -> str:
    notes_md = render_background_notes_md(notes)
    base = strip_background_notes_md(content_md)
    if not notes_md:
        return base
    if not base:
        return notes_md
    return f"{base}\n\n{notes_md}"


def strip_background_notes_md(content_md: str) -> str:
    base = content_md.strip()
    if not base:
        return ""
    block_with_gap = f"\n\n{BACKGROUND_NOTES_BLOCK}"
    if block_with_gap in base:
        return base.split(block_with_gap, 1)[0].rstrip()
    if base.startswith(BACKGROUND_NOTES_BLOCK):
        return ""
    return base
