# VoxPress API 代码评审 v2（2026-04-23）

> 本轮所有发现均以**当前磁盘文件**为准，逐文件重读，不再沿用之前上下文里的缓存总结。上一版 `REVIEW.md` 和 `PR_PLAN.md` 里与本表冲突的基线以本文档为准。

---

## 0. 和上一版的差异（上一版错在哪）

| 事项 | 上一版 PR_PLAN 描述 | 当前实际（已核对 `voxpress/config.py`） |
|---|---|---|
| `download_concurrency` | 4 | 4（一致） |
| `transcribe_concurrency` | **1** | **4** |
| `correct_concurrency` | **1** | **8** |
| `organize_concurrency` | **2** | **8** |
| `save_concurrency` | 4 | 4（一致） |
| 默认 LLM 模型 | qwen-plus | **qwen3.6-plus**（定价也已含） |
| 默认 corrector 模型 | qwen-plus | **qwen-turbo** |
| ASR 轮询与超时参数 | 未实现 | 已实现（`dashscope_asr_poll_interval_sec=2`，`dashscope_asr_timeout_sec=1800`） |
| Chat/ASR pricing map | 未实现 | 已内建（`dashscope_chat_pricing` / `dashscope_asr_pricing`） |
| background_notes prompt 改写 | 计划中 | `prompts.py` 已含"政治实体优先"规则 |
| organizer prompt "保留火候 / 金句" | 计划中 | 已落地 |

由此带来的结果：PR_PLAN.md 中"提高 transcribe/organize/correct 并发"一类的改造项**基本已经完成**，不再需要；但**运行期覆盖机制、以 annotate_background 为代表的 prompt 注入路径仍未完整打通**。

---

## 1. 系统快照（经校验）

**项目结构（`voxpress/*.py`，非 services/）**：
- 核心层：`config.py`(153) · `models.py`(379) · `schemas.py`(425) · `db.py`(39) · `main.py`(56) · `errors.py`(73) · `markdown.py`(94) · `url_resolve.py`(136) · `seed.py`(221)
- 路由层：`routers/`(9 个：health / creators / videos / articles / tasks / system_jobs / media / resolve / settings)
- SSE：`voxpress/sse.py`（75 行，独占 asyncpg 连接 + `asyncio.Queue(maxsize=512)`）
- 队列 & 存储层（非 services/，平铺）：`task_store.py` · `task_metrics.py` · `system_job_store.py` · `media_store.py` · `creator_sync.py` · `creator_refresh.py`
- Worker：`worker.py`（单进程 5 个 stage 循环 + CreatorRefreshScheduler）
- Pipeline：`pipeline/protocols.py` · `runner.py`(690) · `dashscope.py`(608) · `corrector.py`(183) · `stub.py`(107) · `douyin_video.py`(346) · `douyin_scraper.py`(299) · 遗留 `ytdlp.py` / `mlx.py` / `ollama.py` · `jobs/transcribe.py`
- 提示词：`voxpress/prompts.py`（ORGANIZER / BACKGROUND_NOTES / CORRECTOR 三个默认模板）
- Alembic：11 条 migration，线性链完整
- 测试：5 个文件（`test_corrector.py` · `test_background_notes.py` · `test_markdown.py` · `test_task_metrics.py` · `test_organize_density.py`），无端到端集成测试

**5 阶段管线实测参数**：`download(4) → transcribe(4) → correct(8) → organize(8) → save(4)`，全局 `max_pipeline_concurrency=2`，lease=120s，heartbeat=15s，poll=1.2s。`StageConcurrencyResolver` 对 organize/correct 做**只降不升**的运行期覆盖（`worker.py:44–63`）。

**数据模型（10 张表）**：creators / videos / articles / transcript_segments / transcripts / tasks / task_artifacts / task_stage_runs / system_job_runs / settings。`tasks.stage` 在 init migration 里仅含 4 态，`c3f4a7d8b912` 迁移补齐 `correct`。

---

## 2. Blocker（必须先修，已逐条核对代码）

### B1. Media proxy 开启 follow_redirects → SSRF 风险
**位置**：`voxpress/routers/media.py:46`
```python
async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
```
allowlist 只校验初始 URL（`_is_allowed_host`），开启跟随重定向后，`douyinpic.com` 返回 302 指向 `127.0.0.1` 或内网地址时，服务端会主动访问它。修法：`follow_redirects=False`，或手动按 allowlist 校验每一跳。

