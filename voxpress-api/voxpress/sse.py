from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import asyncpg
from sqlalchemy import text
from sqlalchemy.engine import make_url

from voxpress.config import settings
from voxpress.db import engine

TaskEventKind = Literal["create", "update", "remove"]
TASK_EVENTS_CHANNEL = "task_events"


@dataclass(slots=True)
class TaskEvent:
    kind: TaskEventKind
    task_id: str

    def sse(self, payload: dict) -> dict[str, str]:
        return {
            "event": f"task.{self.kind}",
            "data": json.dumps(payload, default=str, ensure_ascii=False),
        }


def _asyncpg_connect_args() -> dict:
    url = make_url(settings.db_url)
    return {
        "user": url.username,
        "password": url.password,
        "database": (url.database or "").lstrip("/"),
        "host": url.host or "127.0.0.1",
        "port": url.port or 5432,
    }


async def publish_task_event(kind: TaskEventKind, task_id: UUID | str) -> None:
    payload = json.dumps({"kind": kind, "task_id": str(task_id)}, ensure_ascii=False)
    async with engine.begin() as conn:
        await conn.execute(
            text("select pg_notify(:channel, :payload)"),
            {"channel": TASK_EVENTS_CHANNEL, "payload": payload},
        )


async def listen_task_events() -> AsyncIterator[TaskEvent]:
    queue: asyncio.Queue[TaskEvent | None] = asyncio.Queue(maxsize=512)
    conn = await asyncpg.connect(**_asyncpg_connect_args())

    def _listener(_: asyncpg.Connection, __: int, ___: str, payload: str) -> None:
        try:
            data = json.loads(payload)
            event = TaskEvent(kind=data["kind"], task_id=str(data["task_id"]))
            queue.put_nowait(event)
        except Exception:
            return

    await conn.add_listener(TASK_EVENTS_CHANNEL, _listener)
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
    finally:
        await conn.remove_listener(TASK_EVENTS_CHANNEL, _listener)
        await conn.close()
