from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voxpress.models import Task


@dataclass(slots=True)
class TaskStatusSnapshot:
    id: UUID
    status: str
    rerun_of_task_id: UUID | None
    started_at: datetime | None


def _snapshot_sort_key(snapshot: TaskStatusSnapshot) -> tuple[datetime, str]:
    started_at = snapshot.started_at or datetime.min.replace(tzinfo=timezone.utc)
    return (started_at, str(snapshot.id))


def build_effective_status_map(
    snapshots: Sequence[TaskStatusSnapshot],
    *,
    root_ids: Sequence[UUID] | None = None,
) -> dict[UUID, str]:
    by_id = {snapshot.id: snapshot for snapshot in snapshots}
    children: dict[UUID, list[UUID]] = defaultdict(list)
    for snapshot in snapshots:
        if snapshot.rerun_of_task_id is not None:
            children[snapshot.rerun_of_task_id].append(snapshot.id)

    memo: dict[UUID, TaskStatusSnapshot | None] = {}
    visiting: set[UUID] = set()

    def latest_descendant(task_id: UUID) -> TaskStatusSnapshot | None:
        if task_id in memo:
            return memo[task_id]
        if task_id in visiting:
            return None

        visiting.add(task_id)
        best: TaskStatusSnapshot | None = None
        for child_id in children.get(task_id, []):
            child = by_id.get(child_id)
            if child is not None and (best is None or _snapshot_sort_key(child) > _snapshot_sort_key(best)):
                best = child
            nested = latest_descendant(child_id)
            if nested is not None and (best is None or _snapshot_sort_key(nested) > _snapshot_sort_key(best)):
                best = nested
        visiting.remove(task_id)
        memo[task_id] = best
        return best

    targets = list(root_ids) if root_ids is not None else list(by_id.keys())
    resolved: dict[UUID, str] = {}
    for task_id in targets:
        snapshot = by_id.get(task_id)
        if snapshot is None:
            continue
        effective_status = snapshot.status
        latest = latest_descendant(task_id)
        if snapshot.status == "failed" and latest is not None and latest.status == "done":
            effective_status = "done"
        resolved[task_id] = effective_status
    return resolved


async def load_effective_status_map(
    session: AsyncSession,
    tasks: Sequence[Task],
) -> dict[UUID, str]:
    if not tasks:
        return {}

    snapshots = {
        task.id: TaskStatusSnapshot(
            id=task.id,
            status=task.status,
            rerun_of_task_id=task.rerun_of_task_id,
            started_at=task.started_at,
        )
        for task in tasks
    }

    pending = set(snapshots.keys())
    while pending:
        rows = (
            await session.execute(
                select(Task.id, Task.status, Task.rerun_of_task_id, Task.started_at).where(
                    Task.rerun_of_task_id.in_(pending)
                )
            )
        ).all()

        next_pending: set[UUID] = set()
        for task_id, status, rerun_of_task_id, started_at in rows:
            if task_id in snapshots:
                continue
            snapshots[task_id] = TaskStatusSnapshot(
                id=task_id,
                status=status,
                rerun_of_task_id=rerun_of_task_id,
                started_at=started_at,
            )
            next_pending.add(task_id)
        pending = next_pending

    return build_effective_status_map(list(snapshots.values()), root_ids=[task.id for task in tasks])
