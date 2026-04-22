from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import time
from dataclasses import dataclass
from uuid import UUID

from voxpress.config import settings
from voxpress.creator_refresh import scheduler as creator_refresh_scheduler
from voxpress.db import session_scope
from voxpress.models import SettingEntry
from voxpress.pipeline import runner
from voxpress.task_store import (
    claim_next_task,
    clear_artifact,
    finish_stage_run,
    heartbeat,
    load_artifact,
    mark_task_done,
    mark_task_failed,
    queue_next_stage,
    save_organized_artifact,
    start_stage_run,
    update_task_progress,
)
from voxpress.task_metrics import asr_usage

logger = logging.getLogger(__name__)


class LeaseLost(RuntimeError):
    pass


@dataclass(slots=True)
class StageSpec:
    name: str
    concurrency: int


class StageConcurrencyResolver:
    def __init__(self) -> None:
        self._cached_llm_limit = settings.organize_concurrency
        self._checked_at = 0.0

    async def get(self, stage: str, fallback: int) -> int:
        if stage not in {"organize", "correct"}:
            return fallback
        now = time.monotonic()
        if now - self._checked_at < 2.0:
            return max(1, min(fallback, self._cached_llm_limit))
        async with session_scope() as s:
            row = await s.get(SettingEntry, "llm")
        value = (row.value or {}).get("concurrency") if row else None
        limit = fallback
        if isinstance(value, int):
            limit = max(1, min(fallback, value))
        self._cached_llm_limit = limit
        self._checked_at = now
        return limit


class LeaseHeartbeater:
    def __init__(self, task_id: UUID, lease_owner: str) -> None:
        self.task_id = task_id
        self.lease_owner = lease_owner
        self._task: asyncio.Task | None = None
        self.lost = asyncio.Event()

    async def __aenter__(self) -> LeaseHeartbeater:
        self._task = asyncio.create_task(self._run(), name=f"lease-heartbeat:{self.task_id}")
        return self

    async def __aexit__(self, *_exc_info) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(settings.task_heartbeat_seconds)
            alive = await heartbeat(self.task_id, lease_owner=self.lease_owner)
            if not alive:
                self.lost.set()
                return


async def _ensure_progress(task_id: UUID, lease_owner: str, **kwargs) -> None:
    ok = await update_task_progress(task_id, lease_owner=lease_owner, **kwargs)
    if not ok:
        raise LeaseLost(f"task {task_id} lost lease before progress update")


async def _advance(task_id: UUID, lease_owner: str, *, stage: str, progress: int, detail: str) -> None:
    ok = await queue_next_stage(
        task_id,
        lease_owner=lease_owner,
        next_stage=stage,
        progress=progress,
        detail=detail,
    )
    if not ok:
        raise LeaseLost(f"task {task_id} lost lease before stage transition")


async def _complete(task_id: UUID, lease_owner: str, article_id) -> None:
    ok = await mark_task_done(task_id, lease_owner=lease_owner, article_id=article_id)
    if not ok:
        raise LeaseLost(f"task {task_id} lost lease before completion")


async def _process_download(task_id: UUID, lease_owner: str) -> None:
    await start_stage_run(
        task_id,
        lease_owner=lease_owner,
        stage="download",
        provider="douyin",
        model="douyin-web",
        detail="Douyin Web API 读取视频",
    )
    await _ensure_progress(task_id, lease_owner, progress=5, detail="Douyin Web API 读取视频", eta_sec=None)
    meta = await runner.download_stage(task_id)
    detail = "下载完成"
    if meta.audio_object_key:
        detail = "下载完成 · 已归档音频"
    await finish_stage_run(
        task_id,
        lease_owner=lease_owner,
        stage="download",
        status="done",
        provider="douyin",
        model="douyin-web",
        detail=detail,
    )
    await _advance(task_id, lease_owner, stage="transcribe", progress=40, detail=detail)


