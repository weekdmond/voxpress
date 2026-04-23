# VoxPress API

FastAPI + SQLAlchemy async + Postgres 16。当前真实链路已经切到：

- Douyin / F2 抓取视频元信息和媒体
- DashScope `qwen3-asr-flash-filetrans` 做转写
- DashScope Qwen 做纠错、整理和背景注
- OSS 做音频/视频归档

## 启动

```bash
uv sync
uv run alembic upgrade head

# 终端 1
uv run uvicorn voxpress.main:app --host 127.0.0.1 --port 8787 --workers 1

# 终端 2
uv run python -m voxpress.worker
```

## 环境变量

参考 [`.env.example`](/Users/auston/cowork/dy_docs/voxpress-api/.env.example)。

最小真实运行集：

```bash
VOXPRESS_PIPELINE=real
VOXPRESS_DASHSCOPE_API_KEY=sk-xxx
VOXPRESS_DB_URL=postgresql+asyncpg://auston@localhost/voxpress
```

`VOXPRESS_DASHSCOPE_API_KEY` 和 OSS 相关环境变量现在主要作为兜底/冷启动配置。运行中推荐把 DashScope / OSS 凭证写到数据库 `settings` 表，通过 `PATCH /api/settings` 管理；抖音 Cookie 仍走 `/api/cookie` 上传。

示例：

```bash
curl -X PATCH localhost:8787/api/settings \
  -H 'content-type: application/json' \
  -d '{
    "dashscope":{"api_key":"sk-xxx"},
    "oss":{
      "region":"cn-hangzhou",
      "bucket":"your-bucket",
      "access_key_id":"LTAI...",
      "access_key_secret":"secret"
    }
  }'
```

## 验证

```bash
curl localhost:8787/api/health
curl localhost:8787/api/creators | jq '.total'
curl -sN --max-time 6 localhost:8787/api/tasks/stream
curl -X POST localhost:8787/api/tasks \
  -H 'content-type: application/json' \
  -d '{"url":"https://www.douyin.com/video/7291abcd"}'
```

## 结构

```text
voxpress/
├── main.py
├── config.py
├── db.py
├── models.py
├── schemas.py
├── task_store.py
├── worker.py
├── creator_sync.py
├── creator_refresh.py
├── media_store.py
├── system_job_store.py
├── jobs/
│   └── rebackfill_background_notes.py
├── routers/
│   ├── articles.py
│   ├── creators.py
│   ├── health.py
│   ├── settings.py
│   ├── system_jobs.py
│   ├── tasks.py
│   └── videos.py
└── pipeline/
    ├── corrector.py
    ├── dashscope.py
    ├── douyin_scraper.py
    ├── douyin_video.py
    ├── protocols.py
    ├── runner.py
    └── stub.py
```

## 回刷背景注

```bash
uv run python -m voxpress.jobs.rebackfill_background_notes \
  --since 2026-04-01 \
  --dry-run \
  --out /tmp/background_notes_diff.csv
```

实际写回时加上 `--apply` 和 `--backup`。

## 测试

```bash
uv run pytest -q
uv run pytest -m live tests/test_background_notes_live.py -v
```

## 架构文档

- [ARCHITECTURE.md](/Users/auston/cowork/dy_docs/voxpress-api/ARCHITECTURE.md)
- [ARCHITECTURE-DIAGRAMS.md](/Users/auston/cowork/dy_docs/voxpress-api/ARCHITECTURE-DIAGRAMS.md)
