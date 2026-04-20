# VoxPress · 设计文档

> **项目**：VoxPress —— 把视频口播内容变成可读文章的个人工具
> **名字来源**：Vox（拉丁语"声音"）+ Press（印刷/出版）
> **版本**：v0.4（设计阶段）
> **日期**：2026-04-20
> **目标平台**：macOS（M5 Max / 128GB）本地运行
> **MVP 对接平台**：抖音；架构上多平台可扩展
>
> **v0.2 更新**：扩展博主/视频元数据字段；数据库改用 PostgreSQL 16 + pgvector。
> **v0.3 更新**：MVP 只集成 Ollama，ClaudePolisher 推迟到后续版本（抽象接口保留，便于后接）。
> **v0.4 更新**：项目正式命名为 VoxPress。目录结构、包名、数据库名、启动命令全部同步。

---

## 一、项目概述

**VoxPress** 把视频博主的口播内容自动转写成结构化的文章库。MVP 对接抖音，架构上为多平台预留扩展点（YouTube / B 站 / 小红书 / 播客等），首版单机运行、个人使用。

名字寓意："vox"（声音）经由"press"（印刷）成为文字。每一条视频都是一次从声波到铅字的转化。

### 1.1 核心使用场景

- 关注的博主持续更新，想沉淀成可搜索、可回顾的文字资料
- 把对谈类、干货类视频转成文章，方便二次消化或引用
- 建立个人知识库，为后续语义搜索 / 主题聚类打基础

### 1.2 核心价值

把"被动刷视频"转为"主动读文章"。视频是线性媒介，文章是随机访问媒介——转换之后可检索、可标注、可引用、可分享。

---

## 二、功能范围

### 2.1 MVP 功能（首版交付）

- 提交单条抖音视频链接 → 输出一篇 markdown 文章
- 提交抖音博主主页链接 → 拉取视频列表 → 用户选择要处理的视频 → 批量生成文章
- **每篇文章自带完整溯源信息**：博主（抖音号、昵称、粉丝数、认证等）+ 视频（标题、发布时间、点赞/评论/转发/收藏/播放量、封面、原链接）
- 文章整理使用本地 Ollama（Qwen2.5-72B 或其他已安装模型），抽象接口预留给后续接入 Claude API
- 博主库视图：按博主分组展示已生成的文章，显示博主粉丝、获赞等聚合数据
- 文章阅读页：并排显示逐字稿原文和整理后的文章
- 任务进度实时可视化（下载 / 转写 / 整理 / 归档四阶段）

### 2.2 明确不做的（首版不做）

- 多用户、登录、权限
- 公网部署、域名、HTTPS
- 移动端适配（桌面浏览器足够）
- 自动定时抓取（后续版本加）
- 除抖音外的其他平台（架构上预留接口，不实现）

### 2.3 后续版本规划

- **Claude API 后端**（ClaudePolisher）：用于高质量文章整理，与 Ollama 并列可切换
- 定时轮询博主更新，增量处理新视频
- 全文搜索 + 向量语义搜索
- 按主题 / 标签聚合视图
- YouTube、B 站、小红书支持（多 extractor）
- 文章导出为 PDF / EPUB 合集

---

## 三、技术架构

### 3.1 架构图

```
┌──────────────────────────────────────────────────┐
│   前端（浏览器）                                   │
│   HTML + Tailwind(CDN) + Alpine.js                │
│   · 任务提交  · 实时进度  · 博主库  · 文章阅读    │
└────────────────┬─────────────────────────────────┘
                 │ HTTP + Server-Sent Events
┌────────────────▼─────────────────────────────────┐
│   FastAPI 后端                                    │
│   · REST API   · SSE 进度推送                     │
│   · 任务队列（BackgroundTasks + 内存队列）         │
└────────────────┬─────────────────────────────────┘
                 │
┌────────────────▼─────────────────────────────────┐
│   Pipeline Orchestrator                           │
│                                                   │
│   ┌─────────┐   ┌─────────┐   ┌──────────┐       │
│   │Download │──▶│Transcribe│──▶│ Polish  │       │
│   │yt-dlp   │   │mlx-whisper│   │LLM(可切换)│     │
│   └─────────┘   └─────────┘   └──────────┘       │
│        │             │              │             │
│        ▼             ▼              ▼             │
│   ┌───────────────────────────────────────┐       │
│   │ PostgreSQL 16 + pgvector + pg_trgm    │       │
│   │ （元数据 / 向量 / 全文搜索）           │       │
│   │    +  文件系统（音频 / 逐字稿 / md）   │       │
│   └───────────────────────────────────────┘       │
└──────────────────────────────────────────────────┘
```

