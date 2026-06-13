from datetime import datetime, timezone
from types import SimpleNamespace

from voxpress.models import Video
from voxpress.pipeline.youtube_ytdlp import YouTubeChannelInfo
from voxpress.youtube_sync import (
    _enrich_lightweight_youtube_videos,
    _looks_like_refresh_timestamp,
    _merge_rss_video_metadata,
    _videos_from_rss,
    _videos_requiring_metadata_probe,
    upsert_youtube_video,
)


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


def test_merge_rss_video_metadata_preserves_metrics_and_prefers_rss_published_at() -> None:
    channel = YouTubeChannelInfo(
        channel_id="UC123",
        handle="@demo",
        name="Demo Channel",
    )
    fallback_published_at = datetime(2026, 6, 11, 7, 3, tzinfo=timezone.utc)
    rss_published_at = datetime(2024, 5, 19, 12, 30, tzinfo=timezone.utc)
    existing = _videos_from_rss(
        channel,
        [
            SimpleNamespace(
                id="youtube:abc",
                external_id="abc",
                title="yt-dlp 标题",
                source_url="https://www.youtube.com/watch?v=abc",
                published_at=fallback_published_at,
            )
        ],
    )[0]
    existing = existing.__class__(
        id=existing.id,
        external_id=existing.external_id,
        title=existing.title,
        duration_sec=734,
        plays=5400,
        likes=55,
        comments=3,
        cover_url="https://i.ytimg.com/vi/abc/maxresdefault.jpg",
        source_url=existing.source_url,
        published_at=existing.published_at,
        channel=existing.channel,
    )

    merged = _merge_rss_video_metadata(
        channel,
        [existing],
        [
            SimpleNamespace(
                id="youtube:abc",
                external_id="abc",
                title="RSS 标题",
                source_url="https://www.youtube.com/watch?v=abc",
                published_at=rss_published_at,
            )
        ],
    )

    assert len(merged) == 1
    assert merged[0].title == "yt-dlp 标题"
    assert merged[0].duration_sec == 734
    assert merged[0].plays == 5400
    assert merged[0].likes == 55
    assert merged[0].published_at == rss_published_at


async def test_enrich_lightweight_youtube_videos_fills_metadata(monkeypatch) -> None:
    channel = YouTubeChannelInfo(channel_id="UC123", handle="@demo", name="Demo Channel")
    published_at = datetime(2026, 6, 8, 4, 0, tzinfo=timezone.utc)
    lightweight = _videos_from_rss(
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

    async def fake_probe_video(_url: str):
        item = lightweight[0]
        return SimpleNamespace(
            id=item.id,
            external_id=item.external_id,
            title="探测标题",
            duration_sec=734,
            plays=5400,
            likes=55,
            comments=3,
            cover_url="https://i.ytimg.com/vi/abc/maxresdefault.jpg",
            source_url=item.source_url,
            published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    monkeypatch.setattr("voxpress.youtube_sync.probe_video", fake_probe_video)

    enriched = await _enrich_lightweight_youtube_videos(lightweight)

    assert enriched[0].title == "探测标题"
    assert enriched[0].duration_sec == 734
    assert enriched[0].likes == 55
    assert enriched[0].plays == 5400
    assert enriched[0].published_at is published_at
    assert enriched[0].channel is channel


def test_videos_requiring_metadata_probe_skips_rows_with_existing_metrics() -> None:
    channel = YouTubeChannelInfo(channel_id="UC123", handle="@demo", name="Demo Channel")
    videos = _videos_from_rss(
        channel,
        [
            SimpleNamespace(
                id="youtube:has",
                external_id="has",
                title="已有元数据",
                source_url="https://www.youtube.com/watch?v=has",
                published_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
            ),
            SimpleNamespace(
                id="youtube:missing",
                external_id="missing",
                title="缺元数据",
                source_url="https://www.youtube.com/watch?v=missing",
                published_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
            ),
        ],
    )

    probe_ids = _videos_requiring_metadata_probe(videos, [("youtube:has", 734, 0, 0)])

    assert probe_ids == {"youtube:missing"}


async def test_upsert_youtube_video_preserves_existing_metrics_when_refresh_is_lightweight() -> None:
    existing = Video(
        id="youtube:abc",
        creator_id=1,
        title="旧标题",
        duration_sec=734,
        likes=55,
        plays=5400,
        comments=8,
        cover_url="old.jpg",
        source_url="https://www.youtube.com/watch?v=abc",
        published_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )

    class FakeSession:
        async def get(self, _model, _id):
            return existing

    channel = YouTubeChannelInfo(channel_id="UC123", handle="@demo", name="Demo Channel")
    lightweight = _videos_from_rss(
        channel,
        [
            SimpleNamespace(
                id="youtube:abc",
                external_id="abc",
                title="新标题",
                source_url="https://www.youtube.com/watch?v=abc",
                published_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
            )
        ],
    )[0]

    result = await upsert_youtube_video(FakeSession(), creator_id=2, video=lightweight)

    assert result is None
    assert existing.creator_id == 2
    assert existing.title == "新标题"
    assert existing.duration_sec == 734
    assert existing.likes == 55
    assert existing.plays == 5400
    assert existing.comments == 8
    assert existing.cover_url == "https://i.ytimg.com/vi/abc/hqdefault.jpg"
