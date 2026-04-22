# VoxPress · 设计文档

> **项目**：VoxPress —— 把视频口播内容变成可读文章的个人工具
> **名字来源**：Vox（拉丁语"声音"）+ Press（印刷/出版）
> **版本**：v0.6（设计阶段）
> **日期**：2026-04-21
> **目标平台**：macOS（M5 Max / 128GB）本地运行
> **MVP 对接平台**：抖音；架构上多平台可扩展
>
> **v0.2 更新**：扩展博主/视频元数据字段；数据库改用 PostgreSQL 16 + pgvector。
> **v0.3 更新**：MVP 只集成 Ollama，Claude 后端推迟到后续版本（抽象接口保留，便于后接）。
> **v0.4 更新**：项目正式命名为 VoxPress。目录结构、包名、数据库名、启动命令全部同步。
> **v0.5 更新**：基于首版实测结果新增两项质量增强——转写纠错阶段（6.5 节）和背景注机制（7.4 节）。Pipeline 从 4 段变 5 段。
> **v0.6 更新**：文档正式对齐当前已实现后端架构——`FastAPI 控制层 + 独立 worker + Postgres 持久化任务队列 + LISTEN/NOTIFY SSE`。同时把本次功能设计落到真实 schema 和现有目录结构上，不再按旧的单进程骨架方案书写。

---

## 一、项目概述

**VoxPress** 把视频博主的口播内容自动转写成结构化的文章库。MVP 对接抖音，架构上为多平台预留扩展点（YouTube / B 站 / 小红书 / 播客等），首版单机运行、个人使用。

名字寓意："vox"（声音）经由"press"（印刷）成为文字。每一条视频都是一次从声波到铅字的转化。

### 1.1 核心使用场景

- 关注的博主持续更新，想沉淀成可搜索、可回顾的文字资料
- 把对谈类、干货类视频转成文章，方便二次消化或引用
- 建立个人知识库，为后续语义搜索、主题聚类和高质量重写打基础

### 1.2 核心价值

把"被动刷视频"转为"主动读文章"。视频是线性媒介，文章是随机访问媒介——转换之后可检索、可标注、可引用、可分享。

---

## 二、功能范围

### 2.1 MVP 功能（首版交付）

- 提交单条抖音视频链接 → 输出一篇 Markdown 文章
- 提交抖音博主主页链接 → 拉取视频列表 → 用户选择要处理的视频 → 批量生成文章
- 每篇文章自带完整溯源信息：博主（抖音号、昵称、粉丝数、认证等）+ 视频（标题、发布时间、点赞/评论/转发/收藏/播放量、封面、原链接）
- 文章整理使用本地 Ollama（Qwen2.5-72B 或其他已安装模型），接口层为未来接入 Claude 预留扩展
- 博主库视图：按博主分组展示视频与文章，显示博主粉丝、获赞等聚合数据
- 文章阅读页：并排显示逐字稿和整理后的文章，支持原稿/修正版切换
- 任务进度实时可视化（下载 / 转写 / 纠错 / 整理 / 保存五阶段）

### 2.2 明确不做的（首版不做）

- 多用户、登录、权限
- 公网部署、域名、HTTPS
- 移动端适配（桌面浏览器足够）
- 除抖音外的其他平台实现（架构上预留接口，不实现）

### 2.3 后续版本规划

- Claude API 后端（用于高质量重整）
- 定时轮询博主更新，增量处理新视频
- 全文搜索 + 向量语义搜索
- 按主题 / 标签聚合视图
- YouTube、B 站、小红书支持
- 文章导出为 PDF / EPUB 合集

---

## 三、技术架构

### 3.1 架构图

```text
前端（React / Vite）
    │  HTTP + SSE
    ▼
FastAPI API（控制层）
    │  读写 / notify
    ▼
Postgres（状态层）
    ├─ creators / videos / transcripts / articles
    ├─ transcript_segments / tasks / task_artifacts / settings
    └─ LISTEN / NOTIFY 事件总线
    ▲
    │  claim / heartbeat / update
Worker（执行层）
    ├─ download
    ├─ transcribe
    ├─ correct
    ├─ organize
    └─ save
    │
    ├─ 转写子进程（隔离 mlx-whisper）
    ├─ Douyin Web API / F2 / 媒体直链
    ├─ OSS（视频/音频归档）
    └─ Ollama（qwen2.5:72b）
```

### 3.2 分层职责

| 层级 | 职责 |
|---|---|
| 前端 | 提交链接、展示任务、阅读文章、修改设置 |
| API 控制层 | 接收请求、建任务、查状态、推送 SSE |
| Worker 执行层 | 按阶段执行下载、转写、纠错、整理、保存 |
| Postgres 状态层 | 业务库 + 持久化任务队列 + 事件总线 |

