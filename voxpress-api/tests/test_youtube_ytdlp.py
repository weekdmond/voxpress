from voxpress.pipeline.youtube_ytdlp import (
    YouTubeExtractError,
    YouTubeExtractor,
    _channel_tab_urls,
    _channel_videos_url,
    _looks_like_video_id,
    _parse_compact_count,
    _write_youtube_cookie_file,
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


async def test_youtube_extractor_downloads_audio_in_extract_stage(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_extract_audio(url: str) -> object:
        calls.append(url)
        return object()

    monkeypatch.setattr("voxpress.pipeline.youtube_ytdlp.settings.youtube_audio_enabled", True)
    monkeypatch.setattr("voxpress.pipeline.youtube_ytdlp.extract_audio", fake_extract_audio)

    result = await YouTubeExtractor().extract("https://www.youtube.com/watch?v=KJ-efTR7WxM")

    assert result is not None
    assert calls == ["https://www.youtube.com/watch?v=KJ-efTR7WxM"]


async def test_youtube_extractor_requires_audio_download_enabled(monkeypatch) -> None:
    monkeypatch.setattr("voxpress.pipeline.youtube_ytdlp.settings.youtube_audio_enabled", False)

    try:
        await YouTubeExtractor().extract("https://www.youtube.com/watch?v=KJ-efTR7WxM")
    except YouTubeExtractError as exc:
        assert "音频下载已关闭" in str(exc)
    else:
        raise AssertionError("expected YouTubeExtractError")


def test_write_youtube_cookie_file_converts_cookie_header() -> None:
    path = _write_youtube_cookie_file("SID=one; HSID=two")
    try:
        text = path.read_text()
    finally:
        path.unlink()

    assert ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tone" in text
    assert ".youtube.com\tTRUE\t/\tTRUE\t0\tHSID\ttwo" in text