### 3.2 技术选型

| 层级 | 技术 | 选择理由 |
|---|---|---|
| Web 框架 | FastAPI | async 原生支持长任务；自动生成 OpenAPI；生态成熟 |
| 前端 | HTML + Alpine.js + Tailwind CDN | 无构建步骤，改起来快，适合个人工具 |
| 任务队列 | FastAPI BackgroundTasks + asyncio.Queue | 单机场景够用，避免引入 Celery/Redis |
| 数据库 | PostgreSQL 16 + pgvector + pg_trgm | 中文 FTS + 向量搜索生态最成熟；brew 一键安装 |
| ORM | SQLAlchemy 2.0（async）+ asyncpg | 异步原生支持；配 Alembic 做迁移 |
| 视频下载 | yt-dlp | 抖音支持稳定，可通过 cookie 绕过反爬 |
| 语音转写 | mlx-whisper | Apple Silicon 原生优化，M5 Max 上比 PyTorch 快 2-3 倍 |
| LLM（本地） | Ollama + Qwen2.5-72B | 中文效果好，128GB 内存轻松跑；MVP 唯一后端 |
| 实时通信 | Server-Sent Events | 比 WebSocket 简单，单向推送足够 |

---

## 四、数据模型

### 4.1 PostgreSQL 表结构