### B2. `annotate_background()` 硬编码 system prompt，无运行期覆盖
**位置**：`voxpress/pipeline/dashscope.py:185`
```python
system=DEFAULT_BACKGROUND_NOTES_TEMPLATE,
```
对比 `organize()`（同文件 L121）走 `prompt_template or DEFAULT_ORGANIZER_TEMPLATE`，`annotate_background` 完全绕过 DB 里的 `SettingEntry("prompt")`。也就是说：即使上一轮你在 prompts.py 里加了"政治实体优先"规则，这条规则**只能靠重新部署生效**，无法在运行期切模板或做 A/B。修法：新增 `SettingEntry("prompt_background")` 或让 `annotate_background` 复用同一份 `prompt.template`。

### B3. `attempt_count` 无上限 → 失败任务无限重试
**位置**：`voxpress/task_store.py:365`（claim 路径）
```python
task.attempt_count += 1
```
claim 路径每次 `+1`，`status=failed` 的单次任务确实不会被再次 claim，但 `status=running && lease_expires_at <= now`（worker 崩溃或永久 hang）的任务会被反复回收，`attempt_count` 没有任何阈值判断，也没有死信态。修法：在 claim 前加 `attempt_count >= N` 判断，改判 `status=dead_lettered`（或复用 `failed` + `error`）。

### B4. Heartbeat 失效只在 transcribe 里被检查
**位置**：`voxpress/worker.py`（`LeaseHeartbeater` 定义在 L66–90；`_process_transcribe` 会检查 `hb.lost`，其他 `_process_download / _process_correct / _process_organize / _process_save` 并不检查）
后果：心跳判定已丢租约后，这些 stage 仍会跑完并尝试写 DB。下游的 `update_task_progress / queue_next_stage / mark_task_done` 会因为 `lease_owner` 不匹配而返回 False，才抛 `LeaseLost`（见 L93–114）—— 表象上不会直接双写，但会白白消耗一次 LLM/ASR 调用（成本和 token）。修法：统一在进入每个 stage 前后增加 `if hb.lost: raise LeaseLost`。

### B5. SSE 事件在队列满时静默丢弃
**位置**：`voxpress/sse.py:57–63`
```python
def _listener(_, __, ___, payload: str) -> None:
    try:
        ...
        queue.put_nowait(event)
    except Exception:
        return
```
`asyncio.Queue(maxsize=512)` + `put_nowait` + 宽泛 `except` 意味着：当消费端卡顿或客户端掉线未清理时，新事件会被静默丢弃，前端看不到"已经完成"的任务。修法：改用 `await queue.put()` 或在前端新增周期性对账（GET `/api/tasks?status=running` 回填）。

---

## 3. Major（应在本轮 PR 内处理）

### M1. 历史文章的 background_notes 没有回填
**位置**：`voxpress/pipeline/dashscope.py:406`（低置信度过滤）+ `voxpress/prompts.py:52`（政治实体优先规则）
prompt 已经改好，但没有看到针对历史 article 批量重跑 `organize` 的 system job。上一轮那个"西大/朗茨/黄毛 全部被识别成商业主体"的文章**仍然是老版本**。修法：新增一次性 system job（或扩展 `system_jobs` 表支持 `rebuild_background_notes`），按 `articles.updated_at` 分批重跑。

### M2. 每个 SSE 连接占用独立 asyncpg 连接
**位置**：`voxpress/sse.py:55`
`await asyncpg.connect(**_asyncpg_connect_args())` 每客户端一条连接，Postgres 默认 `max_connections=100`。本地自用没问题，上任何一台部署都是扩容炸弹。修法：全局起一条 listener + 内部 fan-out（多个 `asyncio.Queue` 订阅同一个事件源）。

### M3. Chunk 合并后未再做整体 ratio 校验
**位置**：`voxpress/pipeline/corrector.py`（`split_correction_chunks` + `validate_correction_result`）
每个 chunk 内部有 0.85–1.15 的长度校验，但合并后字符串没有再校验一次。极端情况（分段各自通过，但合并时换行/空格策略把文本吞掉几段）理论上能静默漏字。修法：在 `DashScopeCorrector.correct` 返回前对 `"\n".join(corrected_parts)` vs 原文再做一次总体 ratio 判断。

