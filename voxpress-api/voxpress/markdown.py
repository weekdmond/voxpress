"""Markdown → HTML helper. One converter, used by pipeline and routers.

We keep this tiny wrapper instead of calling mistune directly so if we ever
swap renderers (e.g. to add sanitization or classes matching the frontend
reader's CSS) it's a single point of change.
"""

from __future__ import annotations

import mistune


_markdown = mistune.create_markdown(
    escape=True,
    plugins=["strikethrough", "footnotes", "table"],
)


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