```sql
-- 启用扩展
CREATE EXTENSION IF NOT EXISTS vector;        -- pgvector：向量搜索
CREATE EXTENSION IF NOT EXISTS pg_trgm;       -- 三元组模糊匹配（中文 FTS 辅助）
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 博主（平台无关）
CREATE TABLE creator (
    id                  BIGSERIAL PRIMARY KEY,
    platform            TEXT NOT NULL,           -- 'douyin' / 'youtube' / 'bilibili' / ...
    platform_user_id    TEXT NOT NULL,           -- 平台内部 ID（如抖音 sec_uid、YouTube channel_id）
    platform_handle     TEXT,                    -- 用户自定义 ID（如抖音号 @xxx、YouTube @handle）
    nickname            TEXT NOT NULL,
    avatar_url          TEXT,
    bio                 TEXT,                    -- 个人简介 / 签名
    -- 统计数据
    follower_count      BIGINT,                  -- 粉丝量 / 订阅数
    following_count     BIGINT,                  -- 关注数
    total_likes         BIGINT,                  -- 获赞总数（部分平台无）
    video_count         INTEGER,                 -- 作品数
    -- 认证与属地
    verified            BOOLEAN DEFAULT FALSE,
    verify_info         TEXT,                    -- 认证类型（抖音蓝V、YouTube 官方验证等）
    region              TEXT,                    -- IP 属地 / 所在地（部分平台无）
    -- 其他
    extra               JSONB,                   -- 原始元数据备份（平台特有字段都塞这里）
    stats_fetched_at    TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (platform, platform_user_id)
);
CREATE INDEX creator_nickname_trgm ON creator USING GIN (nickname gin_trgm_ops);
CREATE INDEX creator_handle ON creator (platform, platform_handle);

-- 视频（平台无关）
CREATE TABLE video (
    id                  BIGSERIAL PRIMARY KEY,
    creator_id          BIGINT NOT NULL REFERENCES creator(id) ON DELETE CASCADE,
    platform            TEXT NOT NULL,
    platform_video_id   TEXT NOT NULL,           -- 抖音 aweme_id、YouTube video_id 等
    title               TEXT,                    -- 视频标题 / 文案
    description         TEXT,                    -- 完整描述（若与 title 不同）
    duration_sec        INTEGER,
    published_at        TIMESTAMPTZ,             -- 发布时间
    cover_url           TEXT,                    -- 封面图 / 缩略图
    webpage_url         TEXT,                    -- 原视频网页链接
    video_url           TEXT,                    -- 视频源文件 URL
    -- 互动数据
    like_count          BIGINT,                  -- 点赞量
    comment_count       BIGINT,                  -- 评论量
    share_count         BIGINT,                  -- 转发量
    collect_count       BIGINT,                  -- 收藏量
    view_count          BIGINT,                  -- 播放量（若可用）
    -- 其他
    hashtags            JSONB,                   -- ["#话题1", "#话题2"]
    music_title         TEXT,                    -- 背景音乐名
    music_author        TEXT,
    extra               JSONB,                   -- 原始元数据备份
    stats_fetched_at    TIMESTAMPTZ,
    discovered_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (platform, platform_video_id)
);
CREATE INDEX video_creator_time ON video (creator_id, published_at DESC);
CREATE INDEX video_title_trgm ON video USING GIN (title gin_trgm_ops);
CREATE INDEX video_platform_time ON video (platform, published_at DESC);

-- 处理任务
CREATE TABLE task (
    id                  BIGSERIAL PRIMARY KEY,
    video_id            BIGINT NOT NULL REFERENCES video(id) ON DELETE CASCADE,
    status              TEXT NOT NULL,
        -- pending / downloading / transcribing / polishing / done / failed
    progress            REAL DEFAULT 0,          -- 0.0 ~ 1.0
    stage_timings       JSONB,                   -- {"download": 3.2, "transcribe": 45.8, ...}
    error_message       TEXT,
    llm_backend         TEXT,                    -- ollama / claude
    llm_model           TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);
CREATE INDEX task_status_active ON task (status)
    WHERE status IN ('pending', 'downloading', 'transcribing', 'polishing');

-- 逐字稿
CREATE TABLE transcript (
    video_id            BIGINT PRIMARY KEY REFERENCES video(id) ON DELETE CASCADE,
    raw_text            TEXT NOT NULL,
    segments            JSONB,                   -- [{start, end, text}, ...]
    language            TEXT DEFAULT 'zh',
    whisper_model       TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX transcript_text_trgm ON transcript USING GIN (raw_text gin_trgm_ops);

-- 文章
CREATE TABLE article (
    id                  BIGSERIAL PRIMARY KEY,
    video_id            BIGINT NOT NULL REFERENCES video(id) ON DELETE CASCADE,
    title               TEXT NOT NULL,
    body_md             TEXT NOT NULL,           -- 完整 markdown（含 front matter）
    summary             TEXT,
    tags                JSONB,                   -- ["标签1", "标签2"]
    llm_backend         TEXT,
    llm_model           TEXT,
    prompt_version      TEXT,
    file_path           TEXT,                    -- 导出的 .md 文件路径
    -- 语义搜索向量（未来功能，允许 NULL）
    title_embedding     VECTOR(1024),
    body_embedding      VECTOR(1024),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX article_body_trgm ON article USING GIN (body_md gin_trgm_ops);
-- HNSW 向量索引（待有 embedding 后启用）
-- CREATE INDEX article_title_hnsw ON article USING hnsw (title_embedding vector_cosine_ops);
-- CREATE INDEX article_body_hnsw  ON article USING hnsw (body_embedding  vector_cosine_ops);
```

**为什么这样设计**：

- **平台无关设计**：`platform` + `platform_user_id` / `platform_video_id` 的组合替代专属字段（不再出现 `douyin_sec_uid` 这类绑死命名）。MVP 插入时 `platform='douyin'`，未来加 YouTube 只要新增 `platform='youtube'` 即可，schema 不动。
- `extra` JSONB 存 yt-dlp 返回的完整原始数据，每个平台特有的字段（比如抖音的 `music_title`、YouTube 的 `category_id`）都能塞进去，查询时按需取
- `stats_fetched_at` 分别记录博主和视频的统计数据抓取时间，便于做"数据陈旧"判断（比如粉丝量超过 7 天没更新就后台刷新）
- `pg_trgm` 索引让"模糊搜视频标题/逐字稿"变得很快，中文场景特别有用
- 向量字段现在允许 NULL，未来补 embedding 时再跑索引，MVP 阶段不必实现

### 4.2 文件系统布局

```
data/
├── audio/
│   └── {aweme_id}.mp3                             原始音频（可定期清理）
├── transcripts/
│   └── {aweme_id}.json                            带时间戳的分段逐字稿
└── articles/
    └── {creator_nickname}/
        └── {date}-{title}.md                       最终文章（便于直接阅读）
```

文章同时写入数据库和文件系统：**数据库用于查询和检索，文件系统用于直接阅读和备份**。
PostgreSQL 数据库本身在 `/opt/homebrew/var/postgresql@16/`（Homebrew 默认路径），可用 `pg_dump` 备份。

