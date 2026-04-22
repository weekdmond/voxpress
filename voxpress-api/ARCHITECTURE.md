# VoxPress API 架构说明

本文档描述 `voxpress-api` 当前后端实现的模块职责、系统分层、任务流转和外部依赖，作为团队内部的技术说明基线。

## 1. 总体设计

当前架构采用三层分离：

1. 控制层（API）
   负责接收请求、创建任务、查询状态、返回内容、推送 SSE。
2. 执行层（Worker）
   负责下载、转写、整理、保存四段任务执行。
3. 状态层（Postgres）
   同时承担业务数据库、持久化任务队列、任务租约状态和事件总线。

核心设计目标：

- API 进程不再直接执行重任务，避免被 `mlx-whisper` / Metal 崩溃拖死。
- 任务队列持久化到数据库，避免进程内内存队列在重启时丢失。
- 下载、转写、整理、保存按阶段拆分，允许独立并发策略。
- 转写通过子进程隔离，单次转写崩溃不影响 API 与 worker 主进程。

## 2. 运行中的进程与职责

### 2.1 API 进程

入口文件：

- [voxpress/main.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/main.py)

职责：

- 提供 REST API
- 提供任务 SSE 流 `/api/tasks/stream`
- 读写业务数据
- 创建任务记录并发送任务事件

不负责：

- 不直接执行 pipeline
- 不直接维护任务调度循环

### 2.2 Worker 进程

入口文件：

- [voxpress/worker.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/worker.py)

职责：

- 从数据库抢占任务
- 维持任务租约与 heartbeat
- 按阶段执行：
  - `download`
  - `transcribe`
  - `organize`
  - `save`
- 在阶段之间推进任务状态
- 运行博主定时刷新调度器

### 2.3 转写子进程

入口文件：

- [voxpress/jobs/transcribe.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/jobs/transcribe.py)

职责：

- 接收音频路径、模型名、语言参数
- 调用 `mlx-whisper`
- 将转写结果以 JSON 输出给 worker 主进程

意义：

- 把 `mlx-whisper` 从 API / worker 主进程隔离出去
- 即使转写阶段因 Metal / GPU 断言崩溃，也只会杀死子进程

## 3. 模块职责说明表

| 模块 | 文件 | 职责 | 备注 |
|---|---|---|---|
| 应用入口 | [voxpress/main.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/main.py) | 装配 FastAPI、注册中间件和路由 | 当前只做控制层 |
| 配置 | [voxpress/config.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/config.py) | 统一读取环境变量、目录、并发和租约配置 | 含阶段并发配置 |
| 数据库会话 | [voxpress/db.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/db.py) | 提供 async engine / session / session_scope | API 与 worker 共用 |
| ORM 模型 | [voxpress/models.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/models.py) | 定义 creators / videos / articles / tasks / settings 等表结构 | `tasks` 已具备租约字段 |
| Pydantic Schema | [voxpress/schemas.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/schemas.py) | 定义 API 输入输出结构 | 前后端契约层 |
| 统一错误 | [voxpress/errors.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/errors.py) | 定义 `ApiError` 及标准错误包络 | 路由统一返回 |
| 任务路由 | [voxpress/routers/tasks.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/routers/tasks.py) | 创建任务、批量入队、列任务、取消任务、SSE 流 | API 控制层核心 |
| 解析路由 | [voxpress/routers/resolve.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/routers/resolve.py) | 单入口解析抖音视频 / 博主链接 | 视频建任务，博主直接抓列表 |
| 文章路由 | [voxpress/routers/articles.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/routers/articles.py) | 查询文章、修改文章、删除文章、重建文章 | 重建本质是新建任务 |
| 设置路由 | [voxpress/routers/settings.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/routers/settings.py) | 模型设置、Cookie 导入与测试 | 运行时配置入口 |
| 视频/博主/媒体路由 | `routers/videos.py` `routers/creators.py` `routers/media.py` | 业务查询与媒体代理 | 面向前端读取 |
| SSE 事件层 | [voxpress/sse.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/sse.py) | 基于 Postgres `LISTEN/NOTIFY` 发布和监听任务事件 | 代替旧内存 broker |
| 任务存储层 | [voxpress/task_store.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/task_store.py) | 任务认领、heartbeat、阶段推进、失败/完成、artifact 存取 | 队列核心 |
| Worker | [voxpress/worker.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/worker.py) | 阶段循环、并发控制、子进程转写、租约续约 | 执行层核心 |
| Runner 领域服务 | [voxpress/pipeline/runner.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/pipeline/runner.py) | 媒体恢复、元数据 upsert、组织输入准备、文章保存 | 不再自己调度任务 |
| 抖音提取 | `pipeline/douyin_video.py` `pipeline/douyin_scraper.py` | 抖音元信息抓取、媒体直链下载、博主页抓取 | 真实 pipeline 输入层 |
| Whisper 实现 | `pipeline/mlx.py` + [jobs/transcribe.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/jobs/transcribe.py) | 音频转写 | 当前通过子进程隔离 |
| LLM 实现 | `pipeline/ollama.py` | 调用本地 Ollama 整理文章 | 当前主要用 `qwen2.5:72b` |
| 媒体归档 | `media_store.py` | 视频、音频上传/下载 OSS | 支持重跑复用 |
| 博主同步 | `creator_sync.py` | 抓博主页、更新博主与视频元数据 | API 与定时任务复用 |
| 博主定时刷新 | [voxpress/creator_refresh.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/creator_refresh.py) | 周期性刷新每个博主最近作品 | 当前由 worker 承载 |