async def _process_transcribe(task_id: UUID, lease_owner: str, hb: LeaseHeartbeater) -> None:
    whisper_model = await runner.current_whisper_model()
    whisper_language = await runner.current_whisper_language()
    await start_stage_run(
        task_id,
        lease_owner=lease_owner,
        stage="transcribe",
        provider="dashscope",
        model=whisper_model,
        detail=await runner.current_whisper_label(),
    )
    await _ensure_progress(
        task_id,
        lease_owner,
        progress=45,
        detail=await runner.current_whisper_label(),
        eta_sec=None,
    )
    transcript = await runner.transcribe_inline(task_id)
    if hb.lost.is_set():
        raise LeaseLost(f"task {task_id} lost lease while transcribing")
    initial_prompt_used = await runner.build_initial_prompt(task_id)
    await runner.save_transcript_stage(
        task_id,
        transcript,
        initial_prompt_used=initial_prompt_used,
        whisper_model=whisper_model,
        whisper_language=whisper_language,
    )
    usage = asr_usage(whisper_model, duration_sec=await runner.task_duration_sec(task_id))
    await finish_stage_run(
        task_id,
        lease_owner=lease_owner,
        stage="transcribe",
        status="done",
        provider="dashscope",
        model=whisper_model,
        detail=f"转写完成 · {len(transcript.segments)} 段",
        input_tokens=int(usage["input_tokens"]),
        output_tokens=int(usage["output_tokens"]),
        total_tokens=int(usage["total_tokens"]),
        cost_cny=float(usage["cost_cny"]),
    )
    if not await runner.auto_correct_enabled():
        await runner.mark_correct_skipped(task_id)
        await _advance(
            task_id,
            lease_owner,
            stage="organize",
            progress=68,
            detail=f"转写完成 · 跳过纠错 · {len(transcript.segments)} 段",
        )
        return
    await _advance(
        task_id,
        lease_owner,
        stage="correct",
        progress=58,
        detail=f"转写完成 · {len(transcript.segments)} 段",
    )


async def _process_correct(task_id: UUID, lease_owner: str) -> None:
    corrector_model = await runner.current_corrector_model()
    await start_stage_run(
        task_id,
        lease_owner=lease_owner,
        stage="correct",
        provider="dashscope",
        model=corrector_model,
        detail=await runner.current_corrector_label(),
    )
    await _ensure_progress(
        task_id,
        lease_owner,
        progress=62,
        detail=await runner.current_corrector_label(),
        eta_sec=None,
    )
    result = await runner.correct_stage(task_id)
    corrections = result.get("corrections") or []
    status = str(result.get("correction_status") or "ok")
    usage = result.get("_usage") or {}
    await finish_stage_run(
        task_id,
        lease_owner=lease_owner,
        stage="correct",
        status="done" if status in {"ok", "skipped"} else "failed",
        provider="dashscope",
        model=str(result.get("corrector_model") or corrector_model),
        detail=(
            f"纠错完成 · {len(corrections)} 处修正"
            if status == "ok"
            else "纠错失败 · 已降级原稿"
        ),
        error=None if status in {"ok", "skipped"} else "已降级使用原始逐字稿",
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        total_tokens=int(usage.get("total_tokens") or 0),
        cost_cny=float(usage.get("cost_cny") or 0.0),
    )
    await _advance(
        task_id,
        lease_owner,
        stage="organize",
        progress=72,
        detail=(
            f"纠错完成 · {len(corrections)} 处修正"
            if status == "ok"
            else "纠错失败 · 已降级原稿"
        ),
    )


