# VoxPress API · 全量代码评审

> 评审日期：2026-04-21
> 评审范围：`voxpress/` 源码 + `alembic/versions/*` + `pyproject.toml`（跳过 `.venv`）
> 对照基线：`ARCHITECTURE.md` / `README.md` / `/Users/auston/cowork/dy_docs/voxpress-design.md` v0.5

整体感受是 **骨架扎实、细节遗漏多**：三层分工（API / Worker / Postgres）清晰，租约 + 心跳 + `FOR UPDATE SKIP LOCKED` 的任务调度模型用对了，子进程隔离转写也实现了。但 v0.5 设计文档里三个核心特性（**纠错阶段、背景注、Whisper initial_prompt**）**全部没落地**，且运行期有几个会导致事件丢失、子进程僵死、任务取消无法真正中断的隐患。

按严重程度分类如下。每条都带 **文件:行号** 定位，可直接丢给 Codex 修改。

---

## Blocker —— 上线前必须修

### B1. SSE 事件在队列满时被静默丢弃
**位置**：`voxpress/sse.py:53-63`

```python
queue: asyncio.Queue = asyncio.Queue(maxsize=512)
def _listener(...):
    try:
        queue.put_nowait(event)     # 队列满时抛 QueueFull
    except Exception:
        return                      # ← 吞掉,没日志没指标
```

**问题**：asyncpg LISTEN 的回调是同步函数,只能 `put_nowait`。一旦 queue 满了（512 条积压）或任何解析异常,事件被无声丢弃。SSE 客户端不会收到这条 `task.update`,前端进度条会卡住,用户刷新也刷不出来(新事件也丢)。

**触发场景**：
- 单任务 4 阶段 × 每阶段多次 progress 更新 → 并发 10 个任务就能压到数百条/秒
- 网页端短时间打开多个 tab,每个 tab 都有自己的 `listen_task_events()`,每个都独占一条 asyncpg 连接(见 B3 一并修)

**建议**：
1. 至少加 `logger.warning("sse queue full, dropping %s", event)`,让丢事件可观测
2. 改用 `asyncio.run_coroutine_threadsafe(queue.put(event), loop)` 异步入队(asyncpg 的监听器可以调用这个)
3. 或者把队列调整为"只保留最新 N 个 task_id 的最后一个事件"—— 业务上后到的 update 天然覆盖旧的,没必要都送到

---

### B2. 转写子进程可能因 stdout 管道缓冲溢出而僵死
**位置**：`voxpress/worker.py:117-159`

```python
proc = await asyncio.create_subprocess_exec(..., stdout=PIPE, stderr=PIPE)
while True:
    try:
        await asyncio.wait_for(proc.wait(), timeout=...)   # ← 没读 stdout!
        stdout, stderr = await proc.communicate()
        break
    except TimeoutError:
        if hb.lost.is_set(): proc.kill(); raise LeaseLost
        continue
```

**问题**：`proc.wait()` 不消费 stdout。macOS 管道缓冲通常 16–64KB,长视频转写输出的 JSON 段落列表一旦超过这个阈值,子进程会阻塞在 `sys.stdout.write()`,父进程的 `wait()` 永远不返回 → 心跳也不动 → 直到 lease 超时被另一个 worker 抢占,新 worker 再 fork 一个进程,又僵死一次。本地 M5 Max 跑长视频(> 10 分钟)几乎必中。

**建议**：
```python
# 同时 drain stdout/stderr,wait 变成等任一完成
async def _read(stream):
    return await stream.read()
stdout, stderr = await asyncio.gather(_read(proc.stdout), _read(proc.stderr))
await proc.wait()
```
或者让子进程把结果写到临时文件,stdout 只输出 JSON 指针,彻底避开大载荷走管道。

---

### B3. 任务取消无法真正中断运行中的工作
**位置**：`voxpress/task_store.py:223-239` + `voxpress/worker.py:93-108`

```python
# task_store.cancel_task() 只改 DB 状态
task.status = "canceled"; task.lease_owner = None

# worker 只有在调 _ensure_progress / _advance / _complete 时才会发现 lease 丢失
```

