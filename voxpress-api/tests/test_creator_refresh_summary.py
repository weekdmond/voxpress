from types import SimpleNamespace

from voxpress.creator_sync import CreatorRefreshSummary, _creator_result_item, _error_message


def test_creator_refresh_summary_exposes_structured_result() -> None:
    row = SimpleNamespace(id=12, name="付鹏的财经世界", handle="@付鹏的财经世界")
    failure = _creator_result_item("youtube", row, error="YouTube RSS 请求失败")
    skipped = _creator_result_item("douyin", row, reason="来源已暂停同步")

    summary = CreatorRefreshSummary(
        total=2,
        refreshed=0,
        failed=1,
        skipped=1,
        failures=[failure],
        skipped_details=[skipped],
    )

    assert summary.result() == {
        "failures": [failure],
        "skipped": [skipped],
    }


def test_error_message_falls_back_to_exception_class_name() -> None:
    assert _error_message(TimeoutError()) == "TimeoutError"
