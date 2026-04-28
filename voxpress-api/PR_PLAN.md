# VoxPress 云端化迁移 PR 计划

**版本**：v1.0
**更新日期**：2026-04-23
**作者**：Review 产出
**关联文档**：[`REVIEW.md`](./REVIEW.md)、[`ARCHITECTURE.md`](./ARCHITECTURE.md)

---

## 1. 背景与目标

VoxPress 在最近一次迭代里完成了三件事：
1. **ASR 从 mlx-whisper 切换到阿里云 DashScope `qwen3-asr-flash-filetrans`**
2. **Organize 从本地 Ollama qwen2.5:72b 切换到 qwen-plus**
3. **新增 Correct 阶段（qwen-turbo）**

切换后暴露出三类问题：
- 代码里残留 mlx/ollama/jobs 三套死代码，命名（`whisper`）与实际（qwen ASR）不一致
- 架构层面的小瑕疵：`StageConcurrencyResolver` 只能降不能升、`transcribe_concurrency=1` 是 Metal 时代遗留、correct 失败即降级无重试
- 一次真实样本显示 `background_notes` 误把政治代称（西大/朗茨/黄毛）解读为商业实体

本计划把上述问题拆成 **6 个独立可合并的 PR**，按 ROI+风险递增排序，每个 PR 小、可回滚、可独立测。

### 关键前置发现（Codex 已完成的部分）

在审阅 `voxpress/prompts.py` 时发现：

- `DEFAULT_BACKGROUND_NOTES_TEMPLATE` 已经更新，**明确包含**上次错误违反的所有规则（不要把政治人物解释成某企业、context 不是摘要、只输出 high/medium、aliases 最多 4 条）
- `DEFAULT_ORGANIZER_TEMPLATE` 已经加上"保留火候"第 7 条

换言之：**Prompt 层已经修过了**。用户在 UI 里看到的 `prompt.version: v1.0` 是**过旧的运行时配置**，没有反映最新的 `prompts.py`。所以 PR 1 不是"去改 prompt"，而是"**验证新 prompt 是否修好了 + 同步运行时配置 + 历史文章回刷**"。

---

## 2. 非目标（Out of Scope）

- **不处理 REVIEW.md 里的 B1/B2/B3 Blocker**。这些在 PR 计划之外另行修复（B2 子进程 pipe 死锁已因切换云 ASR 自然消失）。
- **不改动前端**。所有 API 契约保持向后兼容；PR 4 的重命名通过双 key 读写实现平滑过渡。
- **不引入新的外部依赖**。继续用现有的 httpx + asyncpg + DashScope。
- **不做分布式多 worker 部署**。仍按单机 API 进程 + 单机 worker 进程的现状。

---

## 3. PR 概览

| PR | 主题 | 工作量 | 风险 | 依赖 | 关联 REVIEW 项 |
|---|---|---|---|---|---|
| **PR 0** | 背景注回归 fixture | 0.5 天 | 极低 | 无 | — |
| **PR 1** | 背景注 prompt 升级验证 + 历史回刷 | 1 天 | 低 | PR 0 | — |
| **PR 2** | 修 `StageConcurrencyResolver` + 放开 `transcribe_concurrency` | 0.5 天 | 低 | 无 | — |
| **PR 3** | Correct 失败重试 + 统一 `attempt_count` 上限 | 1 天 | 中 | 无 | M6 |
| **PR 4** | 清死代码 + `whisper → asr` 重命名 | 1 天 | 中 | PR 2/3 合并后 | — |
| **PR 5**（可选） | Organize + 背景注合并为一次 LLM 调用 | 1.5 天 | 中 | PR 1 验证完 | — |

**总工作量**：~5.5 天（单人串行）；两人并行可压缩到 3 天内。

---

## 4. 依赖关系与合并顺序

```
Day 1   │ PR 0  (fixture)  ─┐
        │ PR 2  (并发)     ─┼─  互不依赖,并行
        │                   │
Day 2   │ PR 1  (回刷)    ◀─┘   依赖 PR 0 的 fixture 结论
        │
Day 3   │ PR 3  (重试)
        │
Day 4   │ PR 4  (清死代码 + 重命名)
        │
Day 5   │ PR 5  (合并调用, 可选)
        │
Day 6+  │ 生产观察期: 3 天追踪 DashScope 账单与 token 曲线
```