**问题**：用户点击"取消"后,数据库立即变成 `canceled`,但 worker 正在跑的那条任务(尤其 organize 阶段的 LLM 调用,单次 30–60 秒)**不知道自己被取消了**,会跑到阶段结束才在 `_advance()` 里抛 `LeaseLost`。用户看到"已取消"但 GPU/CPU 还在满负荷干活,违反直觉。

**建议**：
- 低成本方案:cancel 时发一个 `pg_notify('task_cancel', task_id)`,worker 内部订阅这个通道,收到后对该 task 的 subprocess 立即 `kill()`,对 httpx 调用设一个 `asyncio.Event` 并 `cancel()` 掉 `httpx.AsyncClient` 请求
- 高成本方案:在每个阻塞调用前后主动 `await heartbeat(...)`,把检查频率提到 1–2 秒

---

## Major —— 影响正确性/鲁棒性,两周内修

### M1. 设计文档 v0.5 的三大核心特性全部未落地
**位置**：全局

| 设计文档 | 代码现状 | 缺口 |
|---|---|---|
| §6.5 Correct 5% 纠错阶段 | `worker.py:282` 只有 4 阶段 | 无 `corrector.py` / 无 `transcripts.corrected_text` / 无 `correction_status` |
| §6.5.2 Whisper `initial_prompt` | `mlx.py` 的 `transcribe()` 不收 prompt 参数 | 用不上视频标题/作者做 biasing,"美伊交战→每一交站"这类同音错会一直存在 |
| §7.4 背景注 | `articles` 表无 `background_notes` 字段,`ollama.py` 的 prompt 没要求输出 | 博主隐晦代称仍然没人解释 |

**影响**：你在上一轮会话里明确说要解决的两个真实问题("美伊交战"同音错 + 隐晦内容解释),代码里**一个都没修**。必须补上,否则设计文档是空中楼阁。

**建议**：这是三件独立的事,按优先级做。**先做 initial_prompt（30 分钟成本,最大收益）**:
1. `Transcriber.transcribe(path, language, initial_prompt=None)` 加个参数
2. `runner.transcribe_inline()` 从 `VideoContext` 构造 `f"{title}。{creator}。{tags}"` 传入
3. `mlx.py` 把 prompt 透给 `mlx_whisper.transcribe(..., initial_prompt=...)`
4. `transcript_segments` 表或 `task_artifacts` 里记下用了什么 prompt,便于后续回放评估

纠错阶段和背景注需要改 schema + 加 stage,工作量各 3–4 小时。

---

### M2. list_tasks 有 N+1,stream_tasks 启动阶段也有
**位置**：`voxpress/routers/tasks.py:60`, `voxpress/task_store.py:42`

```python
for t in items:
    creator = await s.get(Creator, t.creator_id) if t.creator_id else None
```

100 条任务 = 101 次 SQL round-trip。`build_task_payload()` 同样每条 task 都 get 一次 creator,`stream_tasks()` 初始重放时对 N 个活跃任务也会打 N 次。

**建议**：`selectinload(Task.creator)` 或直接 `select(Task, Creator).outerjoin(Creator)` 一次拉齐。

---

### M3. LLM 输出没有 schema 校验,content_md 可能为空
**位置**：`voxpress/pipeline/ollama.py:73-92`

```python
data = _loose_json(raw)       # 可能是 {}
title = (data.get("title") or title_hint).strip()
content_md = (data.get("content_md") or "").strip()
...
"content_md": content_md or f"# {title}\n\n> {summary}",  # 兜底用 summary
```

当 Qwen 返回空(Ollama 服务没跑 / 模型没下载),`organize()` 不报错,返回一条只有标题的"文章"就进库了。用户看到的是一篇假文章,排查时还以为 pipeline 正常。

**建议**：
1. `raise RuntimeError("LLM 返回空结果")` 当 `data == {}` 或 `content_md` 长度 < 50
2. 把任务状态标 `failed` 并写清楚原因,让 worker 走重试

---

### M4. Cookie 敏感字段脱敏是"事后补救"
**位置**：`voxpress/routers/settings.py:73-76`

