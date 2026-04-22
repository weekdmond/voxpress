# VoxPress API

FastAPI + SQLAlchemy async + Postgres 16。实现 `handoff/05-api-schema.md` 的所有 REST 路由 + SSE 流。
Pipeline (Extractor / Transcriber / LLMBackend) 目前是 stub,实现接 f2 Douyin API / 直链下载 / mlx-whisper / Ollama 不改路由。

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
# 终端 1: API
uv run uvicorn voxpress.main:app --host 127.0.0.1 --port 8787 --workers 1

# 终端 2: worker
uv run python -m voxpress.worker
```

如果只启动 API，不启动 worker：

- 可以正常查询接口
- 可以成功创建任务
- 但任务不会被执行

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
├── main.py            FastAPI app（控制层）
├── config.py          pydantic-settings
├── db.py              async engine + session
├── models.py          ORM + tasks / task_artifacts / settings
├── schemas.py         Pydantic 响应/请求
├── errors.py          ApiError + handler (错误包络)
├── sse.py             Postgres LISTEN/NOTIFY 事件层
├── task_store.py      持久化任务租约 / 心跳 / 阶段推进
├── worker.py          独立 worker：download / transcribe / organize / save
├── jobs/
│   └── transcribe.py  转写子进程入口（隔离 mlx-whisper）
├── routers/           creators / videos / articles / tasks / settings / health
├── pipeline/
│   ├── protocols.py   Extractor / Transcriber / LLMBackend Protocol
│   ├── stub.py        当前占位实现(前端能看到真实进度)
│   └── runner.py      领域服务：媒体恢复 / upsert / 文章保存
├── creator_sync.py    博主抓取与入库
├── creator_refresh.py 博主定时刷新调度器
└── seed.py            灌种子数据
```

## 架构文档

完整中文架构说明见：

- [ARCHITECTURE.md](/Users/auston/cowork/dy_docs/voxpress-api/ARCHITECTURE.md)

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
   - 导出浏览器的 `cookies.txt` 文件
   - 前端 `/settings` 里选择 `cookies.txt` → 点击「导入并测试」
   - 后端会读取文件内容,并在抓取博主页 / 视频详情 / 下载媒体时复用同一份登录态

### 切换后的表现

- stub 模式下每个任务 ~4 秒走完 4 阶段(占位数据)
- real 模式下:
  - download 阶段:f2 拉取视频详情后直链下载 mp4,再抽取 m4a 到 `VOXPRESS_AUDIO_DIR`
  - transcribe 阶段:首次跑会下载 whisper 模型;512 秒音频在 M5 Max 上约 30–60 秒
  - organize 阶段:72B 模型整理 3000 字文章约 30–50 秒
