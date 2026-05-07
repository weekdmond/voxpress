from datetime import datetime, timezone

from voxpress.youtube_sync import _looks_like_refresh_timestamp


def test_refresh_timestamp_detection_only_matches_current_time() -> None:
    now = datetime(2026, 5, 7, 4, 54, 51, tzinfo=timezone.utc)

    assert _looks_like_refresh_timestamp(datetime(2026, 5, 7, 4, 54, 49, tzinfo=timezone.utc), now)
    assert not _looks_like_refresh_timestamp(datetime(2026, 4, 24, 11, 0, 21, tzinfo=timezone.utc), now)
