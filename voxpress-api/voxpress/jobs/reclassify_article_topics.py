"""Reclassify existing articles into controlled topics and cleaned tags.

Examples:

    uv run python -m voxpress.jobs.reclassify_article_topics --dry-run --limit 20
    uv run python -m voxpress.jobs.reclassify_article_topics --apply --resume --limit 200
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from voxpress.db import session_scope
from voxpress.models import Article, Creator, Video
from voxpress.pipeline.dashscope import DashScopeLLM
from voxpress.pipeline.runner import runner
from voxpress.runtime_settings import load_topic_taxonomy_runtime_settings


@dataclass(slots=True)
class Candidate:
    article_id: UUID
    title: str
    summary: str
    content_md: str
    source_title: str
    creator_name: str
    current_topics: list[str]
    current_tags: list[str]


@dataclass(slots=True)
class Result:
    candidate: Candidate
    topics: list[str]
    tags: list[str]
    error: str | None = None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reclassify article topics and tags.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Run classification without writing changes.")
    mode.add_argument("--apply", action="store_true", help="Write topics/tags back to articles.")
    parser.add_argument("--resume", action="store_true", help="Only classify articles with empty topics.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum articles to classify.")
    parser.add_argument("--concurrency", type=int, default=2, help="Concurrent DashScope calls.")
    return parser.parse_args()


async def _load_candidates(*, limit: int, resume: bool) -> list[Candidate]:
    stmt = (
        select(Article, Creator.name, Video.title)
        .join(Creator, Creator.id == Article.creator_id)
        .join(Video, Video.id == Article.video_id)
        .order_by(Article.updated_at.desc(), Article.id.desc())
        .limit(max(1, limit))
    )
    if resume:
        stmt = stmt.where(func.cardinality(Article.topics) == 0)

    async with session_scope() as s:
        rows = (await s.execute(stmt)).all()
    return [
        Candidate(
            article_id=article.id,
            title=article.title,
            summary=article.summary,
            content_md=article.content_md,
            source_title=source_title,
            creator_name=creator_name,
            current_topics=list(article.topics or []),
            current_tags=list(article.tags or []),
        )
        for article, creator_name, source_title in rows
    ]


async def _classify_candidate(
    candidate: Candidate,
    *,
    llm: DashScopeLLM,
    taxonomy_paths: list[str],
    synonyms: dict[str, str],
    semaphore: asyncio.Semaphore,
) -> Result:
    async with semaphore:
        try:
            payload = await llm.classify_article(
                title=candidate.title,
                summary=candidate.summary,
                content_md=candidate.content_md,
                source_title=candidate.source_title,
                creator_hint=candidate.creator_name,
                taxonomy_paths=taxonomy_paths,
                synonyms=synonyms,
            )
        except Exception as exc:  # noqa: BLE001
            return Result(candidate=candidate, topics=[], tags=[], error=str(exc))
    return Result(
        candidate=candidate,
        topics=list(payload.get("topics") or []),
        tags=list(payload.get("tags") or []),
    )


async def _apply_results(results: list[Result]) -> int:
    changed = 0
    async with session_scope() as s:
        for result in results:
            if result.error:
                continue
            article = await s.get(Article, result.candidate.article_id)
            if article is None:
                continue
            if article.topics == result.topics and article.tags == result.tags:
                continue
            article.topics = result.topics
            article.tags = result.tags
            changed += 1
    return changed


def _print_summary(*, results: list[Result], applied: bool, changed: int) -> None:
    errors = [result for result in results if result.error]
    samples: list[dict[str, Any]] = []
    for result in results[:10]:
        samples.append(
            {
                "article_id": str(result.candidate.article_id),
                "title": result.candidate.title,
                "old_topics": result.candidate.current_topics,
                "new_topics": result.topics,
                "old_tags": result.candidate.current_tags,
                "new_tags": result.tags,
                "error": result.error,
            }
        )
    print(
        json.dumps(
            {
                "applied": applied,
                "requested": len(results),
                "changed": changed,
                "errors": len(errors),
                "samples": samples,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


async def _run(args: argparse.Namespace) -> int:
    applied = bool(args.apply)
    candidates = await _load_candidates(limit=args.limit, resume=bool(args.resume))
    taxonomy = await load_topic_taxonomy_runtime_settings()
    model = await runner.current_llm_model()
    llm = DashScopeLLM(model=model)
    semaphore = asyncio.Semaphore(max(1, args.concurrency))
    results = await asyncio.gather(
        *[
            _classify_candidate(
                candidate,
                llm=llm,
                taxonomy_paths=taxonomy.paths,
                synonyms=taxonomy.synonyms,
                semaphore=semaphore,
            )
            for candidate in candidates
        ]
    )
    changed = await _apply_results(results) if applied else 0
    _print_summary(results=results, applied=applied, changed=changed)
    return 1 if any(result.error for result in results) else 0


def main() -> None:
    raise SystemExit(asyncio.run(_run(_parse_args())))


if __name__ == "__main__":
    main()
