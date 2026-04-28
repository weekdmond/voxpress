# 2026-04-28 Tags / Entities Cleanup

## Status

Implemented locally.

## Context

After the tag/topic taxonomy backfill, `topics` became usable for analytics, but `tags` still mixed real keywords with named entities. The most frequent tags were creator/person names such as `金枪大叔` and `付鹏`, which makes keyword clouds and tag filters less useful.

## Decision

Split article metadata into three layers:

- `topics`: controlled taxonomy paths for analytics and digest.
- `tags`: free but non-entity keywords, such as concepts, methods, events, and industry terms.
- `entities`: named entities grouped by type, such as creators, people, organizations, brands, products, places, and events.

The article classifier should return `entities` separately and remove those values from `tags`.

## Data Model

Add `articles.entities` as JSONB:

```json
{
  "creators": ["金枪大叔"],
  "people": ["雷军"],
  "organizations": ["美联储"],
  "brands": ["小米"],
  "products": ["SU7"],
  "places": ["纽约"],
  "events": ["俄乌冲突"]
}
```

Keep the first rollout as JSONB rather than separate normalized tables. If entity search and global entity pages become important, introduce a normalized `article_entities` table later.

## Execution Plan

1. Add `articles.entities` migration, model field, schema, API serialization, and patch support.
2. Add entity normalization helpers and use them in the classifier.
3. Update DashScope classification prompt to split tags and entities.
4. Save `entities` in new article generation.
5. Extend historical reclassification script so it can re-clean existing `tags` and populate `entities`.
6. Display entities on the article detail page.

## Verification

- Backend tests and frontend typecheck/build must pass.
- Dry-run a small historical batch and inspect that creator/person/company names move from `tags` to `entities`.
- Apply the backfill in resumable batches.

Local verification completed on 2026-04-28:

- `uv run pytest -q` in `voxpress-api`: 70 passed.
- `uv run ruff check voxpress tests` in `voxpress-api`: passed.
- `npm run typecheck` in `voxpress`: passed.
- `npm run build` in `voxpress`: passed.
- `uv run alembic upgrade head && uv run alembic current` in `voxpress-api`: upgraded local DB to `b4e3c9d8a1f2 (head)`.

## Open Questions

- Should entities get first-class filter UI on the article list?
- Should creators be excluded from `entities.creators` when they duplicate the source creator?
- Should entity aliases be normalized across variants, such as `OpenAI` / `Open AI`?