---

## 5. PR 规格详表

### PR 0 — 背景注回归 fixture

**目的**：把"舆论战是商战的正面战场"这条视频固化成可重复的回归用例；以后任何改动 prompt 或切换模型，都能一键 diff。

**改动清单**：

| 文件 | 操作 |
|---|---|
| `tests/fixtures/background_notes/yulun_zhan.json` | **新建**。包含 `{transcript, title_hint, creator_hint, expected_aliases, expected_no_patterns}` |
| `tests/pipeline/test_background_notes_regression.py` | **新建**。调用 live DashScope（pytest mark=slow），断言输出不命中 `expected_no_patterns` |
| `pyproject.toml` 或 `pytest.ini` | 注册 `slow` marker，`pytest -m slow` 单独跑 |

**fixture 示例结构**：

```json
{
  "source_url": "https://www.douyin.com/video/...",
  "title_hint": "...",
  "creator_hint": "Jinqiangdashu2",
  "transcript": "(原始逐字稿全文)",
  "expected_aliases": [
    {
      "term": "西大",
      "refers_to_contains": ["美", "西方"],
      "confidence_in": ["high", "medium"]
    },
    {
      "term": "朗茨",
      "refers_to_contains": ["伊朗"],
      "confidence_in": ["high", "medium"]
    }
  ],
  "expected_no_patterns": [
    "某大型跨国科技企业",
    "某头部中国科技公司",
    "虚构国名",
    "全文以.*为引子.*实则"
  ]
}
```

**测试步骤**：
```bash
pytest -m slow tests/pipeline/test_background_notes_regression.py -v
```

**期望结果**：基于当前 `prompts.py` + qwen-plus，fixture 应当 **pass**。
- 若 pass：确认最新 prompt 已修复问题，PR 1 走 "A 路径"（只回刷历史）
- 若 fail：PR 1 走 "B 路径"（继续加强 prompt）

**风险**：极低。不改生产代码。

**验收标准**：
- `pytest -m slow` 能跑
- fixture 文件提交到 git
- 在 PR 描述里附上一次 live 运行的 stdout，标注 pass/fail 状态

---

### PR 1 — 背景注 prompt 升级验证 + 历史回刷

**前提**：PR 0 的回归已跑过一次，确定 pass/fail 状态。

#### 情况 A：PR 0 pass（推荐路径）

**改动清单**：

| 文件 | 操作 |
|---|---|
| `voxpress/jobs/rebackfill_background_notes.py` | **新建**。批量回刷历史 Article 的背景注 |
| `voxpress/routers/settings.py` | **新增**端点 `POST /api/settings/prompt/upgrade`（`from_version, to_version, dry_run`） |
| 数据库 `settings` 表 | 通过新端点把 `prompt.template` 从 v1.0 升到当前 `DEFAULT_ORGANIZER_TEMPLATE` |
| `voxpress/prompts.py` | **不动** |
| `voxpress/pipeline/dashscope.py` | **不动** |

**回刷脚本交互**：

```bash
# 1. dry-run: 看看哪些文章会被 overwrite,diff 写到 CSV
python -m voxpress.jobs.rebackfill_background_notes \
  --since 2026-04-01 --dry-run --out /tmp/bn_diff.csv

# 2. 人工 review CSV 里的 diff

# 3. 实际写回(走备份表避免误伤)
python -m voxpress.jobs.rebackfill_background_notes \
  --since 2026-04-01 --apply --backup-table articles_background_notes_v1
```

**回刷脚本要点**：
- 并发控制：默认 `--concurrency 2`，遵守 qwen-plus RPM
- 限额控制：`--max-articles 100` 防跑飞
- 幂等：记录每次 run 的 `run_id`，重跑同 run_id 自动跳过已处理文章
- 备份：写入前把旧 `background_notes` 存到 `articles_background_notes_v1` 表（一次性 migration 创建）

#### 情况 B：PR 0 fail（备用路径）

**改动清单**：

| 文件 | 操作 |
|---|---|
| `voxpress/prompts.py` | 在 `DEFAULT_BACKGROUND_NOTES_TEMPLATE` 末尾加反例段 |
| `voxpress/pipeline/dashscope.py:165` | `annotate_background` 的 user prompt 末尾追加一句硬约束 |
| 其余与情况 A 相同 |