### 4.3 文章 Markdown 输出格式

每篇生成的 `.md` 文件都自包含完整溯源信息，由两部分组成：

**(1) YAML Front Matter —— 机器可读的元数据**

```yaml
---
title: "被 AI 取代的第一批人……"
summary: "100 字以内的摘要"
tags: [AI, 职场, 观察]

source:
  platform: douyin
  video_url: https://www.douyin.com/video/7xxxxxxxx
  platform_video_id: "7xxxxxxxx"
  published_at: 2026-04-15T19:23:00+08:00
  duration_sec: 512
  cover_url: https://p3-sign.douyinpic.com/...

creator:
  platform: douyin
  platform_user_id: "MS4wLjABAAAA..."
  platform_handle: "@xxxxx"
  nickname: "某博主"
  avatar_url: https://p3-pc.douyinpic.com/...
  follower_count: 1254000
  verified: true
  verify_info: "财经领域创作者"
  region: "北京"

stats:
  like_count: 45200
  comment_count: 3211
  share_count: 1520
  collect_count: 8934
  view_count: 892000
  fetched_at: 2026-04-20T14:30:00+08:00

hashtags: ["#AI", "#职场", "#科技观察"]
music: "原创音乐 - 某博主"

generated:
  whisper_model: large-v3
  llm_backend: claude
  llm_model: claude-sonnet-4-6
  prompt_version: v1.0
  generated_at: 2026-04-20T14:32:11+08:00
---
```

**(2) 视频信息卡片 —— 渲染时可见的溯源区块**

```markdown
![封面](https://p3-sign.douyinpic.com/...)

> **来源视频** · [在抖音打开原视频 ↗](https://www.douyin.com/video/7xxxxxxxx)
>
> **作者**：某博主（@xxxxx）· 125.4w 粉丝 · 蓝V 认证
> **发布**：2026-04-15 19:23 · 时长 8:32 · IP 属地：北京
> **数据**：❤️ 点赞 4.52w · 💬 评论 3,211 · 🔁 转发 1,520 · ⭐ 收藏 8,934 · ▶️ 播放 89.2w
> **话题**：#AI #职场 #科技观察

---

# {文章正文从这里开始}

## 小节一

...

## 小节二

...
```

这样设计的好处：

- **自包含**：把单个 `.md` 文件拿到任何地方打开，都能看到完整的视频溯源信息
- **机器可读**：YAML front matter 可被 Obsidian、Dataview、静态博客工具直接解析
- **人类友好**：渲染出来的卡片简洁清晰，一眼看到关键数据
- **数据可回溯**：`stats_fetched_at` 标明了数据的时效性，避免读者误以为是实时数据

---

## 五、页面设计

### 5.1 首页 `/`

**顶部**：提交框，单行输入，占满宽度。支持三种输入自动识别：
- 单条视频链接（`www.douyin.com/video/...`）
- 博主主页链接（`www.douyin.com/user/...`）
- 短链接（`v.douyin.com/...`，自动跟随重定向）

**中部**：运行中任务列表。每行显示博主头像、视频标题缩略、进度条、当前阶段、预计剩余时间。点击展开看详细日志。

**底部**：最近完成的 10 篇文章卡片。

### 5.2 博主库 `/creators`

卡片网格，每张卡片：博主头像、昵称、已处理文章数、最近更新时间。点击进入博主详情页（该博主所有视频列表 + 文章列表）。

### 5.3 文章阅读 `/articles/{id}`

左右两栏（可拖拽调整宽度）：
- 左：视频元信息（封面、标题、发布时间、时长、原视频链接）+ 原始逐字稿（折叠，可展开）
- 右：整理后的 markdown 文章，支持目录导航

右上角操作区：
- "重新整理"按钮：弹出 prompt 编辑框，可换模型/换 prompt 再跑一次
- "导出 markdown"
- "标签管理"

### 5.4 博主批量提交 `/creators/{id}/import`

提交博主主页链接后跳转到这里：
1. 第一步：显示"正在拉取视频列表…"
2. 第二步：列出所有视频，默认按时间倒序，复选框全选/反选，支持按时长、时间范围筛选
3. 第三步：用户确认后点"开始处理"，跳转回首页看进度

### 5.5 设置 `/settings`

