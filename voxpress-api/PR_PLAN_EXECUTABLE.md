# VoxPress 可执行 PR 计划

**版本**：v1.1  
**日期**：2026-04-23  
**基线代码**：`/Users/auston/cowork/dy_docs/voxpress-api` 当前工作区  
**说明**：本计划以“当前代码可以直接落地”为约束，优先做小步、安全、可验证的改动；把需要额外设计或 schema 变更的事项从主线里拆出去。

---

## 1. 执行结论

本轮建议按 **5 个主 PR + 1 个可选 spike** 推进：

| 顺序 | PR | 主题 | 目标 |
|---|---|---|---|
| 1 | PR 0 | 背景注回归基线 | 固化 live 回归样本，后续每个 PR 都能对比 |
| 2 | PR 1 | 背景注回刷 + prompt 元数据同步 | 回刷历史 `background_notes`，同步过时的 `prompt.version` |
| 3 | PR 2 | `StageConcurrencyResolver` 修正 | 让 UI 的 `llm.concurrency` 真正生效 |
| 4 | PR 3 | Correct 阶段重试与降级硬化 | 解决一次性 429/5xx 导致的无谓降级 |
| 5 | PR 4 | 死代码/依赖/文档清理 | 清掉 mlx/ollama 遗留，但暂不动公开 API 契约 |
| 可选 | Spike | Organize + 背景注合并调用 | 先做实验，不预设一定合并 |

本轮**不建议**直接做两件事：

- 不把 `attempt_count` 当成“失败重试次数”来做任务级熔断。
- 不在这一轮推进公开 `whisper -> asr` API / DB key 重命名。

这两项都值得做，但都不适合塞进当前主线。

---

## 2. 当前代码现实

下面这些事实已经对照当前代码确认过，后续 PR 应以它们为前提：

- `prompt.template` 在数据库里已经和 `voxpress/prompts.py` 的默认模板一致；当前过时的是 `prompt.version` 元数据，不是 prompt 正文。
- `transcribe_concurrency` 当前默认值已经是 `4`，不是 `1`。
- `correct_stage` 现在的行为是：调用失败时直接降级为原始逐字稿并继续进入 organize。
- `attempt_count` 是任务被 worker claim 的累计次数，不是某个 stage 的失败次数。
- 当前相关单测基线可用：`uv run pytest -q tests/test_background_notes.py tests/test_organize_density.py` 已通过。

由此推导出的执行原则：

- 背景注问题先用回归样本和回刷脚本解决。
- Correct 先做“调用级重试”，不碰任务队列模型。
- 清死代码先做内部和依赖层面，不碰前后端契约。

---

## 3. 主线 PR 计划

### PR 0：背景注回归基线

**目标**

- 把“舆论战是商战的正面战场”样本固化成可重复回归。
- 给后续 prompt 调整、回刷、合并调用提供统一验收标准。

**改动范围**

- 新建 `tests/fixtures/background_notes/yulun_zhan.json`
- 新建 `tests/test_background_notes_live.py`
- 在 `pyproject.toml` 里注册 `live` marker

**实现方式**

- fixture 保存 `transcript`、`title_hint`、`creator_hint`
- 断言采用宽松匹配：
  - `aliases.term` 精确匹配
  - `refers_to` 用 `contains` 子串匹配
  - `confidence` 只允许 `high|medium`
  - `expected_no_patterns` 禁止命中典型错误表达
- live 测试默认只在显式执行时运行，不进日常快速测试

**建议命令**

```bash
uv run pytest -m live tests/test_background_notes_live.py -v
```

**验收**

- 新增 fixture 可读、可复用
- live 测试能在本地显式执行
- PR 描述附一次运行结果和模型输出摘要

**回滚**

- 纯测试代码，`git revert` 即可

---

### PR 1：背景注回刷 + prompt 元数据同步

**目标**

- 在不改 prompt 正文的前提下，回刷历史文章的 `background_notes`
- 解决 UI 上 `prompt.version` 过旧的问题

**为什么这样做**

- 当前 prompt 正文已经是新版本，没必要新增 `POST /api/settings/prompt/upgrade`
- 真正需要的是：
  - 一个可控的回刷脚本
  - 一个同步 `prompt.version` 的一次性更新

**改动范围**

