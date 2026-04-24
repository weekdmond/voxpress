from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from voxpress.task_status import TaskStatusSnapshot, build_effective_status_map


def _snapshot(
    *,
    status: str,
    rerun_of_task_id=None,
    started_at: datetime,
) -> TaskStatusSnapshot:
    return TaskStatusSnapshot(
        id=uuid4(),
        status=status,
        rerun_of_task_id=rerun_of_task_id,
        started_at=started_at,
    )


def test_failed_task_is_treated_as_done_when_latest_rerun_succeeds() -> None:
    now = datetime.now(timezone.utc)
    root = _snapshot(status="failed", started_at=now)
    rerun = _snapshot(status="done", rerun_of_task_id=root.id, started_at=now + timedelta(minutes=1))

    effective = build_effective_status_map([root, rerun], root_ids=[root.id, rerun.id])

    assert effective[root.id] == "done"
    assert effective[rerun.id] == "done"


def test_latest_descendant_status_wins_for_failed_task() -> None:
    now = datetime.now(timezone.utc)
    root = _snapshot(status="failed", started_at=now)
    first_rerun = _snapshot(status="done", rerun_of_task_id=root.id, started_at=now + timedelta(minutes=1))
    second_rerun = _snapshot(
        status="failed",
        rerun_of_task_id=first_rerun.id,
        started_at=now + timedelta(minutes=2),
    )

    effective = build_effective_status_map(
        [root, first_rerun, second_rerun],
        root_ids=[root.id, first_rerun.id, second_rerun.id],
    )

    assert effective[root.id] == "failed"
    assert effective[first_rerun.id] == "done"
    assert effective[second_rerun.id] == "failed"


def test_failed_task_without_successful_rerun_stays_failed() -> None:
    now = datetime.now(timezone.utc)
    root = _snapshot(status="failed", started_at=now)
    rerun = _snapshot(status="running", rerun_of_task_id=root.id, started_at=now + timedelta(minutes=1))

    effective = build_effective_status_map([root, rerun], root_ids=[root.id, rerun.id])

    assert effective[root.id] == "failed"
    assert effective[rerun.id] == "running"