### 3.3 技术选型

| 层级 | 技术 | 选择理由 |
|---|---|---|
| Web 框架 | FastAPI | API/SSE 简洁，适合控制层 |
| 前端 | React + Vite + TypeScript | 当前项目已实现，状态订阅方便 |
| 任务执行 | 独立 worker 进程 | 将重任务与 API 隔离，避免单点崩溃 |
| 任务队列 | PostgreSQL 持久化队列 + 租约 | 单机可用，实现可控，不额外引入 Redis/Celery |
| 数据库 | PostgreSQL 16 + pg_trgm + pgvector | 当前主库；文本搜索和未来语义搜索都能覆盖 |
| 转写 | mlx-whisper + 子进程隔离 | Apple Silicon 上快，同时能隔离 Metal 崩溃 |
| 纠错与整理 | Ollama + Qwen2.5-72B | 中文质量好，当前实际可用 |
| 实时通信 | SSE + LISTEN/NOTIFY | 比 WebSocket 更简单，跨进程天然兼容 |
| 媒体存储 | 本地临时目录 + OSS | 降低重复下载成本，便于重跑复用 |

### 3.4 设计原则

- API 不直接执行重任务
- worker 分阶段执行，按阶段独立限流
- 任务状态持久化到 Postgres，不依赖内存队列
- 转写崩溃只能影响当前任务，不影响整个服务
- 原始转写永不覆盖，修正版与背景注都是增量资产

---

## 四、数据模型

### 4.1 当前持久化基线

当前后端已经落库并在使用的主表：

- `creators`：博主主数据
- `videos`：视频元信息、封面、媒体 OSS 键
- `articles`：文章正文、摘要、标签
- `transcript_segments`：文章阅读页的分段逐字稿
- `tasks`：持久化任务队列
- `task_artifacts`：阶段中间产物
- `settings`：单行 KV 配置

本次设计在此基础上新增一张真正的 `transcripts` 表，用来承载“原始转写 + 纠错结果”这类长期资产，避免把正式数据混进 `task_artifacts`。

### 4.2 任务表 `tasks`

`tasks` 继续沿用当前真实状态模型，不重新发明一套新的 status。

```sql
CREATE TABLE tasks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_url          TEXT NOT NULL,
    title_guess         TEXT NOT NULL DEFAULT '',
    creator_id          BIGINT REFERENCES creators(id) ON DELETE SET NULL,
    video_id            TEXT,
    article_id          UUID REFERENCES articles(id) ON DELETE SET NULL,
    stage               TEXT NOT NULL DEFAULT 'download'
        CHECK (stage IN ('download', 'transcribe', 'correct', 'organize', 'save')),
    status              TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'done', 'failed', 'canceled')),
    progress            SMALLINT NOT NULL DEFAULT 0,
    eta_sec             INTEGER,
    detail              TEXT,
    error               TEXT,
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    run_after           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lease_owner         TEXT,
    lease_expires_at    TIMESTAMPTZ,
    last_heartbeat_at   TIMESTAMPTZ,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at         TIMESTAMPTZ
);

CREATE INDEX idx_tasks_stage_ready ON tasks (stage, status, run_after);
CREATE INDEX idx_tasks_status ON tasks (status, started_at);
CREATE INDEX idx_tasks_creator ON tasks (creator_id);
```

设计原则：

- `status` 只表达任务生命周期：`queued / running / done / failed / canceled`
- `stage` 表达当前处理阶段，本次只新增 `correct`
- worker 靠 `lease_owner + lease_expires_at + heartbeat` 抢占和续租，不再使用进程内队列
- `attempt_count` 为后续自动重试、退避和失败审计留接口

### 4.3 转写资产表 `transcripts`（新增）

这张表是本次设计新增的关键点，用来承接 `transcribe` 和 `correct` 两个阶段的正式结果。

```sql
CREATE TABLE transcripts (
    video_id              TEXT PRIMARY KEY REFERENCES videos(id) ON DELETE CASCADE,
    raw_text              TEXT NOT NULL,          -- Whisper 原始全文，永不覆盖
    segments              JSONB NOT NULL,         -- [{start, end, text}, ...]
    corrected_text        TEXT,                   -- 纠错后全文；失败时允许为 NULL
    corrections           JSONB,                  -- [{from, to, reason}, ...]
    correction_status     TEXT NOT NULL DEFAULT 'pending'
        CHECK (correction_status IN ('pending', 'ok', 'skipped', 'failed')),
    initial_prompt_used   TEXT,
    whisper_model         TEXT,
    whisper_language      TEXT,
    corrector_model       TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_transcripts_raw_trgm
    ON transcripts USING GIN (raw_text gin_trgm_ops);
CREATE INDEX idx_transcripts_corrected_trgm
    ON transcripts USING GIN (corrected_text gin_trgm_ops);
```