**prompt 反例段（新增内容）**：

```
━━ 反例(不要这样输出) ━━
错 ▶ {"aliases":[{"term":"西大","refers_to":"某大型跨国科技企业"}],
     "context":"全文以美伊冲突为引子,实则聚焦商业传播"}
对 ▶ {"aliases":[{"term":"西大","refers_to":"美国","confidence":"medium"}],
     "context":"作者引用 2025 年美伊军事对峙作为类比素材"}
```

**user prompt 追加（`dashscope.py:181` 之后）**：

```python
user += (
    "\n⚠ 当 aliases 含政治实体时,context 不要写成"
    "'全文以 X 为引子,实则聚焦 Y' 的总评结构。"
)
```

**验收标准**：
- PR 0 的 fixture 必须 pass
- 随机抽 5 条已完成 Article 回刷，人工 review 新旧 `background_notes` diff，主观评估"新的不比旧的差"
- `articles_background_notes_v1` 备份表存在，可回退

**风险**：低。背景注生成是独立调用，降级也就是回到"没背景注"。

---

### PR 2 — 修 `StageConcurrencyResolver` + 放开 `transcribe_concurrency`

**问题定位**：

`voxpress/worker.py:46-60`（`StageConcurrencyResolver.get`）当前逻辑：

```python
limit = fallback  # = organize_concurrency(=2) 或 correct_concurrency(=1)
if isinstance(value, int):  # value = settings.llm.concurrency
    limit = max(1, min(fallback, value))  # ← 只能 cap 不能 raise
```

导致即使 UI 里把 `llm.concurrency` 调到 8，实际 organize 仍被 `organize_concurrency=2` 封顶。

**改动清单**：

| 文件 | 操作 |
|---|---|
| `voxpress/worker.py:46` | 修 `StageConcurrencyResolver.get` 允许双向生效 |
| `voxpress/config.py` | 新增 `organize_concurrency_max: int = Field(default=20, ge=1, le=50)` |
| `voxpress/config.py` | 新增 `correct_concurrency_max: int = Field(default=20, ge=1, le=50)` |
| `voxpress/config.py:28` | `transcribe_concurrency: int = Field(default=4, ge=1, le=20)` （原 default=1） |
| `voxpress/config.py` 注释 | 标注 `transcribe_concurrency` 不再是 Metal 限制 |

**新逻辑**：

```python
async def get(self, stage: str, fallback: int) -> int:
    if stage not in {"organize", "correct"}:
        return fallback
    # 2s 缓存保留
    ...
    ceiling_map = {
        "organize": settings.organize_concurrency_max,
        "correct": settings.correct_concurrency_max,
    }
    ceiling = ceiling_map[stage]
    if isinstance(value, int):
        limit = max(1, min(ceiling, value))  # 允许突破 fallback,不超硬上限
    else:
        limit = fallback
    return limit
```

**测试**：

| 场景 | 配置 | 期望 |
|---|---|---|
| 默认配置 | `llm.concurrency` 未设 | `get("organize", 2) == 2` |
| UI 调大 | `llm.concurrency=8` | `get("organize", 2) == 8` |
| 超上限 | `llm.concurrency=100` | `get("organize", 2) == 20`（被 `organize_concurrency_max` 封） |
| 调小 | `llm.concurrency=1` | `get("organize", 2) == 1` |
| 非 LLM stage | — | `get("download", 4) == 4`（resolver 直接返回 fallback） |

**风险**：低。硬上限 `organize_concurrency_max` 防 RPM 超限。

**附带收益**：`transcribe_concurrency` 瓶颈顺便解除。

**验收标准**：
- 单元测试覆盖 5 个场景
- UI 调节 `llm.concurrency` 生效，观察 organize 实际在跑的协程数吻合

---

### PR 3 — Correct 失败重试 + 统一 `attempt_count` 上限

**问题定位**：

1. `voxpress/pipeline/runner.py:290-297`（`correct_stage` except 分支）直接把 `correction_status='failed'` 落库，**无重试**。一次 DashScope 429 就永久降级。
2. `voxpress/task_store.py:75-113`（`claim_next_task`）`attempt_count += 1` **无上限**，任务可无限重试（REVIEW M6）。

**改动清单**：