- **Ollama 模型**：下拉（从 Ollama API `/api/tags` 自动发现已安装的模型），显示 Ollama 服务健康状态
- **Whisper 模型**：large-v3 / medium / small，展示各自速度预估
- **Prompt 模板**：文本框，修改文章整理的 prompt
- **抖音 Cookie**：文件上传或粘贴 Netscape 格式文本，测试连接按钮

> UI 上预留"LLM 后端"下拉框的位置，但 MVP 阶段只有 Ollama 一个选项。后续加入 Claude 时在这里扩展。

---

## 六、Pipeline 设计

### 6.1 四阶段流水线

```
Stage 1: Download        (权重 10%)
  ├─ yt-dlp 下载音频（--extract-audio --audio-format mp3）
  ├─ 从 info.json 提取视频元数据：
  │    title / description / duration / published_at / cover_url
  │    like_count / comment_count / share_count / collect_count / view_count
  │    hashtags / music_title / music_author
  ├─ 顺带拉取博主统计数据（follower_count / total_likes / video_count 等）
  │    若首次见到该博主 → 建 creator 记录
  │    若已存在但 stats_fetched_at 超过 7 天 → 刷新
  └─ 入库 video 表（包含所有互动数据），关联 creator_id

Stage 2: Transcribe      (权重 50%)
  ├─ mlx-whisper 转写
  ├─ 模型默认 large-v3，语言强制中文
  ├─ 输出带时间戳的分段 JSON
  └─ 入库 transcript 表

Stage 3: Polish          (权重 35%)
  ├─ 组装 prompt：system + 风格样本（可选）+ 逐字稿
  ├─ 长文本分段（>4000 字时按段落切）
  ├─ 调用 Polisher.polish() 抽象接口
  ├─ 生成：标题、正文、摘要、标签
  └─ 入库 article 表 + 写 .md 文件

Stage 4: Archive         (权重 5%)
  ├─ 音频文件可选保留或删除
  ├─ 更新 task 状态为 done
  └─ 记录各阶段耗时
```

### 6.2 错误处理

- 每阶段单独 try/except，失败时把错误信息写入 `task.error_message`，状态设为 `failed`
- 下载阶段失败自动重试 3 次，每次间隔递增（5s/15s/60s）
- 转写失败通常是模型未下载，给出明确错误提示 + 下载命令
- LLM 失败支持"重试"按钮，不需要从头跑

### 6.3 并发控制

```python
# 全局限制
MAX_CONCURRENT_DOWNLOADS = 3     # 避免触发抖音风控
MAX_CONCURRENT_TRANSCRIBES = 2   # GPU 内存限制（虽然 128GB 够用，但单次转写已很快）
MAX_CONCURRENT_POLISHES = 5      # LLM 调用并发
```

使用 `asyncio.Semaphore` 实现。

### 6.4 平台扩展架构

VoxPress 从第一天起就按"平台无关"设计，MVP 只实现抖音一个适配器。`app/platforms/` 模块定义统一接口：

```python
class Platform(ABC):
    name: str                                 # 'douyin' / 'youtube' / ...

    @abstractmethod
    def match_url(self, url: str) -> URLKind: ...
        # 返回 video / creator / short_link / unknown

    @abstractmethod
    async def resolve_short_link(self, url: str) -> str: ...

    @abstractmethod
    async def fetch_creator_info(self, user_id: str) -> CreatorInfo: ...
        # 拉博主的粉丝量、认证等统计数据

    @abstractmethod
    async def list_creator_videos(
        self,
        user_id: str,
        cookie: str | None = None,
    ) -> list[VideoMeta]: ...

    @abstractmethod
    def get_ytdlp_opts(self, cookie: str | None = None) -> dict: ...
        # 平台特定的 yt-dlp 参数（user-agent、cookie、extractor 参数等）
```

**MVP 只提供 `DouyinPlatform` 一个实现**。将来加 YouTube 只需要：
1. 写一个 `YouTubePlatform` 类实现上述接口
2. 在平台注册表里登记
3. 前端平台过滤器加一项

数据库 schema、pipeline 编排、文章模板全部不需要改。

---

## 七、LLM 抽象层设计

### 7.1 接口定义

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class PolishResult:
    title: str
    body_md: str
    summary: str
    tags: list[str]

class Polisher(ABC):
    """把逐字稿整理成文章的抽象接口"""

    @abstractmethod
    async def polish(
        self,
        transcript: str,
        video_title: str,
        style_hint: str = "",
    ) -> PolishResult: ...

    @property
    @abstractmethod
    def backend_name(self) -> str: ...  # "ollama" / "claude"

    @property
    @abstractmethod
    def model_name(self) -> str: ...
