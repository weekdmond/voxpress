# VoxPress API

FastAPI + SQLAlchemy async + Postgres 16。实现 `handoff/05-api-schema.md` 的所有 REST 路由 + SSE 流。
Pipeline (Extractor / Transcriber / LLMBackend) 目前是 stub,实现接 yt-dlp / mlx-whisper / Ollama 不改路由。

## 一次性准备

```bash
brew install postgresql@16 pgvector     # 已装过可跳
brew services start postgresql@16
createdb voxpress
psql voxpress -c 'CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;'

uv python install 3.12                   # 已装过可跳
uv sync                                   # 装依赖
uv run alembic upgrade head              # 建表
uv run python -m voxpress.seed           # 灌入示例数据(12 博主 / 78 视频 / 6 文章)
```

## 启动

```bash
uv run uvicorn voxpress.main:app --host 127.0.0.1 --port 8787 --workers 1
```

**必须 `--workers 1`**,SSE 用进程内 `asyncio.Queue` 做 fan-out,多 worker 会丢事件。

## 验证

```bash
curl localhost:8787/api/health
curl localhost:8787/api/creators | jq '.total'
curl -sN --max-time 6 localhost:8787/api/tasks/stream
curl -X POST localhost:8787/api/tasks \
  -H 'content-type: application/json' \
  -d '{"url":"https://www.douyin.com/video/7291abcd"}'
```

## 前端对接

在 `voxpress/.env` 里把 `VITE_USE_MOCK=false`、`VITE_API_BASE=http://localhost:8787` 即可。

## 结构

```
voxpress/
├── main.py            FastAPI app + lifespan (reconcile on startup)
├── config.py          pydantic-settings
├── db.py              async engine + session
├── models.py          6 张 ORM(与 handoff/06 DDL 对齐)
├── schemas.py         Pydantic 响应/请求
├── errors.py          ApiError + handler (错误包络)
├── sse.py             TaskBroker (in-memory pubsub)
├── routers/           creators / videos / articles / tasks / settings / health
├── pipeline/
│   ├── protocols.py   Extractor / Transcriber / LLMBackend Protocol
│   ├── stub.py        当前占位实现(前端能看到真实进度)
│   └── runner.py      任务 runner: 全局 semaphore + 4 阶段推进 + reconcile
└── seed.py            灌种子数据
```

## 切到真实 pipeline

三个真实实现都已经就位(`pipeline/ytdlp.py` · `pipeline/mlx.py` · `pipeline/ollama.py`)。切换只需 `.env`:

```bash
# voxpress-api/.env
VOXPRESS_PIPELINE=real   # 默认 stub; 改成 real 后下一条任务就走真后端
```

### 首次跑真后端需要的一次性准备

1. **系统依赖**（已装的跳过）:
   ```bash
   brew install ffmpeg ollama postgresql@16 pgvector
   brew services start ollama
   brew services start postgresql@16
   ```

2. **拉 Ollama 模型**(按你 128GB 内存挑一个):
   ```bash
   ollama pull qwen2.5:72b       # ~40GB, M5 Max 128GB 轻松
   # 或更轻量:
   ollama pull qwen2.5:32b       # ~18GB
   ollama pull qwen2.5:7b        # ~5GB, 测试用
   ```
   然后在 `/settings` 页面把 LLM model 切到对应名字。

3. **Whisper 模型**第一次 transcribe 时 mlx-whisper 会自动从 HuggingFace 下载
   `mlx-community/whisper-large-v3-mlx`(~3GB)。想预热:
   ```bash
   uv run python -c "import mlx_whisper; mlx_whisper.transcribe('/tmp/empty.wav', path_or_hf_repo='mlx-community/whisper-large-v3-mlx')" || true
   ```

4. **抖音 Cookie**(访问受登录保护的页面需要):
   - 浏览器登录 douyin.com
   - DevTools → Network → 任一请求的 Request Headers → Cookie
   - 复制整串(形如 `sessionid=xxx; passport_csrf_token=...; ...`)
   - 粘到前端 `/settings` 的「抖音 Cookie」文本框 → 保存
   - 后端自动写 Netscape 格式的 cookie file 传给 yt-dlp,不落盘(只在每次下载时临时写)

### 切换后的表现

- stub 模式下每个任务 ~4 秒走完 4 阶段(占位数据)
- real 模式下:
  - download 阶段:yt-dlp 实际下载 m4a 到 `VOXPRESS_AUDIO_DIR`
  - transcribe 阶段:首次跑会下载 whisper 模型;512 秒音频在 M5 Max 上约 30–60 秒
  - organize 阶段:72B 模型整理 3000 字文章约 30–50 秒