### M4. Organize LLM 超时 600s 过长
**位置**：`voxpress/pipeline/dashscope.py:134` 左右（`timeout_sec=600.0`）
一条任务可以卡在 organize 10 分钟，期间心跳正常、lease 不会过期，但用户看不到任何进展。修法：降到 180–240s，再把 "overcompression retry" 的超时独立开，在 TaskRunner 层加 per-stage timeout（哪怕先搞个 600s 硬兜底）。

### M5. 运行期 Settings PATCH 在 merge 之前缺类型校验
**位置**：`voxpress/routers/settings.py:80–81`
`{**merged[key], **value}` 假设两边都是 dict，如果前端（或攻击者）PATCH `{"llm": "not a dict"}`，会在后续 `_normalize_settings_dict` 里 `dict(...)` 时抛 500，而且前面已经部分 upsert。修法：将 `SettingsPatch` 改成 `Pydantic` 强类型 schema（按 key 分 oneOf），合并前先 validate。

### M6. Task.article_id 没有索引；creator/scope 查询会退化
**位置**：`voxpress/models.py:245` 附近
`article_id` 是 FK，`__table_args__` 里没加 idx，"通过 article_id 反查 task"之类查询（rebuild detail / cost 聚合）会走全表。修法：`Index("idx_tasks_article", "article_id")` + 对应 alembic。

### M7. `main.py.lifespan` 空空如也
**位置**：`voxpress/main.py:28–30`
启动时不做 DB 健康探针、不 warm 连接池、不校验 DashScope key 是否能用。生产上 API 会"起得来但第一个请求才发现 DB 不通"。修法：在 lifespan 里加 `SELECT 1` 和（可选）一次 DashScope ping。

### M8. 遗留模块未删除
**位置**：`voxpress/pipeline/ollama.py`（220）、`mlx.py`（61）、`ytdlp.py`（337）、`jobs/transcribe.py`（43）
全部都不在 runner 的调用路径上（grep 验证），但一直在 Python 包里会造成：① 误以为系统还支持本地模型；② `_corrector_backend` 未来分支逻辑容易被这些旧实现污染。修法：整个删掉 + `VOXPRESS_PIPELINE=real/stub` 一刀切，同时把 `worker.py` 里还在打印 `whisper_model` 的日志改名。

---

## 4. Minor

| ID | 位置 | 问题 | 建议 |
|---|---|---|---|
| N1 | `voxpress/models.py`（各 JSONB 列） | `articles.background_notes / transcripts.segments / transcripts.corrections / task_artifacts.*` 均无 schema 校验 | pydantic 子模型校验后再入库 |
| N2 | `voxpress/routers/media.py:63` | `res.content` 一次性读入，无大小限制 | httpx `limits=httpx.Limits(...)` 或流式读并设上限（比如 10MB） |
| N3 | `voxpress/routers/articles.py`（batch/delete / DELETE） | 硬删无确认、无审计、无速率 | 加最大 batch size + soft-delete（或审计日志）|
| N4 | `voxpress/routers/tasks.py:237` | `page` 与 `offset` 并存且 `offset` 覆盖 `page` | 文档化优先级；或拒绝同时传 |
| N5 | `voxpress/routers/articles.py:122–191` | article 详情 N+1（creator / video / transcript / task 分别 get） | 统一 `selectinload` |
| N6 | `voxpress/routers/health.py:18–21` | `except Exception: db_ok=False` 吞错误详情 | 至少记 warning |
| N7 | `voxpress/creator_refresh.py:34` | 间隔调度无抖动、无分布式锁（未来多副本会重复刷） | 加数据库级租约，或在 system_job_runs 上用唯一键 |
| N8 | `voxpress/config.py:44–48` | stage concurrency 1–20 与 `max_pipeline_concurrency` 不做交叉校验 | Pydantic model_validator 校验 `max >= each` |
| N9 | `voxpress/models.py` | `tasks.source_url` / `videos.source_url` 无索引 | 按使用模式决定是否加（当前通过 video_id 回查足够，所以可留 Note） |
| N10 | `voxpress/pipeline/runner.py:232–233` | `MediaStoreError` 仅 warn 吞掉 | 保留吞错误策略，但把这类 "partial save" 标记到 task.detail |
| N11 | `voxpress/pipeline/dashscope.py:136–162` | `organize` 响应字段缺省时 `_normalize_organized_payload` 合成空值 | 字段被合成时写一条 warn 日志，便于审计 |

