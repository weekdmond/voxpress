from __future__ import annotations

from voxpress.pipeline.dashscope import (
    _is_overcompressed_article,
    _min_organized_chars,
    _normalize_markdown_output,
    _visible_text_len,
)


def test_visible_text_len_ignores_basic_markdown_noise() -> None:
    text = "## 标题\n\n> 引文\n\n- 列表项"
    assert _visible_text_len(text) == len("标题引文列表项")


def test_long_video_min_output_chars_scales_up() -> None:
    transcript = "甲乙丙丁" * 5000
    assert _min_organized_chars(transcript, duration_sec=3700) >= 3200
    assert _min_organized_chars(transcript, duration_sec=3700) > _min_organized_chars(transcript, duration_sec=500)


def test_one_hour_video_article_of_1600_chars_is_too_short() -> None:
    transcript = "观点展开与案例说明" * 1400
    content_md = "## 小结\n\n" + ("这是摘要稿。" * 150)

    assert _is_overcompressed_article(
        transcript=transcript,
        content_md=content_md,
        duration_sec=3733,
    )


def test_long_video_article_with_enough_detail_is_not_too_short() -> None:
    transcript = "观点展开与案例说明" * 1400
    content_md = "## 第一部分\n\n" + ("这是更完整的整理稿，保留论据、案例和推导。" * 260)

    assert not _is_overcompressed_article(
        transcript=transcript,
        content_md=content_md,
        duration_sec=3733,
    )


def test_normalize_markdown_output_restores_escaped_newlines() -> None:
    raw = "## 标题 \\(副标题\\)\\\\n正文第一段。\\\\n## 第二节\\\\n> 原话"
    normalized = _normalize_markdown_output(raw)

    assert "## 标题 (副标题)\n正文第一段。\n## 第二节\n> 原话" == normalized


def test_normalize_markdown_output_breaks_single_line_blockquote() -> None:
    raw = "## 标题\n> 一句原话\n后面的正文"
    normalized = _normalize_markdown_output(raw)

    assert normalized == "## 标题\n> 一句原话\n\n后面的正文"