```

### 7.2 MVP 实现：OllamaPolisher

- 通过 `httpx` 调 `http://localhost:11434/api/chat`
- 默认模型 `qwen2.5:72b`，可在设置页切换到其他已安装的模型
- 支持流式返回（可选，用于前端实时显示生成中的文本）
- 长文本自动分段（>4000 字按段落切），最后拼接并让模型做首尾衔接
- 输出约定 JSON 结构（title / summary / tags / body），失败时重试 2 次，仍失败则标记任务失败

### 7.2.1 未来实现：ClaudePolisher（v0.3 暂不实现）

抽象接口 `Polisher` 保留，未来按下面方式接入：
- 调用 Anthropic API（`claude-sonnet-4-6` 或 `claude-opus-4-6`）
- 使用 system + user 消息分层，工具调用约束 JSON 输出
- 长文本复用同一分段策略
- 设置页增加 API key 输入、模型下拉
- 任务级别可指定后端（默认走 Ollama，重要文章单独指定 Claude）

### 7.3 Prompt 模板（v1）

```
[System]
你是一个专业的口播内容整理编辑。你的任务是把视频的逐字稿整理成一篇
可读性强的文章，保留博主的原始观点和语言风格。

整理原则：
1. 不添加原文没有的观点或事实
2. 去除"这个"、"那个"、"就是说"等口语冗余
3. 合并重复表达，理清逻辑
4. 为不同主题段落加上小标题（## 二级标题）
5. 保留博主的金句和独特表达
6. 输出纯正文 markdown，不要包含任何 front matter（front matter 由系统自动生成）

[User]
视频标题：{video_title}
博主昵称：{creator_nickname}

逐字稿：
{transcript}

请完成三件事，用 JSON 结构返回：
{
  "title":   "精炼的文章标题（可与视频标题不同，不超过 30 字）",
  "summary": "100 字以内的摘要",
  "tags":    ["标签1", "标签2", "标签3"],
  "body":    "markdown 正文（不含 front matter，不含视频信息卡片）"
}
```

**为什么让 LLM 只输出正文**：视频信息卡片和 YAML front matter 包含大量结构化数据（粉丝量、点赞量等），由系统代码拼接比让模型生成更可靠——模型可能幻觉出错误数字，而我们有原始数据。模型只负责写文章本身。

---

## 八、进度上报与实时推送

### 8.1 SSE 端点

```
GET /api/tasks/{task_id}/stream
Content-Type: text/event-stream

event: progress
data: {"stage": "transcribe", "progress": 0.45, "message": "转写中 45%"}

event: complete
data: {"article_id": 123}

event: error
data: {"message": "下载失败：需要 cookie"}
```

### 8.2 全局进度广播

```
GET /api/tasks/stream       所有任务的进度更新（首页用）
```

后端用 `asyncio.Queue` 广播事件，每个 SSE 连接订阅一份。

### 8.3 阶段进度的细化

- **下载**：yt-dlp 的 progress hook，按字节数上报
- **转写**：mlx-whisper 按音频秒数回调（每 30s 音频上报一次）
- **整理**：按分段进度上报（分 3 段则 33% / 66% / 100%）

---

## 九、项目结构