---

## 5. 做得扎实的部分（不需要改，避免过度改造）

1. 队列实现：`FOR UPDATE SKIP LOCKED` + `lease_owner`（带 uuid4 后缀）+ 心跳续租（`task_store.py:332–383`），是教科书式实现。
2. Stage 原子推进：`queue_next_stage` 在同一事务里重置 `status/stage/progress` 并清租约，不存在"两个 stage 都持有此任务"的中间态。
3. DB CHECK 强约束 stage/status/trigger_kind（`models.py:210–219` 等）。
4. 定价与 token 累计：`task_metrics.py` 的 `llm_usage_from_dashscope / asr_usage / merge_usage` 把 chat 与 ASR 分开计费，`TaskStageRun` 逐阶段落盘，`_rollup_task_metrics` 再汇总到 `Task`。
5. Alembic 链路完整线性（无分叉无孤儿），`c3f4a7d8b912` 兜住了 init migration 漏掉的 `correct` stage。
6. Prompt 三条链路（organizer / background / corrector）都已迭代过：overcompression 自动 retry（`dashscope.py:136–163`）、低置信度统一过滤（L406）、ratio 校验（corrector 内）。
7. Markdown 渲染用 `mistune(escape=True)`，不走富文本 XSS 面。
8. URL 解析走 httpx + redirect + regex，覆盖了视频 / 图文 / 创作者主页三类规范 URL（`url_resolve.py:98–107`）。

---

## 6. 对 PR_PLAN.md 的 Delta（上一版的 6 条还剩哪几条）

| 原 PR | 描述 | 新判断 |
|---|---|---|
| PR 0 | background_notes 回归测试 fixture | **仍需做**（放进 M1 回填 PR 的前置） |
| PR 1 | prompt 升级 + 历史文章回填 | **部分保留**：prompt 本身已 OK；剩下只做"历史回填"（M1） |
| PR 2 | StageConcurrencyResolver 修复 + 提高并发 | **过时**：并发默认值已经上调；Resolver 的"只降不升"策略其实是故意的，不必改 |
| PR 3 | Correct 重试 + attempt_count 上限 | **保留，降格为 Major**（B3 单独拆出来作为 Blocker） |
| PR 4 | 旧模块清理 + whisper→asr rename | **保留**（M8） |
| PR 5 | organize + annotate_background 合并一次 LLM | **延后**：在 B2 处理之前不做；合并会固化硬编码 prompt 的问题 |

**本轮建议的 PR 组合（按收敛顺序）**：

1. **PR-A（Blocker 打包）**：
   - 关闭 media proxy 的 follow_redirects（B1）
   - 给 `_process_download/correct/organize/save` 加 `hb.lost` 检查（B4）
   - SSE 改 `await queue.put()` + 客户端对账路径（B5）
2. **PR-B（prompt 注入通道）**：
   - `annotate_background` 走 SettingEntry（B2）
   - 一次性 system job：`rebuild_background_notes`（M1）
3. **PR-C（任务韧性）**：
   - `attempt_count` 阈值 + dead-letter（B3）
   - Organize per-stage timeout（M4）
   - Chunk 合并 ratio 复核（M3）
4. **PR-D（Settings 硬化）**：
   - PATCH 强类型（M5）
   - `main.lifespan` DB ping + DashScope probe（M7）
5. **PR-E（清理与索引）**：
   - 删 `ollama.py / mlx.py / ytdlp.py / jobs/transcribe.py`（M8）
   - `idx_tasks_article`（M6）
   - Minor 清单里的 N2 / N3 / N5 / N6 挑必要的合进去

---

## 附：本轮评审过程

- 以 4 个并行 Explore agent 对 core / api-sse / worker-store / pipeline-intel 四层分别逐文件重读
- 4 个 agent 返回后，对所有"Blocker 级"发现单独 Re-Read 原文件（`media.py:46`、`dashscope.py:185`、`task_store.py:365`、`sse.py:57–63`、`worker.py:66–90`）逐字核对
- 路径校准：`task_store.py / creator_sync.py / creator_refresh.py / system_job_store.py / media_store.py` 都在 `voxpress/` 根下，不在 `voxpress/services/` 下，之前描述路径的地方一并修正

> 如果本轮结论里还有哪条与你自己的阅读对不上，指出来，我再 Re-Read 对应文件逐字核对，不再相信缓存。
