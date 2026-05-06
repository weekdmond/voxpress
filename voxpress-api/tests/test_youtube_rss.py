from voxpress.pipeline.youtube_rss import _parse_datetime


def test_parse_datetime_handles_youtube_atom_time() -> None:
    parsed = _parse_datetime("2026-05-06T01:02:03+00:00")

    assert parsed.year == 2026
    assert parsed.month == 5
    assert parsed.day == 6
