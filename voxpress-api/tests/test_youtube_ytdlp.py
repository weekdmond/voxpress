from datetime import datetime, timezone
import os
import sys
from types import SimpleNamespace

import pytest

from voxpress.pipeline.protocols import TranscriptResult
from voxpress.pipeline.youtube_ytdlp import (
    YouTubeChannelInfo,
    YouTubeExtractor,
    YouTubeTranscriptError,
    YouTubeVideoInfo,
    UNKNOWN_YOUTUBE_PUBLISHED_AT,
    _fetch_transcript_sync,
    _channel_tab_urls,
    _channel_videos_url,
    _base_ytdlp_opts,
    _channel_from_info,
    _looks_like_video_id,
    _merge_channel_about,
    _parse_channel_about_description,
    _parse_compact_count,
    _parse_json_string_field,
    _parse_video_published_at_html,
    _enrich_video_info,
    _video_from_info,
    _write_youtube_cookie_file,
    probe_video_metadata_for_cookie_test,
    probe_video_transcript_for_cookie_test,
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


def test_parse_video_published_at_html_reads_youtube_publish_date() -> None:
    published = _parse_video_published_at_html('{"publishDate":"2026-04-24T04:00:21-07:00"}')

    assert published is not None
    assert published.astimezone(timezone.utc).isoformat() == "2026-04-24T11:00:21+00:00"


def test_video_from_info_uses_unknown_publish_time_when_metadata_missing() -> None:
    video = _video_from_info({"id": "KJ-efTR7WxM", "title": "Missing date"})

    assert video.published_at == UNKNOWN_YOUTUBE_PUBLISHED_AT


def test_channel_from_info_reads_description_and_best_avatar() -> None:
    info = {
        "channel_id": "UC9cfcOuTT9rYkyUimMjLxuw",
        "channel": "Money or Life 美股频道",
        "uploader_url": "https://www.youtube.com/@Money_or_Life",
        "description": "欢迎订阅Money or Life 美股频道",
        "channel_location": "新加坡",
        "thumbnails": [
            {"url": "small.jpg", "height": 88},
            {"url": "large.jpg", "height": 900},
        ],
        "channel_follower_count": 76800,
        "playlist_count": 249,
    }

    channel = _channel_from_info(info)

    assert channel.bio == "欢迎订阅Money or Life 美股频道"
    assert channel.region == "新加坡"
    assert channel.avatar_url == "large.jpg"
    assert channel.video_count == 249


def test_channel_from_info_prefers_uploader_url_for_handle() -> None:
    channel = _channel_from_info(
        {
            "channel_id": "UC9cfcOuTT9rYkyUimMjLxuw",
            "channel": "Money or Life 美股频道",
            "channel_url": "https://www.youtube.com/channel/UC9cfcOuTT9rYkyUimMjLxuw",
            "uploader_url": "https://www.youtube.com/@Money_or_Life",
        }
    )

    assert channel.handle == "@Money_or_Life"


def test_channel_about_parsers_read_displayed_description_and_country() -> None:
    html = (
        '"description":"欢迎订阅Money or Life 美股频道\\n谢谢所有人的支持！",'
        '"descriptionLabel":{"content":"说明"},'
        '"country":"新加坡",'
        '"canonicalChannelUrl":"http://www.youtube.com/@Money_or_Life",'
        '"channelId":"UC9cfcOuTT9rYkyUimMjLxuw"'
    )

    assert _parse_channel_about_description(html) == "欢迎订阅Money or Life 美股频道\n谢谢所有人的支持！"
    assert _parse_json_string_field(html, "country") == "新加坡"
    assert _parse_json_string_field(html, "canonicalChannelUrl") == "http://www.youtube.com/@Money_or_Life"


def test_merge_channel_about_keeps_existing_values_when_about_missing() -> None:
    channel = YouTubeChannelInfo(
        channel_id="UC9cfcOuTT9rYkyUimMjLxuw",
        handle="@Money_or_Life",
        name="Money",
        bio="old bio",
        followers=76800,
        video_count=249,
    )

    merged = _merge_channel_about(
        channel,
        {
            "bio": "new bio",
            "region": "新加坡",
            "handle": None,
            "channel_id": None,
        },
    )

    assert merged.handle == "@Money_or_Life"
    assert merged.bio == "new bio"
    assert merged.region == "新加坡"
    assert merged.followers == 76800
    assert merged.video_count == 249


def test_enrich_video_info_disables_oembed_fallback_for_publish_time(monkeypatch) -> None:
    calls: list[bool] = []
    channel = YouTubeChannelInfo(channel_id="UC9cfcOuTT9rYkyUimMjLxuw", handle="@Money_or_Life", name="Money")
    video = YouTubeVideoInfo(
        id="youtube:MpmwlkfaH8I",
        external_id="MpmwlkfaH8I",
        title="Test video",
        duration_sec=1,
        plays=0,
        likes=0,
        comments=0,
        cover_url=None,
        source_url="https://www.youtube.com/watch?v=MpmwlkfaH8I",
        published_at=datetime(2026, 5, 7, tzinfo=timezone.utc),
        channel=channel,
    )

    def fake_probe(_url, cookie_text=None, *, allow_oembed_fallback=True, process=True, proxy_url=None):
        calls.append(allow_oembed_fallback)
        raise RuntimeError("blocked")

    monkeypatch.setattr("voxpress.pipeline.youtube_ytdlp._probe_video_sync", fake_probe)
    monkeypatch.setattr(
        "voxpress.pipeline.youtube_ytdlp._scrape_video_published_at",
        lambda _url, cookie_text=None, proxy_url=None: datetime(2026, 4, 24, 11, 0, 21, tzinfo=timezone.utc),
    )

    enriched = _enrich_video_info(video, channel=channel)

    assert calls == [False]
    assert enriched.published_at.isoformat() == "2026-04-24T11:00:21+00:00"


async def test_youtube_extractor_reads_metadata_without_audio_download(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_probe_video(url: str) -> YouTubeVideoInfo:
        calls.append(url)
        return YouTubeVideoInfo(
            id="youtube:KJ-efTR7WxM",
            external_id="KJ-efTR7WxM",
            title="Test video",
            duration_sec=123,
            plays=456,
            likes=7,
            comments=8,
            cover_url="https://i.ytimg.com/vi/KJ-efTR7WxM/hqdefault.jpg",
            source_url=url,
            published_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            channel=YouTubeChannelInfo(
                channel_id="UC9cfcOuTT9rYkyUimMjLxuw",
                handle="@Money_or_Life",
                name="Money or Life 美股频道",
                followers=76800,
                video_count=249,
            ),
        )

    monkeypatch.setattr("voxpress.pipeline.youtube_ytdlp.probe_video", fake_probe_video)

    result = await YouTubeExtractor().extract("https://www.youtube.com/watch?v=KJ-efTR7WxM")

    assert result.video_id == "youtube:KJ-efTR7WxM"
    assert result.audio_path.name == "youtube:KJ-efTR7WxM.m4a"
    assert calls == ["https://www.youtube.com/watch?v=KJ-efTR7WxM"]


def test_write_youtube_cookie_file_converts_cookie_header() -> None:
    path = _write_youtube_cookie_file("SID=one; HSID=two")
    try:
        text = path.read_text()
    finally:
        path.unlink()

    assert ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tone" in text
    assert ".youtube.com\tTRUE\t/\tTRUE\t0\tHSID\ttwo" in text


def test_write_youtube_cookie_file_closes_mkstemp_fd(monkeypatch, tmp_path) -> None:
    opened_fds: list[int] = []

    def fake_mkstemp(*, prefix: str, suffix: str):
        path = tmp_path / f"{prefix}sample{suffix}"
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        opened_fds.append(fd)
        return fd, str(path)

    monkeypatch.setattr("voxpress.pipeline.youtube_ytdlp.tempfile.mkstemp", fake_mkstemp)

    path = _write_youtube_cookie_file("SID=one")
    try:
        with pytest.raises(OSError):
            os.fstat(opened_fds[0])
    finally:
        path.unlink()


def test_base_ytdlp_opts_includes_proxy_when_configured() -> None:
    assert _base_ytdlp_opts("socks5://127.0.0.1:1080")["proxy"] == "socks5://127.0.0.1:1080"
    assert "proxy" not in _base_ytdlp_opts("")


def test_base_ytdlp_opts_enables_youtube_js_solver(monkeypatch) -> None:
    def fake_which(name: str) -> str | None:
        return {
            "deno": None,
            "node": "/usr/bin/node",
        }.get(name)

    monkeypatch.setattr("voxpress.pipeline.youtube_ytdlp.shutil.which", fake_which)

    opts = _base_ytdlp_opts(None)

    assert opts["js_runtimes"] == ["node:/usr/bin/node"]
    assert opts["remote_components"] == ["ejs:github"]


async def test_cookie_probe_uses_unprocessed_metadata(monkeypatch) -> None:
    calls: list[bool] = []

    def fake_probe(
        url: str,
        cookie_text: str | None = None,
        *,
        allow_oembed_fallback: bool = True,
        process: bool = True,
        proxy_url: str | None = None,
    ):
        calls.append(process)
        return object()

    async def fake_proxy_url():
        return None

    monkeypatch.setattr("voxpress.pipeline.youtube_ytdlp._probe_video_sync", fake_probe)
    monkeypatch.setattr("voxpress.pipeline.youtube_ytdlp.load_youtube_proxy_url", fake_proxy_url)

    assert await probe_video_metadata_for_cookie_test("https://www.youtube.com/watch?v=abc", "SID=one")
    assert calls == [False]


async def test_cookie_transcript_probe_uses_cookie_and_proxy(monkeypatch) -> None:
    transcript = TranscriptResult(segments=[(0, "hello")])
    calls: list[tuple[str, str | None, str | None]] = []

    def fake_fetch(url: str, cookie_text: str | None = None, proxy_url: str | None = None):
        calls.append((url, cookie_text, proxy_url))
        return transcript

    async def fake_proxy_url():
        return "http://proxy.local:7890"

    monkeypatch.setattr("voxpress.pipeline.youtube_ytdlp._fetch_transcript_sync", fake_fetch)
    monkeypatch.setattr("voxpress.pipeline.youtube_ytdlp.load_youtube_proxy_url", fake_proxy_url)

    assert await probe_video_transcript_for_cookie_test("https://www.youtube.com/watch?v=abc", "SID=one") is transcript
    assert calls == [("https://www.youtube.com/watch?v=abc", "SID=one", "http://proxy.local:7890")]


def test_fetch_transcript_reports_ytdlp_error_and_ignores_missing_formats(monkeypatch, tmp_path) -> None:
    captured_opts: dict = {}

    class FakeYoutubeDL:
        def __init__(self, opts: dict):
            captured_opts.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def extract_info(self, _url: str, *, download: bool):
            assert download is True
            raise RuntimeError("Requested format is not available")

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    monkeypatch.setattr("voxpress.pipeline.youtube_ytdlp.settings.audio_dir", tmp_path)

    with pytest.raises(YouTubeTranscriptError, match="Requested format is not available"):
        _fetch_transcript_sync("https://www.youtube.com/watch?v=KJ-efTR7WxM", cookie_text="SID=one")

    assert captured_opts["ignore_no_formats_error"] is True