`_load()` 在返回前手动 `value.pop("text", None)`,这是"补丁式"脱敏。`SettingsOut` schema 没有强制声明 `text` 不暴露,未来加一个新路由或直接 dump `SettingEntry.value`,cookie 明文就会出站。

**建议**：
- `CookieSettings` schema 里 `text: str | None = Field(default=None, exclude=True)`,从 Pydantic 层保证序列化不带
- 或者拆两张表/两个 key:`cookie_public`(status, last_tested_at) 和 `cookie_secret`(text),只有内部 pipeline 能读 secret

---

### M5. `proxy_media` 无响应大小上限
**位置**：`voxpress/routers/media.py:45-66`

白名单限定了 `douyinpic.com`(L16-25,做得对),但仍然 `res.content` 全量读进内存再一次性返回。`timeout=12` 秒内如果抖音 CDN 返回一张超大图(或被污染),会直接吃内存。风险比完全开放的代理小一个档次,但仍建议加防护。

**建议**：检查 `res.headers.get("content-length")`,超过 10MB 直接 413;或者改成流式代理 `async for chunk in res.aiter_bytes():` + `StreamingResponse`。

---

### M6. `claim_next_task` 的 `attempt_count` 没有上限熔断
**位置**：`voxpress/task_store.py:75-113`

抢占逻辑会把 `attempt_count += 1`。如果某条任务的 download 阶段持续失败(比如抖音 cookie 过期、视频被删),任务会进 `failed` 状态不再重试 —— 这是对的。但**如果是 lease 超时路径**(worker 崩溃,任务被其他 worker 接管),`attempt_count` 会一直涨,没有封顶。

**建议**:`attempt_count >= 5` 直接转 `failed`,避免 worker 反复崩溃时一条任务无限占资源。

---

### M7. 批量 emit 串行,吞吐差
**位置**：`voxpress/routers/tasks.py:115-117`

```python
for t in created:
    await s.refresh(t)
    await emit_task_create(t.id)       # 每条走一次 engine.begin() + pg_notify
```

一次 batch 导入 50 个视频 = 50 次连接 begin/commit。每个 `publish_task_event()` 都 `engine.begin()` 是重量级的。

**建议**:`await asyncio.gather(*[emit_task_create(t.id) for t in created])`,或改成单条 SQL `pg_notify` 多次调用。

---

### M8. 缺少索引（设计文档要求的 pgvector HNSW / pg_trgm 完全没建）
**位置**：`alembic/versions/98faa810d482_init_schema.py`

设计文档 §4.4 要求:
- `articles.title_embedding` VECTOR(1024) + HNSW
- `articles.content_md` 上建 pg_trgm gin 索引支持中文模糊

代码里 `Article` 模型完全没有 embedding 列,也没有 extension 启用的 migration。`README.md` 第 12 行让用户手动 `CREATE EXTENSION vector, pg_trgm`,但数据库里没有用到这两个扩展 —— 启了等于没启。

**建议**：要么承认 MVP 不做向量检索(那就从 README 里删掉 `CREATE EXTENSION`,避免误导),要么补一条 migration + 在 `Article` 里加 `title_embedding` + `content_trgm` 索引。

---

## Minor —— 风格/小瑕疵

