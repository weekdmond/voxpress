from voxpress.routers.tasks import _url_kind
from voxpress.url_resolve import extract_douyin_url, normalize_douyin_input


def test_extract_douyin_url_from_share_message() -> None:
    text = "长按复制此条消息，打开抖音搜索，查看TA的更多作品。 https://v.douyin.com/kNzixivkl4A/ "

    assert extract_douyin_url(text) == "https://v.douyin.com/kNzixivkl4A/"


def test_extract_douyin_url_strips_trailing_punctuation() -> None:
    text = "打开抖音看看：https://www.douyin.com/video/7497671502073361704）；"

    assert extract_douyin_url(text) == "https://www.douyin.com/video/7497671502073361704"


def test_normalize_douyin_input_prefers_embedded_url() -> None:
    text = "7.53 复制打开抖音，看看【示例】https://www.douyin.com/user/MS4wLjABAAAA1234567890?from_tab_name=main"

    assert (
        normalize_douyin_input(text)
        == "https://www.douyin.com/user/MS4wLjABAAAA1234567890?from_tab_name=main"
    )


def test_task_url_kind_accepts_share_text_short_link() -> None:
    text = "长按复制此条消息，打开抖音搜索，查看TA的更多作品。 https://v.douyin.com/kNzixivkl4A/ "

    assert _url_kind(text) == "short"
