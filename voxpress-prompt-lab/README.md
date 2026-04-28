# voxpress-prompt-lab

VoxPress（SpeechFolio）的 organize 阶段 **prompt 调优 + eval 工作台**。完全独立项目，不依赖、不修改 `voxpress-api/`。

## 这个项目要解决什么

`voxpress-api` 当前的 organize 阶段是**单轮 prompt**，质量天花板看不见——每次"调优"都是在没有 eval 的情况下凭感觉评估。

本项目提供：

1. **Eval set**：把代表性的 ASR transcript + 你认为"优 / 中 / 差"的参考输出整理成结构化 case
2. **Pipeline 切换**：在 `single_pass`（复刻线上 baseline）和 `multi_pass`（outline → draft → polish）之间一键对照
3. **Prompt 版本化**：每套 prompt 是一个目录，可以并存 `v0`、`v1`、`v1.1`...
4. **Side-by-side diff**：两个版本的输出对同一 case 并排展示，用浏览器打开就能看
5. **Token / 成本核算**：每次 run 自动统计费用，避免悄悄烧钱

## 目录结构

```
voxpress-prompt-lab/
├── pl/                    # 工具包
│   ├── config.py          # 加载 .env、模型配置
│   ├── llm.py             # DashScope (OpenAI 兼容) 客户端
│   ├── preprocess.py      # ASR 文本清洗（口头禅、重复字）
│   ├── pipeline.py        # single_pass / multi_pass 执行器
│   ├── runner.py          # 跑 cases × version
│   ├── diff.py            # 生成 side-by-side HTML
│   ├── cli.py             # `pl run` / `pl diff`
│   └── prompts/           # 各版本 prompt 文件
│       ├── v0_single/     # 单轮 baseline（粘贴你 voxpress 现行 prompt）
│       │   └── prompt.txt
│       └── v1_multi/      # 多轮 outline → draft → polish
│           ├── outline.txt
│           ├── draft.txt
│           └── polish.txt
├── cases/                 # 你手动准备的 eval case
│   ├── _template.json
│   └── case_001.json      # （你自己加）
├── runs/                  # 运行产物（gitignore）
│   └── 2026-04-28T1530-v1_multi/
│       ├── meta.json
│       ├── case_001.json
│       └── ...
├── pyproject.toml
├── .env.example
└── README.md
```

## 第一次跑通的步骤（用 uv 管理）

> 没装 uv 先一键装：`curl -LsSf https://astral.sh/uv/install.sh | sh`

```bash
# 1. 安装依赖（自动创建 .venv 并装好所有包）
cd voxpress-prompt-lab
uv sync

# 2. 配 .env
cp .env.example .env
# 填入 DASHSCOPE_API_KEY=sk-...

# 3. 准备 1 个 case（最快验证 pipeline 可跑）
cp cases/_template.json cases/case_001.json
# 编辑 case_001.json，把 transcript 字段填上一段真实的 ASR 文本

# 4. 跑 baseline
uv run pl run --version v0_single --cases cases/case_001.json

# 5. 跑 multi-pass
uv run pl run --version v1_multi --cases cases/case_001.json

# 6. 列出最近的 run，挑两个做 diff
uv run pl list-runs

# 7. 对比
uv run pl diff \
  --a runs/<v0_single 的 run 目录> \
  --b runs/<v1_multi 的 run 目录> \
  --out diff.html
open diff.html
```

**也可以激活 venv 后直接用 `pl`**：

```bash
source .venv/bin/activate
pl run --version v0_single --cases cases/
```

**常用 uv 命令**：

| 命令 | 用途 |
|---|---|
| `uv sync` | 安装/同步 pyproject 中声明的所有依赖到 `.venv/` |
| `uv add <pkg>` | 加新依赖（同步写入 pyproject.toml + uv.lock） |
| `uv remove <pkg>` | 删依赖 |
| `uv run <cmd>` | 在项目 venv 里跑命令，无需手动 activate |
| `uv lock --upgrade` | 升级所有依赖到最新可解 |
| `uv python pin 3.12` | 锁定 Python 版本（已写在 `.python-version`） |

## 完整工作流（建议节奏）

**Day 1**：
- 选 8–10 个 case（不同视频长度、不同主题、不同质量）
- 把 ASR transcript 准备好（可以从 voxpress DB 里 copy 出来）
- 标"优 / 中 / 差" + 1–2 句"为什么"

**Day 2**：
- 把 voxpress 现行 organize prompt 粘到 `pl/prompts/v0_single/prompt.txt`
- 跑 v0 baseline，人工评分作为对照基准

**Day 3–5**：
- 跑 v1_multi，对比 v0 vs v1 在同一 case 上的输出
- 针对 v1 暴露的失败模式改 prompt → 复制成 v1_1_multi → 再跑
- 每次只改一组 prompt，方便归因

**Day 6**：
- 选定胜出版本
- 把胜出 prompt 同步回 voxpress-api 的 settings（不是改代码 hardcode）

## 设计原则

- **不动 voxpress-api 的代码**：本项目用自己的 DashScope client，自己的 model 配置，自己的依赖
- **不连 voxpress 数据库**：case 用本地 JSON，避免误改产线
- **可复读、可追溯**：每次 run 写 `meta.json` 记录 prompt 版本 / 模型 / 参数 / 费用 / git hash
- **零 LLM-as-judge（v0）**：评分先靠人，等有了 50+ case 再考虑 LLM judge

## 后续延伸（不在 v0 范围）

- LLM-as-judge：用 qwen-max 或 Claude 给 qwen3.6-plus 的输出打分
- 用户 UI 反馈回灌：从 voxpress 的 👍/👎 反馈拉数据当 eval 集
- 多模型对比：同一 prompt 在 qwen3.6-plus / qwen-max / claude / gpt 上跑
- 自动化 prompt 搜索：DSPy / 类似框架的自动迭代