为什么要单独建表：

- `task_artifacts` 适合存“阶段中间态”，不适合承载长期查询和回溯数据
- `raw_text` 和 `corrected_text` 需要长期并存，不能只保留修正后的版本
- 后续重跑文章时应优先复用 `corrected_text`，而不是重新下载视频或重新转写

### 4.4 文章表 `articles` 扩展

`articles` 延续当前真实结构，新增 `background_notes` 字段：

```sql
ALTER TABLE articles
ADD COLUMN background_notes JSONB;
```

推荐结构：

```json
{
  "aliases": [
    {
      "term": "西大",
      "refers_to": "西方大国/美国",
      "confidence": "high"
    }
  ],
  "context": "可选；仅当逐字稿本身能支撑时才输出"
}
```

约束：

- `aliases` 可为空数组
- `context` 可缺省，不强制生成
- `background_notes` 只做附加说明，不替换正文中的原始表述

### 4.5 `task_artifacts` 的职责边界

`task_artifacts` 保留，但定位收窄为“任务阶段之间的中间交换层”：

- `transcript_segments`
- `organized`
- 未来可临时放 `corrected_preview`

它**不再承担正式资产表职责**。正式数据一律落到：

- `transcripts`
- `articles`
- `transcript_segments`

### 4.6 本地与 OSS 媒体布局

媒体资产采用“本地临时目录 + OSS 归档”的双层策略：

```text
/tmp/voxpress/
├── video/     下载中的 mp4 临时文件
└── audio/     转写前后的 m4a 临时文件
```

归档策略：

- `videos.media_object_key`：原始视频 OSS 键
- `videos.audio_object_key`：转写音频 OSS 键
- 重跑任务时优先从 OSS 恢复，尽量不重复请求抖音

### 4.7 Markdown 输出

文章导出的 Markdown 继续采用“两层元信息”：

1. YAML front matter：机器可读
2. 正文前的来源信息条：读者可读

其中：

- 来源信息条只展示真实入库的数据
- 播放量无数据时不渲染
- 背景注固定作为正文末尾附录，不混入正文主体

---

## 五、页面设计

### 5.1 首页 `/`

顶部：单行输入框，支持三种输入自动识别：

- 单条视频链接（`www.douyin.com/video/...`）
- 博主主页链接（`www.douyin.com/user/...`）
- 短链接（`v.douyin.com/...`）

中部：高信息密度任务列表。每行显示：

- 博主头像
- 视频标题
- 当前阶段
- 当前 detail
- 进度
- ETA
- 取消按钮

底部：最近完成文章列表。

### 5.2 博主库 `/library`

列表或紧凑表格，每行显示：

- 博主头像
- 昵称 / Handle
- 粉丝数
- 已抓取视频数
- 已转文章数
- 最近更新时间

点击进入博主详情页。

### 5.3 文章阅读 `/articles/{id}`

左右两栏：

- 左：视频元信息 + 逐字稿对照区
- 右：整理后的 Markdown 文章 + 背景注

逐字稿对照区默认策略：

- 主视图展示 `corrected_text`
- 可切换到 `raw_text`
- 时间戳始终跟随 `segments` 原文，不做字符级硬对齐

右上角操作区：

- 重新整理
- 导出 Markdown
- 标签管理

### 5.4 博主批量提交 `/creators/{id}/import`

流程：

1. 拉取博主视频列表
2. 复选要处理的视频
3. 按时长、时间范围、是否已转文章筛选
4. 点击“开始处理”
5. 返回首页看实时任务队列

### 5.5 设置 `/settings`

- Ollama 模型：下拉（从 Ollama API 自动发现）
- Whisper 模型：`large-v3 / medium / small`
- 转写增强：
  - 启用 `initial_prompt`
  - 转写后自动纠错
- 整理增强：
  - 生成背景注
- Prompt 模板：
  - 文章整理 prompt
  - 转写纠错 prompt
- 抖音 Cookie：
  - 只支持上传 `cookies.txt`
  - 上传后立即测试连接

说明：

- v0.6 不单独暴露“背景注 prompt”，先把配置面保持克制
- 主整理 prompt 不再承担主要 ASR 纠错职责，纠错归独立 `correct` 阶段
- Cookie 不再支持手工粘贴 Header/String，减少格式错误

