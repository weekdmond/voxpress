from voxpress.creator_backfill import _douyin_backfill_detail


def test_douyin_backfill_detail_reports_omitted_items_when_complete() -> None:
    detail = _douyin_backfill_detail("老QU行万里", processed=439, total=457, complete=True)

    assert detail == "补齐 老QU行万里 · 已入库 439/457 条视频 · 抖音接口未返回 18 条，已保留库内已有作品"


def test_douyin_backfill_detail_keeps_partial_failure_suffix_external() -> None:
    detail = _douyin_backfill_detail("老QU行万里", processed=245, total=420, complete=False)

    assert detail == "补齐 老QU行万里 · 已入库 245/420 条视频"