| 文件 | 操作 |
|---|---|
| `voxpress/pipeline/runner.py:290` | `except` 改成 `raise`，让 worker 走 retry |
| `voxpress/config.py` | 新增每个 stage 的 `max_attempts` 上限配置 |
| `voxpress/task_store.py:claim_next_task` | 检查 `attempt_count >= max_attempts` 时走降级分支 |
| `voxpress/task_store.py` | 新增 `compute_backoff(attempt_count) -> seconds` 指数退避 |
| `voxpress/worker.py:_process_correct` | 捕获降级信号时跳到 `organize`，不进 `failed` |

**新增 config 字段**：

```python
# voxpress/config.py
max_download_attempts: int = Field(default=5, ge=1, le=20)
max_transcribe_attempts: int = Field(default=3, ge=1, le=10)
max_correct_attempts: int = Field(default=3, ge=1, le=10)
max_organize_attempts: int = Field(default=2, ge=1, le=10)
max_save_attempts: int = Field(default=5, ge=1, le=20)
retry_backoff_base_sec: int = Field(default=30, ge=1, le=600)
```

**指数退避公式**：

```python
# voxpress/task_store.py
def compute_backoff(attempt_count: int, base: int) -> int:
    """return seconds to wait before retry"""
    return base * (attempt_count ** 2)  # 30s, 120s, 270s, 480s, ...
```

**`claim_next_task` 内部新逻辑**（伪代码）：

```python
max_map = {...}
if task.attempt_count >= max_map[task.stage]:
    if task.stage == "correct":
        # 非关键 stage: 降级为 skipped, 继续推进
        mark_correct_skipped(task_id)
        queue_next_stage(task_id, stage="organize", ...)
    else:
        # 关键 stage: 真正失败
        mark_task_failed(task_id, error="exceeded max attempts")
    # 不把任务分配给当前 worker,跳过
    continue
else:
    # 正常 claim + run_after = now + compute_backoff(...)
    ...
```

**测试**：

| 场景 | 期望 |
|---|---|
| Correct 连续 3 次失败 | `correction_status='skipped'`，任务进 organize |
| Correct 前 2 次 failed 第 3 次 success | `correction_status='ok'` |
| Organize 连续 2 次失败 | `tasks.status='failed'`，不再重试 |
| `run_after` 指数增长 | 失败 3 次后约等下次 4.5 分钟 |

**风险**：中。改动队列核心逻辑 `claim_next_task`。必须有单元测试覆盖 `attempt_count` 和 `run_after` 的交互。

**验收标准**：
- 单元测试全过
- 模拟注入故障：mock DashScope 返回 429，观察任务行为
- `tasks` 表里没有 `attempt_count > max_*` 的僵尸任务

---

### PR 4 — 清死代码 + `whisper → asr` 重命名

**前置**：PR 2/3 合并后再做，避免合并冲突。

**改动清单**：

| 文件 | 操作 |
|---|---|
| `voxpress/pipeline/mlx.py` | **删除**（~326 行） |
| `voxpress/pipeline/ollama.py` | **删除**（161 行） |
| `voxpress/jobs/transcribe.py` | **删除**（mlx subprocess 入口） |
| `voxpress/jobs/__init__.py` | 保留（PR 1 的 rebackfill 放这） |
| `voxpress/config.py` | `transcribe_concurrency` 注释明确说明：已不是 Metal 限制 |
| `voxpress/pipeline/runner.py` | `current_whisper_*` → `current_asr_*`；`build_initial_prompt` → `build_asr_context_prompt`；`_transcriber_backend` 内部变量重命名 |
| `voxpress/worker.py` | 调用点跟着改 |
| `voxpress/pipeline/runner.py:_normalize_runtime_settings` | 把 key `whisper` 改成 `asr`；同时处理旧 key（下方迁移策略） |
| `voxpress/routers/settings.py` | 对外 API 契约保持 `whisper` 字段别名 |
| `voxpress/schemas.py` | Pydantic 模型同时接受 `whisper` 和 `asr` 字段（Field alias） |
| 数据库 `settings` 表 | 不做 schema migration；代码层双 key 读写兼容 6 个月 |

**迁移策略（关键）**：