---

## 六、Pipeline 设计

### 6.1 五阶段流水线

```text
Stage 1: Download   (10%)
  - 优先从本地或 OSS 恢复媒体
  - 若缓存不存在，再走 Douyin Web API / F2 / 媒体直链抓取
  - upsert creator / video 元信息
  - 写入或更新 OSS 归档键

Stage 2: Transcribe (45%)
  - 用视频 metadata 构造 initial_prompt
  - worker 启动独立子进程执行 mlx-whisper
  - 产出 raw_text + segments
  - 写入 transcripts

Stage 3: Correct    (5%)
  - 组装纠错 prompt
  - 长文本分段
  - Ollama 输出 corrected_text + corrections
  - 后验校验
  - 失败降级

Stage 4: Organize   (35%)
  - 优先读取 corrected_text；没有则回退 raw_text
  - 组装 organizer prompt
  - 生成 title / summary / tags / body / background_notes

Stage 5: Save       (5%)
  - upsert articles
  - 重写 transcript_segments
  - 写出 markdown 文件
  - 标记任务 done
```

### 6.2 错误处理

- 每个阶段单独捕获错误，失败时写回 `tasks.error`
- 转写子进程崩溃只会让当前任务失败，不会带死 API 或 worker 主进程
- 纠错阶段失败不阻塞文章生成，直接回退到 `raw_text`
- 自动重试/退避属于下一阶段增强；v0.6 先保留 `attempt_count` 和 `run_after` 作为实现基础

### 6.3 并发控制

```python
MAX_CONCURRENT_DOWNLOADS = 4
MAX_CONCURRENT_TRANSCRIBES = 1
MAX_CONCURRENT_CORRECTS = 2
MAX_CONCURRENT_ORGANIZES = 2
MAX_CONCURRENT_SAVES = 4
```

说明：

- `transcribe=1` 不是因为内存不够，而是因为 `mlx-whisper + Metal` 在并发转写时稳定性不足
- `organize=2` 继续匹配当前 `qwen2.5:72b` 的实测上限
- `download/save` 可以高一些，因为资源争用比转写和 LLM 整理轻
- worker 内部继续按阶段分别限流，而不是使用一个全局总门

### 6.4 平台扩展架构

VoxPress 保持平台无关设计，抽象层建议落在 `voxpress/pipeline/protocols.py` 和后续 extractor 适配器上。

```python
class Platform(ABC):
    name: str

    @abstractmethod
    def match_url(self, url: str) -> URLKind: ...

    @abstractmethod
    async def fetch_creator_info(self, external_id: str) -> CreatorInfo: ...

    @abstractmethod
    async def list_creator_videos(self, external_id: str) -> list[VideoMeta]: ...

    @abstractmethod
    async def fetch_video_detail(self, url: str) -> VideoMeta: ...

    @abstractmethod
    async def download_media(self, video: VideoMeta) -> MediaPaths: ...
```

MVP 只实现抖音一个适配器。未来新增 YouTube/B 站时：

1. 实现新的 platform adapter
2. 在 URL 解析层登记
3. 复用现有 `tasks / worker / transcripts / articles`

### 6.5 转写质量增强

#### 6.5.1 问题背景

基于首版实测（2026-04-20，抖音某博主“舆论战”主题视频），Whisper 在中文口播场景下有两类高频错误：

一、同音字/近音字识别错。真实案例：

| 工具输出 | 正确 | 原因 |
|---|---|---|
| 每一交战 | 美伊交战 | 同音专有名词，"每一"更高频 |
| 化宠为灵 | 化整为零 | 军事成语，训练语料罕见 |
| 勿接必反 | 物极必反 | 成语近音字 |
| 舒服力 | 说服力 | 近音字 |

二、领域特定术语。时事、地缘政治、互联网黑话等——模型缺乏先验知识，只能按音形靠猜。

这类错误如果不在转写后立刻处理，会直接污染整理阶段。主整理模型偶尔能顺手修对，但稳定性不够，不能把“ASR 纠错”继续当成文章整理的副作用。

#### 6.5.2 解法 A：Whisper `initial_prompt`

mlx-whisper 支持 `initial_prompt` 参数作为识别的词汇偏置。做法是把视频元数据拼接作为提示：

```python
def build_initial_prompt(video: Video) -> str:
    parts = [
        video.title or "",
        video.description or "",
        " ".join(video.hashtags or []),
    ]
    text = "。".join(p for p in parts if p)
    return text[:200]
```

效果：

- 视频标题含“美伊”时，正文里所有“每一”更容易识别为“美伊”
- 对专有名词、人名、品牌名命中率明显更高
- 对成语作用有限，因此还需要后续 `correct` 阶段