- 新建 `voxpress/jobs/rebackfill_background_notes.py`
- 如 UI 依赖 `prompt.version`，在脚本里同步更新 `settings.prompt.version`
- 可选：新增一个小的 helper 函数复用 `annotate_background`

**实现方式**

- 先做 `--dry-run`，输出 CSV 或 JSONL diff
- 备份旧值到文件，不新建数据库备份表
  - 示例：`logs/backfill/background_notes_backup_2026-04-23T130000Z.jsonl`
- `--apply` 时才真正写库
- 默认范围：
  - `created_at >= 2026-04-01`
  - 且文章已有 `background_notes` 或全局开关仍为开启
- 提供限流参数：
  - `--concurrency 2`
  - `--limit 100`

**建议命令**

```bash
uv run python -m voxpress.jobs.rebackfill_background_notes \
  --since 2026-04-01 \
  --dry-run \
  --out /tmp/background_notes_diff.csv

uv run python -m voxpress.jobs.rebackfill_background_notes \
  --since 2026-04-01 \
  --apply \
  --backup ./logs/backfill/background_notes_backup.jsonl
```

**验收**

- dry-run 能产出 diff 文件
- apply 前人工抽样 review 至少 5 篇 diff
- apply 后随机抽样 10 篇，确认“不比旧结果差”
- `prompt.version` 若需展示，已与当前模板版本同步

**回滚**

- 用备份 JSONL 恢复原值
- 代码侧 `git revert`

---

### PR 2：`StageConcurrencyResolver` 修正

**目标**

- 让 `/settings` 里的 `llm.concurrency` 真正影响 organize/correct 的实际并发

**当前问题**

- `StageConcurrencyResolver.get()` 现在用 `min(fallback, value)`，只能降不能升
- 因此 UI 调大并发时，organize/correct 仍会被 stage 默认值封顶

**改动范围**

- 修改 `voxpress/worker.py`
- 新增 `tests/test_worker_concurrency.py`
- 仅补充注释，不改 `transcribe_concurrency` 默认值

**实现方式**

- organize / correct 的实际并发取值改为：
  - 若数据库里存在 `llm.concurrency`，则取 `clamp(value, 1, 20)`
  - 否则回退到各自 stage 默认值
- 保留现有 2 秒缓存
- 不新增新的 `*_concurrency_max` 配置，先保持实现最小化

**验收场景**

| 场景 | 期望 |
|---|---|
| `llm.concurrency` 未设置 | organize/correct 使用 stage 默认值 |
| `llm.concurrency=1` | 实际并发为 1 |
| `llm.concurrency=8` | 实际并发为 8 |
| `llm.concurrency=100` | 实际并发被钳到 20 |
| 非 LLM stage | 仍返回原 fallback |

**建议命令**

```bash
uv run pytest -q tests/test_worker_concurrency.py
```

**回滚**

- 纯代码逻辑，`git revert` 即可

---

### PR 3：Correct 阶段重试与降级硬化

**目标**

- 解决 DashScope 一次性 429 / 5xx / timeout 导致的无谓降级
- 保留当前“失败后仍可继续 organize”的整体体验

**明确不做**

- 不在这一 PR 里修改任务队列模型
- 不在这一 PR 里用 `attempt_count` 做任务级重试/熔断

**改动范围**

- `voxpress/pipeline/dashscope.py`
- `voxpress/pipeline/runner.py`
- 新增或扩展 `tests/test_corrector.py`

**实现方式**

- 在 DashScope 对话调用层增加有界重试
  - 重试对象：`429`、`5xx`、网络超时、瞬时连接错误
  - 默认策略：最多 3 次，指数退避
- `correct_stage` 的最终语义统一为：
  - 成功纠错：`correction_status='ok'`
  - 多次重试仍失败后降级：`correction_status='skipped'`
  - 不再把“已降级继续”记成 `failed`
- worker 侧 stage run 状态也同步为 `done` 或 `skipped`，避免“任务成功但 stage 记 failed”的混乱状态

**验收**

- mock 一次瞬时失败后重试成功：最终 `correction_status='ok'`
- mock 持续 429：最终 `correction_status='skipped'`，任务继续进入 organize
- 正常成功路径无回归

**建议命令**

```bash
uv run pytest -q tests/test_corrector.py
```

**回滚**

- 纯代码逻辑，`git revert` 即可

---

### PR 4：死代码 / 依赖 / 文档清理

