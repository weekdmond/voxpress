from datetime import datetime, timezone
from types import SimpleNamespace

from voxpress.pipeline.youtube_ytdlp import YouTubeChannelInfo
from voxpress.youtube_sync import _looks_like_refresh_timestamp, _videos_from_rss


def test_refresh_timestamp_detection_only_matches_current_time() -> None:
    now = datetime(2026, 5, 7, 4, 54, 51, tzinfo=timezone.utc)

    assert _looks_like_refresh_timestamp(datetime(2026, 5, 7, 4, 54, 49, tzinfo=timezone.utc), now)
    assert not _looks_like_refresh_timestamp(datetime(2026, 4, 24, 11, 0, 21, tzinfo=timezone.utc), now)


def test_videos_from_rss_builds_lightweight_youtube_video_info() -> None:
    channel = YouTubeChannelInfo(
        channel_id="UC123",
        handle="@demo",
        name="Demo Channel",
    )
    published_at = datetime(2026, 6, 8, 4, 0, tzinfo=timezone.utc)

    videos = _videos_from_rss(
        channel,
        [
            SimpleNamespace(
                id="youtube:abc",
                external_id="abc",
                title="RSS 视频",
                source_url="https://www.youtube.com/watch?v=abc",
                published_at=published_at,
            )
        ],
    )

    assert len(videos) == 1
    assert videos[0].title == "RSS 视频"
    assert videos[0].duration_sec == 0
    assert videos[0].cover_url == "https://i.ytimg.com/vi/abc/hqdefault.jpg"
    assert videos[0].channel is channel