记录：

- `transcripts.initial_prompt_used` 存本次用到的 prompt

#### 6.5.3 解法 B：独立纠错阶段

职责：只改 ASR 识别错误，不做任何润色/改写。

输入输出：

```text
输入：raw_text + video.title/description/hashtags + creator.name
输出：corrected_text + corrections

corrections = [
  {"from": "每一交战", "to": "美伊交战", "reason": "同音字·专有名词"},
  {"from": "化宠为灵", "to": "化整为零", "reason": "成语识别错"}
]
```

原 `raw_text` 和 `segments` 永不覆盖。`organize` 阶段优先读 `corrected_text`；阅读页默认展示修正版，但允许切回原始稿。

Prompt 设计：

```text
[System]
你是一个中文语音转写的校对员。你的唯一任务是修正自动转写中因同音字/近音字
导致的识别错误，不做任何其他改动。

严格规则：
1. 只改明显的识别错误（成语错字、专有名词、常见搭配）
2. 博主使用的代称/隐语/自造词不要改
3. 口语表达、语气词、重复一律保留
4. 句子结构、断句不要改
5. 若不确定，倾向于不改

输出 JSON：
{
  "corrected": "修正后的全文",
  "changes": [{"from": "原文", "to": "修正", "reason": "同音字/成语/专名"}]
}
```

后验校验：

```python
def validate(original: str, corrected: str, changes: list) -> bool:
    ratio = len(corrected) / len(original)
    if not (0.85 <= ratio <= 1.15):
        raise CorrectionTooAggressive(ratio)

    for c in changes:
        if c["from"] not in original:
            raise InvalidChange(c)
```

#### 6.5.4 Pipeline 权重重新分配

```text
下载  10%
转写  45%
纠错   5%
整理  35%
保存   5%
```

#### 6.5.5 时间戳策略

纠错后的文本不再与原 `segments` 的时间戳严格对齐，不做硬对齐：

- `segments` 保留原样，用于字幕导出和时间定位
- `corrected_text` 用于 organizer 和默认阅读
- 前端双栏展示：左侧原文分段，右侧修正版段落

#### 6.5.6 失败降级

| 失败模式 | 处理 |
|---|---|
| JSON 解析失败 | 重试 2 次 |
| 长度校验失败 | 回退 `corrected_text = NULL`，状态 `failed` |
| Ollama 超时 | 回退同上 |
| 用户关闭纠错开关 | 状态 `skipped` |
| 成功 | 状态 `ok` |

#### 6.5.7 未来增强

- 引入评论区上下文作为纠错辅助
- 维护用户热词表 / 错字表
- 在转写质量极差的视频上尝试切换 ASR 后端

---

## 七、内容整理与背景注设计

### 7.1 接口定义

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class OrganizeResult:
    title: str
    summary: str
    tags: list[str]
    body_md: str
    background_notes: dict | None

class Organizer(ABC):
    @abstractmethod
    async def organize(
        self,
        transcript: str,
        video_title: str,
        creator_name: str,
        style_hint: str = "",
    ) -> OrganizeResult: ...

    @property
    @abstractmethod
    def backend_name(self) -> str: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...
```

说明：

- 当前真实代码里 LLM 调用在 `voxpress/pipeline/ollama.py`
- v0.6 设计文档里统一称这一步为 `organize`，避免继续沿用旧文档的 `polish`
- Claude 仍然可以作为未来可插拔后端，但不是本次功能落地前提

### 7.2 MVP 实现：Ollama Organizer

- 通过 `httpx` 调 `http://localhost:11434/api/chat`
- 默认模型 `qwen2.5:72b`
- 支持长文本切段和结果拼接
- 输出 JSON 结构：
  - `title`
  - `summary`
  - `tags`
  - `body`
  - `background_notes`

### 7.3 Prompt 模板（v0.6）

```text
[System]
你是一个专业的中文口播内容整理编辑。你的任务是把逐字稿整理成可读文章，
保留博主的原始观点和语言风格。

整理原则：
1. 不添加逐字稿里没有的事实或立场
2. 去除口语冗余，但不改变原意
3. 合并重复表达，理顺段落结构
4. 为不同主题段落加二级标题
5. 保留博主的金句和有辨识度的表达
6. 不承担主要 ASR 纠错职责；输入文本默认已由前置 correct 阶段清洗

[User]
视频标题：{video_title}
博主昵称：{creator_name}

逐字稿：
{transcript}

请返回 JSON：
{
  "title": "精炼标题",
  "summary": "100 字以内摘要",
  "tags": ["标签1", "标签2"],
  "body": "markdown 正文",
  "background_notes": {
    "aliases": []
  }
}
```

