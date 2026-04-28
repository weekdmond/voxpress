from voxpress.routers.articles import _extract_summary_from_markdown, _extract_title_from_markdown


def test_extract_title_from_markdown_prefers_h1() -> None:
    content = "# 新标题\n\n> 一句话摘要\n\n正文第一段"

    assert _extract_title_from_markdown(content) == "新标题"


def test_extract_summary_from_markdown_uses_first_blockquote_block() -> None:
    content = "# 新标题\n\n> 第一句摘要\n> 第二句摘要\n\n正文第一段"

    assert _extract_summary_from_markdown(content) == "第一句摘要 第二句摘要"
