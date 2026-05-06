import pytest

from voxpress.pipeline.youtube_url import (
    UnknownYouTubeLink,
    resolve_youtube_url,
    strip_youtube_video_pk,
    youtube_video_pk,
)


def test_resolve_watch_url() -> None:
    info = resolve_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s")

    assert info.kind == "video"
    assert info.external_id == "dQw4w9WgXcQ"
    assert info.canonical_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_resolve_short_url() -> None:
    info = resolve_youtube_url("https://youtu.be/dQw4w9WgXcQ")

    assert info.kind == "video"
    assert info.external_id == "dQw4w9WgXcQ"


def test_resolve_shorts_url() -> None:
    info = resolve_youtube_url("https://www.youtube.com/shorts/abcDEF_1234")

    assert info.kind == "video"
    assert info.canonical_url == "https://www.youtube.com/watch?v=abcDEF_1234"


def test_resolve_embed_url() -> None:
    info = resolve_youtube_url("https://www.youtube.com/embed/abcDEF_1234")

    assert info.kind == "video"
    assert info.external_id == "abcDEF_1234"


def test_resolve_handle_url() -> None:
    info = resolve_youtube_url("https://www.youtube.com/@OpenAI")

    assert info.kind == "channel"
    assert info.handle == "@OpenAI"
    assert info.external_id is None


def test_resolve_channel_url() -> None:
    info = resolve_youtube_url("https://www.youtube.com/channel/UCBR8-60-B28hp2BmDPdntcQ")

    assert info.kind == "channel"
    assert info.external_id == "UCBR8-60-B28hp2BmDPdntcQ"


def test_resolve_playlist_url() -> None:
    info = resolve_youtube_url("https://www.youtube.com/playlist?list=PL123")

    assert info.kind == "playlist"
    assert info.external_id == "PL123"


def test_rejects_non_youtube_url() -> None:
    with pytest.raises(UnknownYouTubeLink):
        resolve_youtube_url("https://example.com/watch?v=dQw4w9WgXcQ")


def test_video_pk_helpers() -> None:
    assert youtube_video_pk("abc") == "youtube:abc"
    assert strip_youtube_video_pk("youtube:abc") == "abc"