系统侧负责：

- front matter
- 来源信息条
- 背景注前导说明
- Markdown 文件输出

模型只负责文章正文和结构化背景注结果。

### 7.4 背景注机制

#### 7.4.1 问题背景

许多视频博主出于规避审查或照顾熟悉观众，大量使用代称、隐语、时事暗号。实测案例：

| 博主说法 | 实际所指 |
|---|---|
| 西大 | 西方大国 / 美国 |
| 朗子 | 伊朗（避讳直称） |
| 黄毛 | 特朗普（以发色代称） |
| 名嘴 | 被雇佣的意见领袖 |
| 遥遥领先的海军打法 | 反讽语，指代网军/水军舆论战术 |

整理模型通常会保留这些代称，这对熟悉语境的观众没问题，但对新读者很不友好。

#### 7.4.2 设计原则

一、不替换博主原文。博主刻意隐晦是为了特定目的，强行改成大白话违背原意。

二、加脚注不改主体。背景解释单独放在文章末尾的“## 背景注”小节。

三、只注释有合理把握的内容。模型不确定某个代称的所指时宁可不注。

四、用户可关闭。对本来就直白的内容，生成背景注可关。

#### 7.4.3 Organizer prompt 扩展

```text
若博主明显使用了代称/隐语/典故，请额外输出 background_notes。

要求：
1. 不要把背景注内容混入正文
2. 不要替换博主原话
3. aliases 只列你有合理把握的内容
4. context 只有在标题、描述、逐字稿本身能够支撑时才输出
5. 不能依赖开放式世界知识做大段延展；不确定时省略
```

#### 7.4.4 输出结构

```json
{
  "background_notes": {
    "aliases": [
      {"term": "西大", "refers_to": "西方大国/美国", "confidence": "high"},
      {"term": "黄毛", "refers_to": "特朗普", "confidence": "high"}
    ],
    "context": "可选字段"
  }
}
```

规则：

- `aliases` 可输出高/中/低置信度
- `context` 是可选字段，不强制生成
- 如果模型只有模糊猜测，宁可只输出 `aliases`，不输出 `context`
- 结构化结果会写入 `articles.background_notes`

#### 7.4.5 渲染示例

```markdown
（……文章正文……）

## 背景注

> 以下为编辑根据上下文补充，非博主原话。

**代称说明**
- **西大** = 西方大国，博主对美国/西方阵营的代称
- **黄毛** = 特朗普（以发色代称）
```

如果存在 `context`，则再补一个“事件背景”小节；没有就只渲染代称清单。

---

## 八、进度上报与实时推送

### 8.1 SSE 端点

```text
GET /api/tasks/stream
Content-Type: text/event-stream

event: task.update
data: {
  "id": "3514e5d7-b00f-4ea7-bc58-e468c6d9a43f",
  "stage": "correct",
  "status": "running",
  "progress": 52,
  "detail": "纠错中",
  "article_id": null
}
```

当前前端只订阅一个全局 SSE 流。

### 8.2 广播机制

事件路径：

1. API 创建/更新任务
2. worker 推进阶段、更新进度、任务完成
3. API/worker 都通过 Postgres `NOTIFY` 发事件
4. API 的 SSE 层通过 `LISTEN` 监听并转发给前端

这样 API 和 worker 即使分进程，也能共享同一条事件通道。

### 8.3 阶段进度细化

- `download`：按媒体下载字节数或恢复命中状态上报
- `transcribe`：按音频时长或分段进度上报
- `correct`：按 chunk 数上报；短文本可视为单阶段完成
- `organize`：按长文本切片和合并阶段上报
- `save`：按“写文章 / 写 transcript_segments / 写文件”粗粒度上报

---

## 九、项目结构