## 4. 数据层设计

### 4.1 业务主表

| 表 | 用途 |
|---|---|
| `creators` | 博主主数据 |
| `videos` | 视频元数据与媒体归档键 |
| `articles` | 文章正文与摘要 |
| `transcript_segments` | 文章逐字稿分段 |
| `settings` | 配置项 KV |

### 4.2 任务相关表

| 表 | 用途 |
|---|---|
| `tasks` | 持久化任务队列 |
| `task_artifacts` | 任务中间产物：逐字稿、整理结果 |

### 4.3 `tasks` 表关键字段

| 字段 | 作用 |
|---|---|
| `stage` | 当前阶段：`download / transcribe / organize / save` |
| `status` | 当前状态：`queued / running / done / failed / canceled` |
| `run_after` | 允许再次被调度的时间 |
| `lease_owner` | 当前 worker 持有者 |
| `lease_expires_at` | 租约过期时间 |
| `last_heartbeat_at` | 最近一次续约时间 |
| `attempt_count` | 当前任务被抢占执行的次数 |

### 4.4 `task_artifacts` 表用途

| 字段 | 内容 |
|---|---|
| `transcript_segments` | 转写产物 |
| `organized` | LLM 整理结果 |

设计意图：

- 阶段之间通过数据库中间产物传递，不依赖内存变量。
- 即使 worker 重启，也能从数据库恢复阶段上下文。

## 5. 当前任务执行链路

### 5.1 视频链接进入系统

1. 前端提交抖音视频链接到 `/api/resolve` 或 `/api/tasks`
2. API 在 `tasks` 表写入一条 `queued` 记录
3. API 通过 Postgres `NOTIFY` 发送任务事件
4. 前端通过 SSE 收到新任务

### 5.2 Worker 抢占任务

1. worker 按阶段轮询
2. 使用 `FOR UPDATE SKIP LOCKED` 抢占一条符合条件的任务
3. 写入新的租约持有者与过期时间
4. 进入对应阶段处理

### 5.3 四阶段执行说明

#### 下载阶段 `download`

职责：

- 优先恢复本地或 OSS 中已有的媒体缓存
- 缓存不存在时才访问抖音下载
- upsert `creator` 和 `video`
- 将任务绑定到 `creator_id`、`video_id`

#### 转写阶段 `transcribe`

职责：

- 准备音频文件
- 启动独立子进程执行 `mlx-whisper`
- 保存逐字稿到 `task_artifacts`

