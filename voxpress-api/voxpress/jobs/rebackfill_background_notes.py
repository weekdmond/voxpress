from __future__ import annotations

import argparse
import asyncio
import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select

from voxpress.db import session_scope
from voxpress.models import Article, Creator, SettingEntry, Transcript, Video
from voxpress.pipeline.dashscope import DashScopeLLM
from voxpress.pipeline.runner import runner
from voxpress.prompts import DEFAULT_ORGANIZER_TEMPLATE, DEFAULT_PROMPT_VERSION


@dataclass(slots=True)
class BackfillCandidate:
    article_id: UUID
    video_id: str
    article_title: str
    source_title: str
    creator_name: str
    article_summary: str
    transcript_text: str
    current_background_notes: dict[str, Any] | None


@dataclass(slots=True)
class BackfillResult:
    candidate: BackfillCandidate
    new_background_notes: dict[str, Any] | None
    changed: bool
    error: str | None = None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild background_notes for historical articles.")
    parser.add_argument("--since", default="2026-04-01", help="Only process articles created on/after this date.")
    parser.add_argument("--limit", type=int, default=100, help="Maximum number of articles to inspect.")
    parser.add_argument("--concurrency", type=int, default=2, help="Concurrent DashScope calls.")
    parser.add_argument("--out", help="CSV output path for dry-run or audit output.")
    parser.add_argument("--dry-run", action="store_true", help="Accepted for CLI clarity; dry-run is the default.")
    parser.add_argument("--apply", action="store_true", help="Write rebuilt background_notes back to the database.")
    parser.add_argument("--backup", help="Required with --apply. JSONL file used to back up current values.")
    return parser.parse_args()


