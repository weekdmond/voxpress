from __future__ import annotations

from voxpress.markdown import append_background_notes_md, render_background_notes_md, strip_background_notes_md


def test_render_background_notes_md_renders_aliases_and_context() -> None:
    md = render_background_notes_md(
        {
            "aliases": [
                {"term": "大A", "refers_to": "A股市场", "confidence": "high"},
                {"term": "老黄", "refers_to": "某政治人物", "confidence": "medium"},
                {"term": "某厂", "refers_to": "某头部互联网公司", "confidence": "low"},
            ],
            "context": "这里补充事件背景，但不改正文。",
        }
    )

    assert "## 背景注" in md
    assert "**代称说明**" in md
    assert "- **大A** = A股市场" in md
    assert "- **老黄** = 某政治人物（中置信度）" in md
    assert "某头部互联网公司" not in md
    assert "**事件背景**" in md
    assert "这里补充事件背景，但不改正文。" in md


def test_append_background_notes_md_keeps_base_content_when_notes_missing() -> None:
    base = "## 正文\n\n这里是文章主体。"

    assert append_background_notes_md(base, None) == base


def test_append_background_notes_md_appends_background_section() -> None:
    base = "## 正文\n\n这里是文章主体。"

    result = append_background_notes_md(
        base,
        {"aliases": [{"term": "老美", "refers_to": "美国", "confidence": "medium"}]},
    )

    assert result.startswith(base)
    assert "## 背景注" in result
    assert "- **老美** = 美国" in result


def test_strip_background_notes_md_removes_generated_suffix() -> None:
    base = "## 正文\n\n这里是文章主体。"
    combined = append_background_notes_md(
        base,
        {"aliases": [{"term": "老美", "refers_to": "美国", "confidence": "medium"}]},
    )

    assert strip_background_notes_md(combined) == base