```text
/Users/auston/cowork/dy_docs/
├── voxpress/                       React 前端
│   ├── src/pages/                  Home / Library / Import / Article / Settings
│   ├── src/features/tasks/         首页任务队列订阅
│   └── src/lib/api.ts              API 客户端
└── voxpress-api/
    ├── pyproject.toml
    ├── README.md
    ├── ARCHITECTURE.md
    ├── alembic/
    │   └── versions/               数据库迁移
    └── voxpress/
        ├── main.py                 FastAPI 控制层入口
        ├── worker.py               独立 worker
        ├── config.py               环境变量与并发配置
        ├── db.py                   async engine + session
        ├── models.py               ORM 模型
        ├── schemas.py              API schema
        ├── task_store.py           Postgres 队列 / lease / artifact
        ├── sse.py                  LISTEN / NOTIFY 事件层
        ├── creator_sync.py         博主抓取与入库
        ├── creator_refresh.py      定时刷新调度器
        ├── media_store.py          OSS 媒体归档
        ├── markdown.py             文章 markdown 拼接
        ├── jobs/
        │   └── transcribe.py       转写子进程入口
        ├── routers/
        │   ├── resolve.py
        │   ├── tasks.py
        │   ├── creators.py
        │   ├── videos.py
        │   ├── articles.py
        │   ├── settings.py
        │   └── media.py
        └── pipeline/
            ├── runner.py           领域服务：媒体恢复 / upsert / 保存
            ├── douyin_scraper.py   博主页抓取
            ├── douyin_video.py     单视频详情与媒体下载
            ├── mlx.py              Whisper 封装
            ├── ollama.py           Organizer 实现
            ├── protocols.py        抽象协议
            ├── ytdlp.py            辅助/兼容实现
            └── corrector.py        计划新增：转写纠错
```

---

## 十、实施计划

当前仓库已经有：

- API 控制层
- worker 执行层
- Postgres 持久化任务队列
- LISTEN / NOTIFY SSE
- 真实抖音抓取、媒体下载、Whisper 转写、Ollama 整理

所以接下来的计划是**在现有系统上增量改造**，不是重新搭骨架。

### Phase A：Schema 与配置对齐（~1.5 小时）

- 新增 `transcripts` 表迁移
- 给 `articles` 增加 `background_notes`
- `tasks.stage` 的 check constraint 扩成五段
- `schemas.py` / `settings.py` 增加：
  - `enable_initial_prompt`
  - `auto_correct`
  - `generate_background_notes`
  - `corrector prompt`

验收：

- `alembic upgrade head` 通过
- `/api/settings` 可读写新字段
- 老任务、老文章不受影响

### Phase B：转写增强接入（~1.5 小时）

- `transcribe` 阶段接入 `initial_prompt`
- 把转写结果正式落到 `transcripts.raw_text / segments`
- `task_artifacts` 只保留阶段交换所需的最小中间态

验收：

- 新任务完成后，数据库里能同时看到 `raw_text`、`segments`、`initial_prompt_used`
- 标题中专有词对转写有明显提升

### Phase C：新增 `correct` 阶段（~2.5 小时）

- 新建 `pipeline/corrector.py`
- worker 阶段链从四段扩到五段
- `correct` 阶段写入：
  - `corrected_text`
  - `corrections`
  - `correction_status`
- 长文本分块与失败降级

验收：

- 用实测“舆论战”视频重跑
- 检查 `"每一交战" → "美伊交战"`、`"化宠为灵" → "化整为零"`、`"勿接必反" → "物极必反"` 是否修正
- 构造异常 JSON 响应时能自动降级而不阻塞整条任务

### Phase D：Organizer 接背景注（~2 小时）

- 主整理 prompt 改成不再承担主要 ASR 纠错
- 增加 `background_notes` 输出
- 系统侧把背景注渲染成文章末尾固定小节
- 只在高把握场景下输出 `context`

验收：

- 文章能正常生成 `title / summary / tags / body`
- 代称视频能产出 `aliases`
- 无明确支撑时 `context` 为空或缺省

### Phase E：前端设置页与文章页（~2 小时）

- 设置页新增三个开关
- 增加 organizer / corrector 两个 prompt 编辑入口
- 文章页逐字稿支持原稿/修正版切换
- 背景注在文章末尾可视化渲染

验收：

- 设置修改后能影响新任务
- 阅读页能分清原始稿、修正版、背景注

### Phase F：回填与验证（~1.5 小时）

- 历史文章逐条补齐 `transcripts`
- 对已有任务链路做一轮真实回归
- 补最小集成测试：
  - 新阶段推进
  - rebuild 不重复插入
  - 纠错失败回退
  - 背景注渲染

验收：

- 至少 2 条真实视频端到端通过
- 历史文章页面不因新字段缺失而报错

### 总预估

**增量开发约 11 小时。**

比旧文档里的 `19.5 小时` 明显下降，原因不是功能变少，而是：

- API / worker 骨架已存在
- Postgres 队列已存在
- 真实媒体链路已跑通
- 当前只是在成熟骨架上补一个阶段和一组新字段

---

## 十一、风险与注意事项

### 11.1 抖音反爬

- 单条视频详情和媒体直链都依赖真实登录态，Cookie 失效会直接影响下载
- 博主主页遍历和媒体获取必须限制速率，避免触发风控
- 当前主路径已经从单纯依赖 `yt-dlp` 转为 `Douyin Web API / F2 / 媒体直链`
- 设置页“测试连接”必须验证到视频下载链路，而不只是主页抓取