def _parse_since(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _select_transcript_text(corrected_text: str | None, raw_text: str | None) -> str:
    preferred = (corrected_text or "").strip()
    if preferred:
        return preferred
    return (raw_text or "").strip()


def _canonical_notes(notes: dict[str, Any] | None) -> str:
    return json.dumps(notes, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _notes_changed(current: dict[str, Any] | None, rebuilt: dict[str, Any] | None) -> bool:
    return _canonical_notes(current) != _canonical_notes(rebuilt)


def _serialize_notes(notes: dict[str, Any] | None) -> str:
    return json.dumps(notes, ensure_ascii=False, sort_keys=True)


def _sync_prompt_value(existing: dict[str, Any] | None) -> dict[str, Any]:
    value = dict(existing or {})
    value["version"] = DEFAULT_PROMPT_VERSION
    value.setdefault("template", DEFAULT_ORGANIZER_TEMPLATE)
    return value


async def _load_candidates(*, since: datetime, limit: int) -> list[BackfillCandidate]:
    async with session_scope() as s:
        stmt = (
            select(
                Article.id,
                Article.video_id,
                Article.title,
                Article.summary,
                Article.background_notes,
                Video.title,
                Creator.name,
                Transcript.corrected_text,
                Transcript.raw_text,
            )
            .join(Video, Video.id == Article.video_id)
            .join(Creator, Creator.id == Article.creator_id)
            .join(Transcript, Transcript.video_id == Article.video_id)
            .where(Article.created_at >= since)
            .order_by(Article.created_at.desc(), Article.id.desc())
            .limit(limit)
        )
        rows = (await s.execute(stmt)).all()

    candidates: list[BackfillCandidate] = []
    for row in rows:
        transcript_text = _select_transcript_text(row.corrected_text, row.raw_text)
        if not transcript_text:
            continue
        current_notes = dict(row.background_notes) if isinstance(row.background_notes, dict) else None
        candidates.append(
            BackfillCandidate(
                article_id=row.id,
                video_id=row.video_id,
                article_title=str(row.title or ""),
                source_title=str(row[5] or ""),
                creator_name=str(row.name or ""),
                article_summary=str(row.summary or ""),
                transcript_text=transcript_text,
                current_background_notes=current_notes,
            )
        )
    return candidates


async def _resolve_llm() -> DashScopeLLM:
    model = await runner.current_llm_model()
    return DashScopeLLM(model=model)


async def _rebuild_candidate(
    candidate: BackfillCandidate,
    *,
    llm: DashScopeLLM,
    semaphore: asyncio.Semaphore,
) -> BackfillResult:
    async with semaphore:
        try:
            rebuilt = await llm.annotate_background(
                transcript=candidate.transcript_text,
                title_hint=candidate.source_title or candidate.article_title,
                creator_hint=candidate.creator_name,
                article_title=candidate.article_title,
                article_summary=candidate.article_summary,
            )
        except Exception as exc:  # noqa: BLE001
            return BackfillResult(candidate=candidate, new_background_notes=None, changed=False, error=str(exc))
    return BackfillResult(
        candidate=candidate,
        new_background_notes=rebuilt,
        changed=_notes_changed(candidate.current_background_notes, rebuilt),
    )


def _write_csv(path: Path, results: list[BackfillResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "article_id",
                "video_id",
                "creator_name",
                "article_title",
                "changed",
                "error",
                "current_background_notes",
                "new_background_notes",
            ],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "article_id": str(result.candidate.article_id),
                    "video_id": result.candidate.video_id,
                    "creator_name": result.candidate.creator_name,
                    "article_title": result.candidate.article_title,
                    "changed": "yes" if result.changed else "no",
                    "error": result.error or "",
                    "current_background_notes": _serialize_notes(result.candidate.current_background_notes),
                    "new_background_notes": _serialize_notes(result.new_background_notes),
                }
            )


def _write_backup(path: Path, results: list[BackfillResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for result in results:
            if result.error or not result.changed:
                continue
            payload = {
                "article_id": str(result.candidate.article_id),
                "video_id": result.candidate.video_id,
                "article_title": result.candidate.article_title,
                "background_notes": result.candidate.current_background_notes,
            }
            f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            f.write("\n")


async def _apply_results(results: list[BackfillResult]) -> tuple[int, bool]:
    changed_results = [result for result in results if result.changed and not result.error]
    article_map = {result.candidate.article_id: result.new_background_notes for result in changed_results}
    prompt_synced = False
    async with session_scope() as s:
        if article_map:
            rows = (
                await s.scalars(select(Article).where(Article.id.in_(list(article_map.keys()))))
            ).all()
            for row in rows:
                row.background_notes = article_map[row.id]

        prompt_row = await s.get(SettingEntry, "prompt")
        next_prompt_value = _sync_prompt_value(prompt_row.value if prompt_row else None)
        if prompt_row is None:
            s.add(SettingEntry(key="prompt", value=next_prompt_value))
            prompt_synced = True
        elif dict(prompt_row.value or {}) != next_prompt_value:
            prompt_row.value = next_prompt_value
            prompt_synced = True
    return len(changed_results), prompt_synced


def _print_summary(*, results: list[BackfillResult], applied: bool, prompt_synced: bool) -> None:
    total = len(results)
    changed = sum(1 for result in results if result.changed and not result.error)
    failed = sum(1 for result in results if result.error)
    skipped = total - changed - failed
    mode = "apply" if applied else "dry-run"
    print(
        json.dumps(
            {
                "mode": mode,
                "total": total,
                "changed": changed,
                "unchanged": skipped,
                "failed": failed,
                "prompt_version": DEFAULT_PROMPT_VERSION,
                "prompt_synced": prompt_synced,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


async def _run(args: argparse.Namespace) -> int:
    if args.apply and not args.backup:
        raise SystemExit("--apply requires --backup for safe rollback.")

    candidates = await _load_candidates(since=_parse_since(args.since), limit=max(1, args.limit))
    llm = await _resolve_llm()
    semaphore = asyncio.Semaphore(max(1, args.concurrency))
    results = await asyncio.gather(
        *[_rebuild_candidate(candidate, llm=llm, semaphore=semaphore) for candidate in candidates]
    )

    if args.out:
        _write_csv(Path(args.out), results)

    prompt_synced = False
    if args.apply:
        _write_backup(Path(args.backup), results)
        _changed_count, prompt_synced = await _apply_results(results)
    _print_summary(results=results, applied=bool(args.apply), prompt_synced=prompt_synced)
    return 0 if not any(result.error for result in results) else 1


def main() -> None:
    raise SystemExit(asyncio.run(_run(_parse_args())))


if __name__ == "__main__":
    main()