```
voxpress/
├── pyproject.toml
├── config.yaml                     用户可编辑的配置
├── .env.example                    Claude API key 等敏感配置
├── README.md
├── app/
│   ├── __init__.py
│   ├── main.py                     FastAPI 入口 + 路由挂载
│   ├── config.py                   配置加载
│   ├── api/
│   │   ├── tasks.py                POST /api/tasks, GET /api/tasks/{id}/stream
│   │   ├── creators.py             CRUD + 批量导入
│   │   ├── articles.py             文章读写、重新整理
│   │   └── settings.py             LLM / prompt / cookie
│   ├── platforms/                  平台适配层（多平台扩展点）
│   │   ├── base.py                 Platform 抽象（URL 识别、cookie、列表拉取）
│   │   └── douyin.py               MVP 唯一实现
│   ├── pipeline/
│   │   ├── downloader.py           yt-dlp 封装 + 平台适配调度
│   │   ├── transcriber.py          mlx-whisper 封装
│   │   ├── polisher_base.py        抽象接口（未来接 Claude 用）
│   │   ├── polisher_ollama.py      MVP 唯一实现
│   │   └── orchestrator.py         四段式串联
│   ├── db/
│   │   ├── models.py               SQLAlchemy ORM
│   │   ├── session.py              async session（asyncpg）
│   │   └── alembic/                Alembic 迁移脚本
│   ├── events/
│   │   └── broker.py               asyncio 事件广播
│   └── web/
│       ├── templates/
│       │   ├── base.html
│       │   ├── index.html
│       │   ├── creator.html
│       │   ├── article.html
│       │   └── settings.html
│       └── static/
│           ├── app.css
│           └── app.js
├── data/                           运行时生成（不含数据库）
│   ├── audio/
│   ├── transcripts/
│   └── articles/
└── scripts/
    ├── dev.sh                      uvicorn --reload
    ├── setup_db.sh                 建库 + 启用扩展 + 跑 Alembic 迁移
    └── test_pipeline.py            命令行跑通 pipeline（开发期用）
```

---

## 十、实施计划

### Phase 1：骨架（~3 小时）
- 项目初始化：`pyproject.toml`、目录结构、依赖安装
- PostgreSQL 安装 + 建库 + 启用 pgvector/pg_trgm 扩展（`scripts/setup_db.sh`）
- Alembic 初始化 + 第一版迁移（创建全部表和索引）
- FastAPI 启动，首页返回 "Hello"
- ORM 跑通基本 CRUD（创建一条 creator 测试）
- **验收**：浏览器打开 `localhost:8000` 看到首页；`psql` 连上能看到全部表

### Phase 2：命令行打通 pipeline（~3.5 小时）
- `platforms/base.py` 定义 Platform 抽象
- `platforms/douyin.py` 实现（URL 匹配、短链接解析、博主信息抓取、yt-dlp 参数）
- `downloader.py`：按 URL 路由到对应 Platform，下载音频 + 元数据
- `transcriber.py`：输入音频，输出 JSON 逐字稿
- 命令行脚本 `scripts/test_pipeline.py` 串起来
- **验收**：命令行跑一条抖音视频，得到 .json 逐字稿 + 正确的博主/视频元数据入库

### Phase 3：LLM 整理（~1.5 小时）
- `polisher_base.py` 定义抽象接口
- `polisher_ollama.py` 实现（调 Ollama `/api/chat`，JSON 输出约定，长文本分段）
- **验收**：命令行用 Ollama 整理一段逐字稿，检查 title/summary/tags/body 四项齐全，行文自然无口语赘余

### Phase 4：Web 任务提交（~3 小时）
- 首页输入框 + 提交接口
- BackgroundTasks 异步跑 pipeline
- SSE 进度推送
- 首页显示实时进度条
- **验收**：浏览器提交链接，看进度条跑完，点击看到文章

### Phase 5：博主库 + 文章阅读页（~3 小时）
- 博主列表、详情
- 文章阅读页（markdown 渲染）
- 基本样式打磨
- **验收**：已处理多条视频后，能从博主库点进文章阅读

### Phase 6：博主批量导入 + Cookie（~3 小时）
- 设置页 cookie 上传
- 博主主页链接 → 拉视频列表 → 用户选择
- 批量提交
- **验收**：提交一个博主主页，选 5 条视频批量处理完

### 总预估
**全部完成 ~17 小时开发时间**。如果不追求美观、只要能跑，前 4 个 Phase（~11 小时）就能拿到完整可用工具。

---

## 十一、风险与注意事项

### 11.1 抖音反爬

- 单条视频链接一般不需要 cookie
- 博主主页遍历必须带 cookie，且频率不能太高（限制并发下载数为 3）
- 抖音接口变动频繁，yt-dlp 可能失效，需要保持 `pip install -U yt-dlp`
- 失败时前端明确提示："如遇失败，尝试在设置页导入 cookie 或升级 yt-dlp"

### 11.2 版权

工具定位为"个人知识管理"，所有文章都附带原视频链接。如果以后支持导出/分享，需要在页面加提示。

### 11.3 磁盘占用

- 一条 10 分钟音频 mp3 约 10MB，1000 条视频 = 10GB
- 默认处理完成后保留音频 7 天，之后自动清理（设置页可调）
- 逐字稿和文章是纯文本，占用忽略不计

### 11.4 LLM 成本与模型

