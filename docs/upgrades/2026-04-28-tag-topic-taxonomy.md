# 2026-04-28 Tag / Topic Taxonomy Upgrade

## Status

Implemented locally.

## Context

SpeechFolio currently asks the organize LLM call to generate `tags` while writing each article. The model only sees the current article, so it invents labels independently. After 1105 local articles, the tag set has already drifted into a long-tail shape:

- 2281 distinct tag strings
- 4737 total tag assignments
- 1740 singleton tags
- 76.3% of tags appear only once

This makes tag-based theme distribution unreliable. It also blocks higher-level features such as Claude digest, because `by_topic` summaries would be calculated from inconsistent labels.

## Problem

The current `tags` field is doing two jobs at once:

- Fine-grained keywords, where freedom is useful
- Coarse analytical topics, where controlled vocabulary is required

That creates several failure modes:

- Synonyms split across articles, such as `技术分析`, `技术解读`, and `市场技术`
- Granularity drift, such as broad `金融` beside narrow `贵州茅台2026Q1`
- Naming inconsistency across noun phrases, hashtags, and overly specific labels
- Weak cross-article overlap, causing topic distribution to underestimate true concentration

## Decision

Introduce a two-layer classification model:

- `tags`: free keywords, still useful for search, detail, and keyword cloud
- `topics`: controlled topic paths from a taxonomy, used for analytics, digest, filtering, and theme distribution

Topic values should use full paths, for example:

```text
金融投资/股票市场
商业经营/品牌营销
科技数码/AI大模型
```

The pipeline should stop relying on the main organize prompt to invent tags. Instead, article writing and article classification should be separate model tasks:

- Organize call writes the article
- Classification call assigns `topics` from taxonomy and cleans `tags`

## Data Model

Add a persisted `topics` column to `articles`:

```python
class Article:
    tags: list[str]
    topics: list[str]
```

Recommended database shape:

```sql
ALTER TABLE articles
ADD COLUMN topics text[] NOT NULL DEFAULT '{}';

CREATE INDEX idx_articles_topics_gin ON articles USING gin (topics);
```

Keep taxonomy in `settings` first, rather than creating a dedicated table immediately. This matches the existing runtime-settings pattern and keeps the first rollout small.

Suggested `settings.key = "topic_taxonomy"` value:

```json
{
  "version": "v1",
  "taxonomy": [
    {
      "topic": "金融投资",
      "subtopics": ["宏观经济", "股票市场", "资产配置", "房产楼市"]
    },
    {
      "topic": "商业经营",
      "subtopics": ["品牌营销", "商业模式", "渠道销售", "组织管理"]
    }
  ],
  "synonyms": {
    "技术分析": "金融投资/股票市场",
    "技术解读": "金融投资/股票市场"
  }
}
```

## Pipeline Changes

Current flow:

```text
transcript -> organize -> {title, summary, content_md, tags} -> save article
```

Target flow:

```text
transcript -> organize -> {title, summary, content_md}
article snapshot + taxonomy -> classify -> {topics, tags}
save article
```

Classification input should include:

- Title
- Summary
- Creator name
- Source title
- Article body head and tail snippets
- Current taxonomy

Classification output:

```json
{
  "topics": ["金融投资/股票市场", "商业经营/品牌营销"],
  "tags": ["茅台", "渠道库存", "价格倒挂"]
}
```

Rules:

- `topics` must contain 1-3 taxonomy paths
- `topics` must be selected from the configured taxonomy
- `tags` may be free keywords, 0-4 items
- `tags` should be concrete nouns or short noun phrases
- Strip `#`, whitespace noise, duplicate values, and overlong labels
- Reject generic tags such as `思考`, `分享`, `干货`, `认知`, `观点`

## Execution Plan

1. Add `articles.topics` migration and expose it in backend schemas.
2. Update article detail/list APIs so `topics` is first-class and no longer copied from `tags`.
3. Add `topic_taxonomy` settings loader with a small default taxonomy.
4. Add a reusable article classifier in the DashScope pipeline.
5. Wire the classifier after organize and before save.
6. Save classifier output as `article.topics` and cleaned `article.tags`.
7. Add a batch script to backfill historical articles with `--dry-run`, `--apply`, `--resume`, and `--limit`.
8. Update article list filtering and future digest code to use `topics` for theme distribution.

## Implementation TODO

- [x] Add `articles.topics` migration, model field, schemas, and API serialization.
- [x] Add `topic_taxonomy` runtime settings with a small default taxonomy.
- [x] Add reusable article metadata classifier that returns controlled `topics` and cleaned free `tags`.
- [x] Wire classifier into new article generation after organize and before save.
- [x] Add historical reclassification job with `--dry-run`, `--apply`, `--resume`, and `--limit`.
- [x] Update article list and detail UI to display and filter by `topics`.
- [x] Run backend tests, frontend typecheck/build, and document verification result.

## Historical Backfill

The historical migration should run in two phases.

Phase 1: taxonomy generation.

Use existing tag frequencies plus representative article samples. Strong model recommended, such as qwen-max.

Input:

- All existing tags and frequencies
- Top representative titles or summaries per frequent tag
- Optional creator distribution

Output:

```json
{
  "taxonomy": [
    {"topic": "金融投资", "subtopics": ["宏观经济", "股票市场", "加密资产", "房产楼市"]}
  ],
  "tag_mapping": {
    "技术分析": ["金融投资/股票市场"],
    "FICC": ["金融投资/宏观经济"]
  }
}
```

Phase 1.5: human review.

The taxonomy should be reviewed before being used for backfill. The first version can be reviewed as JSON in settings or a local file. A settings-page editor can come later.

Phase 2: article reclassification.

Use qwen-plus or equivalent. For each article, pass title, summary, body snippets, and compact taxonomy. Write back `topics` and cleaned `tags`.

## Product Impact

After this upgrade:

- Topic distribution should use `topics`, not `tags`
- Keyword display and search can continue using `tags`
- Claude digest `by_topic` should wait until topics are backfilled
- Article list should eventually support topic filtering
- Settings should eventually expose taxonomy editing

## Verification

Minimum verification:

- Migration applies cleanly on local and production
- New article generated from video has non-empty `topics`
- `tags` remain concrete and do not contain obvious generic labels
- Article detail returns both `tags` and `topics`
- Batch backfill can resume after interruption
- Topic distribution no longer uses raw `tags`

Suggested data checks:

```sql
SELECT COUNT(*) FROM articles WHERE topics = '{}';

SELECT topic, COUNT(*)
FROM articles, unnest(topics) AS topic
GROUP BY topic
ORDER BY COUNT(*) DESC;

SELECT tag, COUNT(*)
FROM articles, unnest(tags) AS tag
GROUP BY tag
ORDER BY COUNT(*) DESC;
```

Local verification completed on 2026-04-28:

- `uv run pytest -q` in `voxpress-api`: 69 passed.
- `uv run ruff check voxpress tests` in `voxpress-api`: passed.
- `npm run typecheck` in `voxpress`: passed.
- `npm run build` in `voxpress`: passed.
- `uv run alembic upgrade head && uv run alembic current` in `voxpress-api`: upgraded local DB to `a7c9d2e4f6b1 (head)`.

## Open Questions

- Should the first taxonomy be stored only in `settings`, or should we introduce a versioned taxonomy table once the first backfill ships?
- Should `topics` allow only subtopic paths, or should top-level-only paths be allowed for ambiguous articles?
- Should changing taxonomy trigger automatic reclassification, or require an explicit batch job?
- Should article list filters show top-level topics first, then subtopics?
- Should Claude writeback be allowed to update `topics`, or only article title/content/tags?
