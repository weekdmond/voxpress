from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from voxpress.worker import StageConcurrencyResolver


class _Row:
    def __init__(self, value: dict[str, int]) -> None:
        self.value = value


class _Session:
    def __init__(self, row: _Row | None) -> None:
        self._row = row

    async def get(self, _model, key: str) -> _Row | None:
        assert key == "llm"
        return self._row


def _session_scope_factory(value: int | None):
    row = _Row({"concurrency": value}) if isinstance(value, int) else None

    @asynccontextmanager
    async def _scope():
        yield _Session(row)

    return _scope


@pytest.mark.asyncio
async def test_stage_concurrency_resolver_uses_stage_fallback_without_setting(monkeypatch) -> None:
    monkeypatch.setattr("voxpress.worker.session_scope", _session_scope_factory(None))
    resolver = StageConcurrencyResolver()

    assert await resolver.get("organize", 8) == 8
    resolver._checked_at = 0.0
    assert await resolver.get("correct", 3) == 3


@pytest.mark.asyncio
async def test_stage_concurrency_resolver_allows_ui_override_to_raise_limit(monkeypatch) -> None:
    monkeypatch.setattr("voxpress.worker.session_scope", _session_scope_factory(8))
    resolver = StageConcurrencyResolver()

    assert await resolver.get("organize", 2) == 8


@pytest.mark.asyncio
async def test_stage_concurrency_resolver_clamps_ui_override_to_hard_limit(monkeypatch) -> None:
    monkeypatch.setattr("voxpress.worker.session_scope", _session_scope_factory(100))
    resolver = StageConcurrencyResolver()

    assert await resolver.get("organize", 2) == 20


@pytest.mark.asyncio
async def test_stage_concurrency_resolver_allows_ui_override_to_reduce_limit(monkeypatch) -> None:
    monkeypatch.setattr("voxpress.worker.session_scope", _session_scope_factory(1))
    resolver = StageConcurrencyResolver()

    assert await resolver.get("organize", 8) == 1


@pytest.mark.asyncio
async def test_stage_concurrency_resolver_returns_fallback_for_non_llm_stage() -> None:
    resolver = StageConcurrencyResolver()

    assert await resolver.get("download", 4) == 4