async def _process_organize(task_id: UUID, lease_owner: str) -> None:
    llm_model = await runner.current_llm_model()
    await start_stage_run(
        task_id,
        lease_owner=lease_owner,
        stage="organize",
        provider="dashscope",
        model=llm_model,
        detail=await runner.current_llm_label(),
    )
    await _ensure_progress(
        task_id,
        lease_owner,
        progress=78,
        detail=await runner.current_llm_label(),
        eta_sec=None,
    )
    organized = await runner.organize_stage(task_id)
    await save_organized_artifact(task_id, organized)
    usage = organized.get("_usage") or {}
    await finish_stage_run(
        task_id,
        lease_owner=lease_owner,
        stage="organize",
        status="done",
        provider="dashscope",
        model=str(organized.get("_primary_model") or llm_model),
        detail="整理完成",
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        total_tokens=int(usage.get("total_tokens") or 0),
        cost_cny=float(usage.get("cost_cny") or 0.0),
    )
    await _advance(task_id, lease_owner, stage="save", progress=92, detail="整理完成")


async def _process_save(task_id: UUID, lease_owner: str) -> None:
    await start_stage_run(
        task_id,
        lease_owner=lease_owner,
        stage="save",
        provider="database",
        model=None,
        detail="写入数据库",
    )
    artifact = await load_artifact(task_id)
    if not artifact.organized:
        raise RuntimeError("任务中间产物缺失，无法保存文章")
    await _ensure_progress(task_id, lease_owner, progress=92, detail="写入数据库", eta_sec=None)
    article_id = await runner.save_stage(task_id, organized=artifact.organized)
    await clear_artifact(task_id)
    await finish_stage_run(
        task_id,
        lease_owner=lease_owner,
        stage="save",
        status="done",
        provider="database",
        detail="写入数据库",
    )
    await _complete(task_id, lease_owner, article_id)


async def _run_claimed_task(stage: str, task_id: UUID, lease_owner: str) -> None:
    try:
        async with LeaseHeartbeater(task_id, lease_owner) as hb:
            if stage == "download":
                await _process_download(task_id, lease_owner)
            elif stage == "transcribe":
                await _process_transcribe(task_id, lease_owner, hb)
            elif stage == "correct":
                await _process_correct(task_id, lease_owner)
            elif stage == "organize":
                await _process_organize(task_id, lease_owner)
            elif stage == "save":
                await _process_save(task_id, lease_owner)
            else:
                raise RuntimeError(f"unknown stage {stage}")
    except LeaseLost:
        logger.info("task %s lease lost at stage %s", task_id, stage)
    except Exception as exc:  # noqa: BLE001
        logger.exception("task %s failed at stage %s", task_id, stage)
        await mark_task_failed(task_id, lease_owner=lease_owner, error=str(exc))


async def _stage_loop(spec: StageSpec, *, worker_name: str, stop: asyncio.Event) -> None:
    active: set[asyncio.Task] = set()
    resolver = StageConcurrencyResolver()
    while not stop.is_set():
        limit = await resolver.get(spec.name, spec.concurrency)
        while not stop.is_set() and len(active) < limit:
            claimed = await claim_next_task(spec.name, worker_name=worker_name)
            if claimed is None:
                break
            task = asyncio.create_task(
                _run_claimed_task(spec.name, claimed.id, claimed.lease_owner),
                name=f"{spec.name}:{claimed.id}",
            )
            active.add(task)

            def _done(t: asyncio.Task) -> None:
                active.discard(t)

            task.add_done_callback(_done)
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_interval_ms / 1000)
        except asyncio.TimeoutError:
            pass
    if active:
        await asyncio.gather(*active, return_exceptions=True)


async def run_worker() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    await creator_refresh_scheduler.start()
    specs = [
        StageSpec(name="download", concurrency=settings.download_concurrency),
        StageSpec(name="transcribe", concurrency=settings.transcribe_concurrency),
        StageSpec(name="correct", concurrency=settings.correct_concurrency),
        StageSpec(name="organize", concurrency=settings.organize_concurrency),
        StageSpec(name="save", concurrency=settings.save_concurrency),
    ]
    try:
        async with asyncio.TaskGroup() as tg:
            for spec in specs:
                tg.create_task(_stage_loop(spec, worker_name=f"worker:{spec.name}", stop=stop))
            await stop.wait()
    finally:
        await creator_refresh_scheduler.stop()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