- **`config.py:19`** `db_url` 默认值把用户名 `auston` 硬编码了,换人部署会迷惑。改成 `""` 或 raise 强制 env 覆盖。
- **`config.py:24-25`** `audio_dir` / `video_dir` 默认 `/tmp/voxpress/...`,macOS 重启后被清掉,OSS 没启用时媒体就消失了。默认指向项目目录下的 `.voxpress-cache/` 更稳妥。
- **`models.py:76`** `Video.likes` 用 `Integer`,头部博主单条点赞会破 2^31。改 `BigInteger`。
- **`routers/tasks.py:27-37`** `_url_kind()` 只白名单 `v.douyin.com` / `douyin.com/video/` / `douyin.com/user/`,未处理带参数的完整链接(比如 `?from_scene=...`),也没约束 URL 长度。建议加 `max_length=2048` + 用 `urllib.parse.urlparse` 做协议+域名校验。
- **`routers/resolve.py:39-41`** 错误信息"链接不能为空/非抖音域名"泄露了具体判断逻辑,虽然对本地工具影响小,但不利于以后多租户化。
- **`routers/articles.py:162`** Content-Disposition 拼接 `article_id`,UUID 安全,但最佳实践是 `filename="..."` + RFC 5987 `filename*=UTF-8''...` 同时给。
- **`main.py:27-29`** `lifespan` 回调体为空,`yield` 前后什么都没有。以后加 httpx client 生命周期、后台任务初始化时容易忘位置。至少留一个 `logger.info("voxpress started")`。
- **`worker.py:258-261`** `_done` 回调里 `active.discard(t)`,没有显式读 `t.exception()`,task 内部抛异常不会冒泡。但因为 `_run_claimed_task` 已经兜底 catch 了所有异常,**这个 Minor 是"没坏但以后别人改会坏"**,建议加注释说明。
- **`alembic/versions/9c1c9e4d6f21_...`** 先 `add_column(..., server_default="0")` 再 `alter_column(..., server_default=None)`,两步操作在已有行的库上会让新列先有默认值再失去默认值。风险小但写得拧巴,合并成一步更清晰。
- **`markdown.py:26-30`** `word_count_cn` 对纯英文/数字的文章会算低。现在文章都是中文应该没事,但如果以后接 YouTube 英文博主就不准了 —— 留个 TODO。
- **`routers/creators.py:35-39`** `name.ilike(f"%{q}%")` 没有索引,数据上万后会慢。配合 M8 的 pg_trgm 索引再解决。

---

## 亮点 —— 值得保留的决策

1. **租约 + 心跳 + `FOR UPDATE SKIP LOCKED`**(`task_store.py:75-113`)：并发抢占 + 僵尸回收 + 再入队,这套在本地单机已经超规格了,上生产也能用。
2. **子进程隔离转写**(`worker.py:121-133`)：把 mlx-whisper 放独立进程跑,Metal 崩溃不会带崩 worker/API,这是正确的稳定性决策。
3. **Postgres 作为事件总线**(`sse.py` + `task_store.emit_*`)：避开 Redis/内存队列依赖,API 和 worker 通过 LISTEN/NOTIFY 解耦,重启任一方都自愈。
4. **OSS 媒体归档 + 本地缓存优先**(`runner.py:82-225`)：`_restore_cached_extract` + `_find_local_audio` + OSS fallback 这套降级路径考虑到了"下载过就不重下",节省抖音反爬的压力。
5. **Stub / Real pipeline 切换**(`pipeline/__init__.py` 看 `settings.pipeline`)：不用真实后端也能跑通全流程,调试体验好。
6. **`idx_tasks_stage_ready(stage, status, run_after)`**(`models.py:171`)：完全覆盖 `claim_next_task()` 的扫描条件,不是拍脑袋加的索引。

---

## 建议的修复顺序

| 优先级 | 任务 | 预估 |
|---|---|---|
| P0 | B2 子进程管道读取、B1 SSE 丢事件日志、B3 取消信号 | 3 小时 |
| P0 | M1.1 Whisper initial_prompt 接入(最高性价比) | 30 分钟 |
| P1 | M1.2 纠错阶段 + M1.3 背景注(补齐设计承诺) | 6–8 小时 |
| P1 | M3 LLM 输出校验、M2 N+1、M4 cookie 脱敏 | 2 小时 |
| P2 | M5 代理大小限制、M6 attempt 熔断、M7 批量 gather | 1 小时 |
| P3 | M8 向量/trgm 索引(如果不做就把 README 对应行删掉) | 2 小时 |
| P3 | 全部 Minor 一起清 | 1 小时 |

---

## 给 Codex 的一句话回推

> 把 `REVIEW.md` 里的 Blocker 3 条 + Major 8 条逐条修掉,每修一条在 commit message 里引用编号(B1 / M3 …)。纠错阶段和背景注(M1.2 / M1.3)可以先开一张单独的 PR,因为要改 schema 和加新 migration,不要和其他修复混在一起。