**目标**

- 清掉 mlx / ollama 云迁移前的遗留实现
- 同步更新 README / 架构说明 / 依赖声明

**本轮边界**

- 删除不用的实现和依赖
- 可以调整内部注释与文案
- 暂不改公开 API 字段名
- 暂不把 `settings.whisper` / `transcript.whisper_*` 改成 `asr`

**为什么这么收口**

- 公开命名重构会同时影响前端、接口、数据库键、健康检查字段
- 这件事值得做，但不该和“删死代码”绑在同一 PR 里

**改动范围**

- 删除：
  - `voxpress/pipeline/mlx.py`
  - `voxpress/pipeline/ollama.py`
  - `voxpress/jobs/transcribe.py`
- 清理依赖：
  - `pyproject.toml` 里的 `mlx-whisper`
- 更新文档：
  - `README.md`
  - `ARCHITECTURE.md`
  - 必要时 `ARCHITECTURE-DIAGRAMS.md`
- 检查残留：
  - `pipeline/corrector.py`
  - `routers/health.py`
  - 其它旧文案引用

**验收**

- 代码中不再有对 `pipeline.mlx` / `pipeline.ollama` / `jobs.transcribe` 的真实引用
- 依赖清单不再包含 `mlx-whisper`
- README 和架构文档描述与当前实现一致
- 全量测试通过

**建议命令**

```bash
uv run pytest -q
rg -n "mlx|ollama|mlx_whisper|pipeline\\.mlx|pipeline\\.ollama" voxpress README.md ARCHITECTURE.md
```

**回滚**

- `git revert`

---

## 4. 可选 Spike：Organize + 背景注合并调用

这项只建议做 **spike / 实验分支**，不建议先排进主线。

**前置门槛**

- PR 0 已建立 live 基线
- PR 1 回刷结果稳定
- 已拿到真实成本和耗时基线

**实验目标**

- 验证一次调用能否同时产出：
  - `title`
  - `summary`
  - `content_md`
  - `tags`
  - `background_notes`

**必须满足的合并条件**

- live 回归不退化
- 10 篇真实样本人工 review 通过
- token 成本和平均延迟有明确下降

**若任一条件不满足**

- spike 停在实验分支，不合并主线

---

## 5. 本轮明确延后项

### A. 任务级重试模型 / `attempt_count` 语义修正

原因：

- 当前 `attempt_count` 是累计 claim 次数，不是某 stage 的失败次数
- 要做对，需要新的计数语义或新增字段
- 这件事更像单独的“任务调度模型 PR”，不适合夹在当前云迁移收尾里

后续建议：

- 单独出设计文档
- 明确是否新增：
  - `stage_attempt_count`
  - `retry_after`
  - 或独立的 stage retry 记录

### B. 公开 `whisper -> asr` 重命名

原因：

- 牵涉前端、Pydantic schema、settings key、健康检查字段、历史兼容
- 可做，但需要一轮完整兼容方案

后续建议：

- 等前端确认后单独做一轮“兼容 + 别名 + 清理”

---

## 6. 建议排期

单人串行建议：

| 日期 | 内容 |
|---|---|
| 2026-04-24 | PR 0 + PR 2 |
| 2026-04-25 | PR 1 |
| 2026-04-26 | PR 3 |
| 2026-04-27 | PR 4 |
| 2026-04-28 起 | 观察期；如有需要再开 spike |

两人并行建议：

- 人员 A：PR 0 -> PR 1
- 人员 B：PR 2 -> PR 3
- PR 4 等前面合并后收尾

---

## 7. 统一验收口径

每个主 PR 合并前至少满足：

1. 新逻辑有对应测试或脚本验证
2. `uv run pytest -q` 不退化
3. 背景注相关改动都回跑 PR 0 的 live 基线
4. 对真实样本至少做一次人工 review

合并后观察项：

- `tasks.status='failed'` 比例
- 平均端到端耗时
- DashScope 日账单
- 回刷脚本日志和错误率

---

## 8. 决策建议

当前建议直接采纳的决策：

- 本轮按 5 个主 PR 推进，暂不做任务级 retry 重构
- PR 1 用“文件备份 + dry-run/apply”，不建数据库备份表
- PR 4 只清代码与依赖，不动公开 `whisper` 契约
- Organize + 背景注合并调用先做 spike，不直接排入主线