### 11.2 版权

工具定位为“个人知识管理”，所有文章都附带原视频链接。如果以后支持导出和分享，需要在页面加提示。

### 11.3 磁盘与 OSS 占用

- 本地只保留短期临时文件，长期资产优先归档到 OSS
- 一条 10 分钟视频的 `mp4 + m4a` 体积远大于纯文本，必须设置保留策略
- 逐字稿和文章体积小，但数量大后仍建议做归档和备份

### 11.4 LLM 成本与模型

- 本地 Ollama：零现金成本，但 Qwen2.5-72B 首次下载约 40GB
- 若 72B 单篇整理速度不够快，可切到 `qwen2.5:32b` 或 `qwen2.5:14b`
- 若将来接入 Claude，可只让“重要重跑”走远端模型，而不是所有文章默认走云端

### 11.5 mlx-whisper 与 Metal

- 需要 macOS 13.3+ 和 Apple Silicon
- 首次运行自动下载模型（large-v3 约 3GB）
- 并发转写存在 Metal 稳定性风险，因此设计上固定 `transcribe=1`
- 若后续仍有稳定性问题，可评估 `faster-whisper` / `SenseVoice` / `FunASR`

### 11.6 PostgreSQL 服务

- PostgreSQL 是长驻后台服务，通过 `brew services start postgresql@16` 启动
- 默认监听 `127.0.0.1:5432`，不对外暴露
- 除业务库外，它还承担任务队列和事件总线职责，可靠性比旧版更关键
- 升级主版本前要先做备份与迁移计划

### 11.7 统计数据时效性

- 点赞、评论、粉丝这些数据是抓取时刻的快照，不是实时
- 设计上用抓取时间标注时效性
- 提供“刷新博主数据”能力，手动或定时更新

### 11.8 背景注的事实风险

- 背景注不是事实数据库，不能把模型猜测写成确定事实
- `context` 只在逐字稿和视频上下文本身足够支撑时输出
- 对低置信度别名要显式提示或直接省略

---

## 十二、验收标准（MVP 通过的最低门槛）

1. ✅ 浏览器打开 `http://127.0.0.1:5173`，输入一条抖音视频链接，最终能得到一篇文章
2. ✅ API 与 worker 分进程运行，重任务不在 API 进程里直接执行
3. ✅ 使用本地 Ollama 完成文章整理，设置页可切换已安装模型
4. ✅ 转写后有独立 `correct` 阶段，纠错失败时能安全降级
5. ✅ 能提交博主主页，选择视频批量处理
6. ✅ 有博主库视图，能按博主查看文章和视频
7. ✅ 文章阅读页能并排看逐字稿与整理文章
8. ✅ 所有长任务通过 `/api/tasks/stream` 实时推送，不需要刷新页面
9. ✅ 生成的 Markdown 自带完整来源信息条和结构化元数据
10. ✅ 背景注只做附加说明，不改正文原意

---

## 附录 A：依赖清单

```toml
[project]
name = "voxpress"
version = "0.1.0"
description = "Turn spoken video content into structured articles. MVP: Douyin."
requires-python = ">=3.12"

dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "python-multipart>=0.0.12",
    "sse-starlette>=2.1",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.30",
    "pgvector>=0.3.6",
    "alembic>=1.13",
    "mlx-whisper>=0.4",
    "httpx>=0.28",
    "pydantic-settings>=2.6",
    "python-dotenv>=1.0",
]
```

## 附录 B：启动命令

```bash
# ---- 一次性环境准备 ----
brew install postgresql@16 pgvector ffmpeg ollama
brew services start postgresql@16
brew services start ollama
createdb voxpress
psql voxpress -c 'CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;'
ollama pull qwen2.5:72b

# ---- 后端 ----
cd /Users/auston/cowork/dy_docs/voxpress-api
uv sync
uv run alembic upgrade head

# 终端 1：API
uv run uvicorn voxpress.main:app --host 127.0.0.1 --port 8787 --workers 1

# 终端 2：worker
uv run python -m voxpress.worker

# ---- 前端 ----
cd /Users/auston/cowork/dy_docs/voxpress
npm install
npm run dev

# 浏览器打开
open http://127.0.0.1:5173
```

## 附录 C：数据库维护命令

```bash
# 备份整个数据库
pg_dump voxpress > backup_$(date +%Y%m%d).sql

# 恢复数据库
psql voxpress < backup_20260420.sql

# 查看任务状态统计
psql voxpress -c "SELECT status, count(*) FROM tasks GROUP BY 1;"
```