特点：

- 当前最重要的稳定性保护点
- 子进程崩溃时，不影响 API / worker 主进程

#### 整理阶段 `organize`

职责：

- 从 `task_artifacts` 读取逐字稿
- 调用 Ollama 生成结构化文章结果
- 保存整理产物到 `task_artifacts`

#### 保存阶段 `save`

职责：

- 根据整理结果更新或重建 `articles`
- 重写 `transcript_segments`
- 标记任务 `done`
- 清理中间产物

## 6. 并发与资源策略

并发配置位于：

- [voxpress/config.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/config.py:26)

当前按阶段独立控制：

| 阶段 | 配置项 | 默认值 |
|---|---|---|
| download | `VOXPRESS_DOWNLOAD_CONCURRENCY` | 4 |
| transcribe | `VOXPRESS_TRANSCRIBE_CONCURRENCY` | 1 |
| organize | `VOXPRESS_ORGANIZE_CONCURRENCY` | 2 |
| save | `VOXPRESS_SAVE_CONCURRENCY` | 4 |

其中：

- `transcribe` 固定单飞，避免 `mlx-whisper` 并发触发 Metal 崩溃
- `organize` 会额外读取设置表中的 `llm.concurrency` 动态收敛

## 7. 实时状态推送

当前 SSE 不再依赖 API 进程内 `asyncio.Queue`。

实现方式：

1. API / worker 在任务变化时执行 `pg_notify`
2. API 的 SSE 路由通过 `asyncpg` 订阅 `task_events`
3. 前端收到三类事件：
   - `task.create`
   - `task.update`
   - `task.remove`

这样做的好处：

- API 和 worker 可以分进程运行
- 多个写入方都能统一触发实时状态更新

## 8. 外部依赖关系

| 外部系统 | 用途 |
|---|---|
| Douyin / F2 | 博主与视频元信息抓取、媒体直链 |
| OSS | 视频 / 音频长期归档，支持重跑复用 |
| Ollama | 本地 LLM 文章整理 |
| mlx-whisper | 本地音频转写 |
| Postgres | 业务数据 + 持久化任务队列 + 事件总线 |

## 9. 当前架构的优点

- API 与重任务执行隔离，单点崩溃面显著缩小
- 任务持久化，不再完全依赖内存队列
- 阶段化清晰，便于后续扩展重试和观测
- 转写子进程隔离已经解决最危险的 API 被 Metal 一起打崩问题
- 支持 OSS 媒体复用，降低重复下载成本

## 10. 当前仍然存在的限制

### 10.1 已经解决的问题

- `mlx-whisper` 崩溃拖死 API：已通过子进程隔离解决
- API / worker 职责混杂：已拆分
- 任务只存在内存中：已改为数据库持久化

### 10.2 仍待完善的问题

1. 还没有完整的自动重试与退避机制
2. 还没有失败任务审计表或 attempt 级别明细
3. `task_artifacts` 目前直接存在 Postgres，中长期可能需要对象化归档
4. 取消任务仍然是 best-effort，不是所有外部调用都可即时中断
5. 博主库归属和视频原作者快照还没有完全分模
6. 定时博主刷新当前与 worker 共进程，后续更适合拆成单独调度器

## 11. 推荐启动方式

当前需要至少两个进程：

### 启动 API

```bash
cd /Users/auston/cowork/dy_docs/voxpress-api
uv run uvicorn voxpress.main:app --host 127.0.0.1 --port 8787 --workers 1
```

### 启动 Worker

```bash
cd /Users/auston/cowork/dy_docs/voxpress-api
uv run python -m voxpress.worker
```

如果只启动 API，不启动 worker：

- 可以查询数据
- 可以创建任务
- 但任务不会被执行

## 12. 一句话总结

当前 VoxPress API 已经演进成：

**一个以 FastAPI 为控制层、以 Postgres 为持久化任务中心、以独立 worker 为执行层、并通过子进程隔离转写风险的小型内容处理系统。**