```python
# voxpress/pipeline/runner.py
async def _load_settings_entry(self, key: str) -> dict | None:
    # 向后兼容: asr 优先, whisper 作为回退
    async with session_scope() as s:
        if key == "asr":
            row = await s.get(SettingEntry, "asr")
            if row is None:
                row = await s.get(SettingEntry, "whisper")  # 旧 key 回退
        else:
            row = await s.get(SettingEntry, key)
        return _normalize_runtime_settings(key, row.value if row else None)
```

写入时**只写新 key** `asr`，读取时**两个 key 都尝试**。6 个月后（2026-10 月）再做 data migration 删除旧 key。

**校验清单**：

```bash
# 删除 mlx/ollama 后应无引用
grep -r "mlx_whisper\|OllamaLLM\|pipeline.mlx\|pipeline.ollama" voxpress/ --exclude-dir=.venv
# 期望: 无输出

# 新旧配置 key 读写测试
curl http://localhost:8787/api/settings | jq .asr   # 新
curl http://localhost:8787/api/settings | jq .whisper  # 兼容别名
```

**风险**：中。改动面广但机械，靠 grep + 全量测试兜底。

**验收标准**：
- 所有现有测试 pass
- `grep -r "mlx\|ollama"` 返回空（除 `.venv/`）
- 手动：UI 读写 settings 一次，新旧 API 路径都工作
- 回滚演练：能 revert 此 PR 不破坏运行态

---

### PR 5 —（可选）Organize + 背景注合并为一次 LLM 调用

**前提**：PR 0/1 完成后，根据 fixture 回归质量数据决定是否做。

**问题**：

`voxpress/pipeline/runner.py:organize_stage` 当前调 **2 次** qwen-plus：

```python
organized = await llm.organize(...)                 # 调用 1
if generate_background_notes:
    organized["background_notes"] = await llm.annotate_background(...)  # 调用 2
```

这导致：
- Token 成本翻倍（~0.006 + ~0.009 = ~0.015 元/篇）
- 背景注的 prompt 只看到 transcript + title + summary，**没看到正文结构**，更容易飘离主题
- 两次独立调用无法互相参考

**改动清单**：

| 文件 | 操作 |
|---|---|
| `voxpress/prompts.py` | 合并两个模板为一个 `DEFAULT_UNIFIED_ORGANIZER_TEMPLATE` |
| `voxpress/pipeline/dashscope.py:organize()` | 一次性输出 `{title, summary, content_md, tags, background_notes}` |
| `voxpress/pipeline/runner.py:organize_stage` | 若 `background_notes_enabled=true`，从 organize 结果直接取；保留 `annotate_background` 接口以防未来需要拆回 |
| `voxpress/pipeline/protocols.py` | `LLMBackend.annotate_background` 接口保留（不删） |

**合并后 JSON schema**：

```json
{
  "title": "...",
  "summary": "...",
  "content_md": "...",
  "tags": ["..."],
  "background_notes": {
    "aliases": [{"term": "", "refers_to": "", "confidence": "high|medium"}],
    "context": "..."
  }
}
```

**指标**：

| 指标 | 合并前 | 合并后（目标） |
|---|---|---|
| 每篇 Token 成本 | ~0.015 元 | ~0.010 元（降约 30%） |
| 每篇 LLM 延迟 | ~18s | ~12s |
| 背景注质量 | PR 0 fixture 基线 | **不得退化** |

**回归**：必须跑 PR 0 的 fixture，对比合并前后 `background_notes` 质量。如果退化，PR 5 **不合并**。

**风险**：中。两步合一步会让单次 prompt 变长（~3500 → ~5000 tokens），qwen-plus 对长 prompt 的结构化输出稳定性可能下降。

**验收标准**：
- PR 0 fixture pass
- 随机抽 10 篇已完成 Article 重跑，人工对比质量
- DashScope 账单连续 3 天观察，确认 token 消耗下降符合预期

---

## 6. 统一验收与回滚策略

### 每个 PR 的验收门槛

1. **单元测试**：新增代码 > 30 行必须有对应单测；修改现有逻辑必须扩展已有单测
2. **回归测试**：PR 0 的 fixture 每个 PR 都跑一遍（除 PR 0 本身）
3. **冒烟测试**：PR 合并前手动抽 3 条真实抖音链接跑完整 pipeline，人工 review 结果
4. **观察期**：合并后至少观察 1 天，确认 DashScope 账单、`tasks.status='failed'` 比例无异常

### 回滚策略

