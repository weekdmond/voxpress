from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)

TaskEventKind = Literal["create", "update", "remove"]


@dataclass
class TaskEvent:
    kind: TaskEventKind
    payload: dict[str, Any]

    def sse(self) -> dict[str, str]:
        return {
            "event": f"task.{self.kind}",
            "data": json.dumps(self.payload, default=str, ensure_ascii=False),
        }


class TaskBroker:
    """In-memory fan-out. MVP single-worker only."""

    def __init__(self) -> None:
        self._subs: set[asyncio.Queue[TaskEvent]] = set()

    async def publish(self, event: TaskEvent) -> None:
        dead: list[asyncio.Queue[TaskEvent]] = []
        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("SSE subscriber queue full, dropping")
                dead.append(q)
        for q in dead:
            self._subs.discard(q)

    def subscribe(self) -> asyncio.Queue[TaskEvent]:
        q: asyncio.Queue[TaskEvent] = asyncio.Queue(maxsize=256)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[TaskEvent]) -> None:
        self._subs.discard(q)

    async def stream(self, initial: list[TaskEvent]) -> AsyncIterator[dict[str, str]]:
        q = self.subscribe()
        try:
            for ev in initial:
                yield ev.sse()
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=20.0)
                    yield ev.sse()
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            self.unsubscribe(q)


broker = TaskBroker()
