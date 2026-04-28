from datetime import datetime, timezone

from voxpress.auto_tasks import latest_videos
from voxpress.models import Video


def _video(video_id: str, published_at: str) -> Video:
    return Video(
        id=video_id,
        creator_id=1,
        title=f"作品 {video_id}",
        duration_sec=60,
        likes=0,
        plays=0,
        comments=0,
        shares=0,
        collects=0,
        published_at=datetime.fromisoformat(published_at).replace(tzinfo=timezone.utc),
        source_url=f"https://www.douyin.com/video/{video_id}",
    )


def test_latest_videos_keeps_newest_unique_items() -> None:
    older = _video("1", "2026-04-20T00:00:00")
    newest = _video("2", "2026-04-22T00:00:00")
    duplicate = _video("1", "2026-04-21T00:00:00")

    assert latest_videos([older, newest, duplicate], limit=2) == [newest, older]


def test_latest_videos_honors_limit() -> None:
    videos = [
        _video("1", "2026-04-20T00:00:00"),
        _video("2", "2026-04-22T00:00:00"),
        _video("3", "2026-04-21T00:00:00"),
    ]

    assert latest_videos(videos, limit=1) == [videos[1]]