所有 PR 按**纯代码或配置改动**设计，**不含 schema migration**：

| PR | 回滚方式 |
|---|---|
| PR 0 | `git revert` |
| PR 1 | `git revert` 代码 + 从 `articles_background_notes_v1` 备份表恢复数据 |
| PR 2 | `git revert`；新增的 env var 不设就走 fallback，无副作用 |
| PR 3 | `git revert`；对于已 retry 多次的任务手动 `UPDATE tasks SET attempt_count=0` |
| PR 4 | `git revert`；因双 key 读写兼容，恢复后立即正常工作 |
| PR 5 | `git revert`；恢复两次 LLM 调用，历史数据不受影响 |

### 统一观测

每次合并后观察以下指标至少 1 天：

- `tasks.status='failed'` 比例（应 ≤ 3%）
- 平均端到端耗时（应不增长 > 20%）
- DashScope 日账单（应与预测一致）
- `/healthz` 可用性（应 100%）

---

## 7. 风险登记

| 风险 | 可能性 | 影响 | 缓解 |
|---|---|---|---|
| PR 0 的 fixture 因 qwen-plus 输出不稳定而 flaky | 中 | 测试 false positive | fixture 用 `refers_to_contains` 模糊匹配、多次重跑取多数 |
| PR 3 的重试逻辑把 RPM 打爆 | 低 | 429 雪崩 | 指数退避 + `run_after` 分散 |
| PR 4 的 `whisper → asr` 重命名漏改一处 | 中 | UI 字段缺失 | 全量 grep + Pydantic alias 双保险 |
| PR 5 合并后 qwen-plus 长 prompt 输出截断 | 中 | `content_md` 丢内容 | fixture 回归 + 拒绝合并 |
| 回刷脚本误伤生产数据 | 低 | 文章背景注被覆盖 | dry-run + 备份表 + `--apply` 需人工确认 |

---

## 8. 待定决策

在开始 PR 3 之前需要产品/技术决策：

1. **PR 3 的 `max_*_attempts` 默认值**：
   - 建议：download=5 / transcribe=3 / correct=3 / organize=2 / save=5
   - 是否采纳？

2. **PR 5 是否做**：
   - 月处理量 < 2000 篇：建议不做（ROI 低）
   - 月处理量 > 5000 篇：建议做
   - 介于中间：先看 PR 0 回归结论

3. **PR 1 回刷范围**：
   - 方案 A：只回刷 2026-04-01 后创建的文章（新功能上线以来）
   - 方案 B：回刷所有已开启 `generate_background_notes=true` 的文章
   - 默认方案 A，B 需额外沟通。

---

## 9. 附录

### 相关 REVIEW 条目追溯

| PR | REVIEW 条目 | 状态 |
|---|---|---|
| PR 3 | M6（`attempt_count` 无上限） | 本 PR 覆盖 |
| PR 2 附带 | REVIEW 里 transcribe_concurrency 建议 | 本 PR 覆盖 |
| — | B1（SSE 队列丢事件） | 不在本计划，另开 PR |
| — | B2（子进程 pipe 死锁） | 已因云 ASR 自然消失 |
| — | B3（cancel 不通知 worker） | 不在本计划 |
| — | M1（Correct 阶段缺失） | 已通过上线 DashScope corrector 解决 |
| — | M2（N+1 查询） | 不在本计划 |
| — | M5（媒体代理无 size 限制） | 不在本计划 |

### 术语表

| 术语 | 含义 |
|---|---|
| **Stage** | Pipeline 的一个阶段：download / transcribe / correct / organize / save |
| **Lease** | Worker 领取任务时加的租约，120s 超时自动释放给其他 worker |
| **背景注（background_notes）** | 文章末尾的代称别名解释 + 事件背景，由独立 LLM 调用生成 |
| **Fixture** | 固定的测试输入输出样本，用于回归对比 |
| **dry-run** | 执行逻辑但不写数据库，只输出 diff 供人工审阅 |

---

**审阅者清单**：
- [ ] 技术 lead 审阅 PR 3 的 `max_attempts` 默认值
- [ ] 产品决定 PR 5 是否列入此 cycle
- [ ] 前端确认 PR 4 的 `whisper` 字段别名保留方案
- [ ] 数据库/运维确认 PR 1 的回刷并发上限（默认 2）
