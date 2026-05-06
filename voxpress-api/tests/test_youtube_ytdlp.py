from voxpress.pipeline.youtube_ytdlp import (
    _channel_tab_urls,
    _channel_videos_url,
    _looks_like_video_id,
    _parse_compact_count,
)


def test_looks_like_video_id_rejects_channel_id() -> None:
    assert not _looks_like_video_id("UC9cfcOuTT9rYkyUimMjLxuw")


def test_looks_like_video_id_accepts_standard_video_id() -> None:
    assert _looks_like_video_id("KJ-efTR7WxM")


def test_channel_videos_url_adds_videos_tab() -> None:
    assert (
        _channel_videos_url("https://www.youtube.com/@Money_or_Life")
        == "https://www.youtube.com/@Money_or_Life/videos"
    )


def test_channel_videos_url_keeps_existing_tab() -> None:
    assert (
        _channel_videos_url("https://www.youtube.com/@Money_or_Life/videos")
        == "https://www.youtube.com/@Money_or_Life/videos"
    )


def test_channel_tab_urls_include_video_shorts_and_streams() -> None:
    assert _channel_tab_urls("https://www.youtube.com/@Money_or_Life") == [
        "https://www.youtube.com/@Money_or_Life/videos",
        "https://www.youtube.com/@Money_or_Life/shorts",
        "https://www.youtube.com/@Money_or_Life/streams",
    ]


def test_parse_compact_count_handles_youtube_labels() -> None:
    assert _parse_compact_count("249") == 249
    assert _parse_compact_count("7.68万") == 76800
    assert _parse_compact_count("1.2K") == 1200
