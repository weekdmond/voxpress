# VoxPress API 架构说明

本文档描述当前 `voxpress-api` 的后端实现，基线为 DashScope + OSS + Postgres。

## 1. 总体结构

系统分成三层：

1. API 层：FastAPI 提供 REST 与 SSE
2. Worker 层：从数据库认领任务并执行各阶段
3. 状态层：Postgres 同时承担业务库、任务队列和事件总线

当前 pipeline 阶段为：

- `download`
- `transcribe`
- `correct`
- `organize`
- `save`

## 2. 外部依赖

真实模式依赖：

- Douyin / F2：抓视频元信息、拉媒体
- DashScope ASR：音频转写
- DashScope Qwen：逐字稿纠错、文章整理、背景注
- OSS：音频和视频归档

## 3. 进程职责

### API 进程

入口：[voxpress/main.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/main.py)

职责：

- 提供 REST API
- 提供 `/api/tasks/stream` SSE
- 写入任务
- 查询文章、视频、博主、设置

不负责：

- 不直接执行 pipeline
- 不维护任务调度循环

### Worker 进程

入口：[voxpress/worker.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/worker.py)

职责：

- 从 `tasks` 表认领任务
- 维持 lease / heartbeat
- 按阶段执行 `download -> transcribe -> correct -> organize -> save`
- 推进任务状态
- 驱动博主定时刷新

## 4. 关键模块

| 模块 | 文件 | 作用 |
|---|---|---|
| 配置 | [voxpress/config.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/config.py) | 环境变量、并发、路径、DashScope 参数 |
| 数据库 | [voxpress/db.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/db.py) | async engine / session |
| ORM | [voxpress/models.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/models.py) | creators / videos / transcripts / articles / tasks / settings |
| 任务存储 | [voxpress/task_store.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/task_store.py) | claim、heartbeat、阶段推进、失败/完成 |
| 运行时编排 | [voxpress/pipeline/runner.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/pipeline/runner.py) | 上下文拼装、转写保存、纠错、整理、最终落库 |
| DashScope 后端 | [voxpress/pipeline/dashscope.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/pipeline/dashscope.py) | Chat/JSON 调用、ASR、Corrector 重试 |
| 抖音抓取 | `pipeline/douyin_video.py` / `pipeline/douyin_scraper.py` | 视频元数据、媒体下载、博主刷新 |
| 回刷 job | [voxpress/jobs/rebackfill_background_notes.py](/Users/auston/cowork/dy_docs/voxpress-api/voxpress/jobs/rebackfill_background_notes.py) | 历史文章背景注回刷 |

## 5. 数据模型

核心业务表：

- `creators`
- `videos`
- `transcripts`
- `articles`
- `transcript_segments`

任务相关表：

- `tasks`
- `task_artifacts`
- `task_stage_runs`
- `system_job_runs`

配置表：

- `settings`

## 6. 执行链路

1. API 创建任务并写入 `tasks`
2. Worker 抢占任务并写 lease
3. `download` 拉视频和音频，更新 `creator` / `video`
4. `transcribe` 调 DashScope ASR，写入 `transcripts`
5. `correct` 调 DashScope corrector，对瞬时错误做有界重试
6. `organize` 调 DashScope Qwen 生成文章和背景注
7. `save` 落库 `articles` 与 `transcript_segments`
8. 全程通过 Postgres `LISTEN/NOTIFY` 向前端推 SSE

## 7. 当前约束

- `attempt_count` 仍表示任务被 claim 的累计次数，不是 stage 失败次数
- `settings.whisper` 等公开字段名暂时保留兼容，不在本轮重命名
- live 背景注回归依赖 DashScope 配额，可在额度不足时 skip
