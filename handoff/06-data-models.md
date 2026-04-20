# 06 · 数据模型（Postgres）

> 建议用 Drizzle 或 Prisma；下面给纯 SQL 方便直接执行。
> 所有时间都用 `timestamptz`，存 UTC。

## 表结构

```sql
-- ─── creators ───────────────────────────────────────
CREATE TABLE creators (
  id              BIGSERIAL PRIMARY KEY,
  platform        TEXT NOT NULL DEFAULT 'douyin',
  external_id     TEXT NOT NULL,          -- 平台方的 sec_uid
  handle          TEXT NOT NULL,
  name            TEXT NOT NULL,
  bio             TEXT,
  region          TEXT,
  verified        BOOLEAN NOT NULL DEFAULT FALSE,
  followers       INTEGER NOT NULL DEFAULT 0,
  total_likes     BIGINT  NOT NULL DEFAULT 0,
  video_count     INTEGER NOT NULL DEFAULT 0,
  recent_update_at TIMESTAMPTZ,
  imported_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (platform, external_id)
);
CREATE INDEX idx_creators_followers ON creators (followers DESC);

-- ─── videos ─────────────────────────────────────────
CREATE TABLE videos (
  id              TEXT PRIMARY KEY,        -- platform video id
  creator_id      BIGINT NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
  title           TEXT NOT NULL,
  duration_sec    INTEGER NOT NULL,
  likes           INTEGER NOT NULL DEFAULT 0,
  plays           BIGINT  NOT NULL DEFAULT 0,
  comments        INTEGER NOT NULL DEFAULT 0,
  shares          INTEGER NOT NULL DEFAULT 0,
  collects        INTEGER NOT NULL DEFAULT 0,
  published_at    TIMESTAMPTZ NOT NULL,
  cover_url       TEXT,
  source_url      TEXT NOT NULL,
  discovered_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_videos_creator_published ON videos (creator_id, published_at DESC);
CREATE INDEX idx_videos_likes ON videos (likes DESC);

-- ─── articles ───────────────────────────────────────
CREATE TABLE articles (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  video_id        TEXT NOT NULL UNIQUE REFERENCES videos(id) ON DELETE CASCADE,
  creator_id      BIGINT NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
  title           TEXT NOT NULL,
  summary         TEXT NOT NULL DEFAULT '',
  content_md      TEXT NOT NULL,
  content_html    TEXT NOT NULL,
  word_count      INTEGER NOT NULL DEFAULT 0,
  tags            TEXT[] NOT NULL DEFAULT '{}',
  likes_snapshot  INTEGER NOT NULL DEFAULT 0,
  published_at    TIMESTAMPTZ NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_articles_creator_pub ON articles (creator_id, published_at DESC);
CREATE INDEX idx_articles_tags ON articles USING GIN (tags);
CREATE INDEX idx_articles_content_tsv ON articles
  USING GIN (to_tsvector('simple', title || ' ' || content_md));

-- ─── transcript_segments ────────────────────────────
CREATE TABLE transcript_segments (
  article_id      UUID NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  idx             INTEGER NOT NULL,
  ts_sec          INTEGER NOT NULL,
  text            TEXT NOT NULL,
  PRIMARY KEY (article_id, idx)
);

-- ─── tasks ──────────────────────────────────────────
CREATE TABLE tasks (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_url      TEXT NOT NULL,
  title_guess     TEXT NOT NULL DEFAULT '',
  creator_id      BIGINT REFERENCES creators(id) ON DELETE SET NULL,
  video_id        TEXT,                    -- 确定后填
  stage           TEXT NOT NULL DEFAULT 'download',
  status          TEXT NOT NULL DEFAULT 'queued',
  progress        SMALLINT NOT NULL DEFAULT 0,
  eta_sec         INTEGER,
  detail          TEXT,
  article_id      UUID REFERENCES articles(id) ON DELETE SET NULL,
  error           TEXT,
  started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at     TIMESTAMPTZ,
  CHECK (stage IN ('download','transcribe','organize','save')),
  CHECK (status IN ('queued','running','done','failed','canceled'))
);
CREATE INDEX idx_tasks_status ON tasks (status, started_at DESC);

-- ─── settings (single-row KV) ───────────────────────
CREATE TABLE settings (
  key             TEXT PRIMARY KEY,
  value           JSONB NOT NULL,
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 初始值： 'llm' / 'whisper' / 'prompt' / 'cookie' / 'storage'
```

## 派生字段 / 视图

```sql
-- 博主文章数（不想每次 count，可以用 trigger 维护 creators.article_count）
CREATE MATERIALIZED VIEW creator_article_counts AS
  SELECT creator_id, COUNT(*) AS article_count
  FROM articles GROUP BY creator_id;
```

## 迁移策略

用 `drizzle-kit generate` 或手写 `migrations/00x_*.sql`。不要用 ORM 自动同步到生产。

## 文件存储

- 音频临时文件：`/var/voxpress/audio/<video_id>.m4a`，按 `settings.storage.audio_retain_days` 定期清理
- 导出 .md：不落盘，直接 stream 给前端

## 数据保留 / 清理 job

- 每天 03:00 运行：
  1. 删除超过 N 天的音频文件
  2. `VACUUM ANALYZE` 关键表
  3. 刷新 `creator_article_counts` materialized view