- 本地 Ollama：零成本，但 Qwen2.5-72B 首次下载约 40GB，首次加载进内存约 20-30 秒
- 若 72B 单篇整理速度不够快，可切到 `qwen2.5:32b`（仍然很好）或 `qwen2.5:14b`（最快）
- 未来接入 Claude API 的参考成本：10 分钟视频约 2500 字逐字稿，生成 2000 字文章，Sonnet 单篇约 $0.03–0.05

### 11.5 mlx-whisper 依赖

- 需要 macOS 13.3+ 和 Apple Silicon（你的 M5 Max 满足）
- 首次运行自动下载模型（large-v3 约 3GB）
- 备选：如果 mlx-whisper 出问题，回退到 `faster-whisper` + MPS

### 11.6 PostgreSQL 服务

- PostgreSQL 是长驻后台服务，通过 `brew services start postgresql@16` 启动，重启 Mac 后自动恢复
- 默认监听 `127.0.0.1:5432`，不对外暴露
- 内存占用约 50–100 MB（相对 128GB 可忽略）
- 数据目录在 `/opt/homebrew/var/postgresql@16/`，升级 Postgres 主版本时需要数据迁移（`pg_upgrade`），短期不会遇到

### 11.7 统计数据时效性

- 点赞/评论/粉丝这些数据是**抓取时刻的快照**，不是实时
- 设计上用 `stats_fetched_at` 标注时间，文章里渲染时也明确显示
- 提供"刷新博主数据"按钮，手动触发更新

---

## 十二、验收标准（MVP 通过的最低门槛）

1. ✅ 浏览器打开 `localhost:8000`，输入一条抖音视频链接，10 分钟内得到一篇整理好的文章
2. ✅ 使用本地 Ollama 完成文章整理，设置页可切换已安装的模型
3. ✅ 能提交博主主页，选择视频批量处理
4. ✅ 有博主库视图，能按博主查看所有文章
5. ✅ 文章阅读页能并排看原逐字稿和整理文章
6. ✅ 所有长任务有实时进度条，不需要刷新页面
7. ✅ 生成的 .md 文件自带完整 YAML front matter 和视频信息卡片，包含博主和视频的全部元数据

---

## 附录 A：依赖清单

```toml
[project]
name = "voxpress"
version = "0.1.0"
description = "Turn spoken video content into structured articles. MVP: Douyin."
requires-python = ">=3.11"

dependencies = [
    # Web
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "jinja2>=3.1",
    "python-multipart>=0.0.12",
    "sse-starlette>=2.1",

    # DB
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.30",
    "pgvector>=0.3.6",              # pgvector 的 SQLAlchemy 集成
    "alembic>=1.13",

    # 管道
    "yt-dlp>=2025.1.0",
    "mlx-whisper>=0.4",

    # LLM（MVP 只用 Ollama，通过 httpx 调）
    "httpx>=0.28",
    # "anthropic>=0.40",            # 后续接入 Claude 时启用

    # 工具
    "pyyaml>=6.0",
    "pydantic-settings>=2.6",
    "python-dotenv>=1.0",
]
```

## 附录 B：启动命令

```bash
# ---- 一次性环境准备 ----
# 1. 安装 PostgreSQL 16 和 pgvector
brew install postgresql@16 pgvector
brew services start postgresql@16

# 2. 建库 + 启用扩展
createdb voxpress
psql voxpress <<EOF
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
EOF

# 3. 安装 Ollama（本地 LLM 方案）
brew install ollama
brew services start ollama
ollama pull qwen2.5:72b

# ---- 项目 ----
cd voxpress
uv sync                                           # 或 pip install -e .

# 配置数据库连接（.env）
echo 'DATABASE_URL=postgresql+asyncpg://localhost/voxpress' > .env

# 跑迁移建表
alembic upgrade head

# 启动
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 浏览器打开
open http://127.0.0.1:8000
```

## 附录 C：数据库维护命令

```bash
# 备份整个数据库
pg_dump voxpress > backup_$(date +%Y%m%d).sql

# 恢复
psql voxpress < backup_20260420.sql

# 只备份结构（不含数据）
pg_dump -s voxpress > schema.sql

# 连进去看数据
psql voxpress

# 常用查询（psql 内）
\dt                           -- 列出所有表
\d creator                    -- 查看 creator 表结构
SELECT count(*) FROM video;   -- 视频总数
```
