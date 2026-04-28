# VoxPress

把抖音博主的口播视频自动转写成结构化文章的个人工具。单机运行,macOS (M5 Max) 原生。

```
vox(声音) + press(印刷) = 把每一条视频从声波到铅字的转化
```

## Monorepo 结构

```
.
├── handoff/         前端 1:1 还原规格(设计 tokens / 组件 / 页面 / API schema)
├── voxpress/        React 18 + Vite 前端
├── voxpress-api/    FastAPI + Postgres + async pipeline 后端
└── voxpress-design.md    v0.4 设计文档
```

## 技术栈

**前端** — React 18 · TypeScript · Vite 5 · React Router v6 · TanStack Query · CSS Modules · sonner
**后端** — Python 3.12 (uv) · FastAPI · SQLAlchemy async · asyncpg · Alembic · sse-starlette · httpx
**数据** — PostgreSQL 16 · pgvector 0.8 · pg_trgm
**AI** — mlx-whisper (大陆 Silicon 原生) · Ollama (qwen2.5:7b / 72b)
**爬虫** — yt-dlp (单视频下载) · f2 (Douyin 签名 Web API)

## 快速启动

### 一次性准备
```bash
# 系统依赖
brew install postgresql@16 pgvector ffmpeg ollama uv
brew services start postgresql@16
brew services start ollama

# DB
createdb voxpress
psql voxpress -c 'CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;'

# 模型(选一个)
ollama pull qwen2.5:7b       # 5GB, 5-15s/篇
ollama pull qwen2.5:72b      # 47GB, 30-50s/篇,质量更好
# Whisper large-v3 首次调用自动下载(~3GB)
```

### 后端
```bash
cd voxpress-api
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run python -m voxpress.seed   # 可选:灌 12 博主 / 6 文章演示数据
uv run uvicorn voxpress.main:app --host 127.0.0.1 --port 8787 --workers 1
```

**`--workers 1` 必须**,SSE 用进程内 asyncio.Queue fan-out,多 worker 会丢事件。

### 前端
```bash
cd voxpress
cp .env.example .env
npm install
npm run dev
```

浏览器打开 http://127.0.0.1:5173/。

## Pipeline 模式

`.env` 的 `VOXPRESS_PIPELINE` 切换：
- `stub` — 占位实现,4 秒跑完一条任务,无外部依赖。默认
- `real` — yt-dlp + mlx-whisper + Ollama。需要 Cookie + 已拉取模型

## 设计文档

详细的视觉 / API / 数据模型规范在 `handoff/`,按号码顺序读即可：
- 01-architecture.md
- 02-design-tokens.md
- 03-components.md
- 04-pages.md
- 05-api-schema.md
- 06-data-models.md
- 07-interactions.md

## 升级记录

所有非平凡升级都需要先写设计记录，统一放在 [docs/UPGRADES.md](docs/UPGRADES.md)。

## 已知限制

- 单用户、单机、无鉴权(MVP 范围)
- mlx-whisper 只支持 Apple Silicon
- SSE 仅单 worker
- Douyin play_count 不对外开放,网页后端也拿不到
- Playwright 无法绕 Douyin 反爬(尝试过 stealth / patchright,都被验证码中间页拦)

## License

个人项目,暂未定 license。
