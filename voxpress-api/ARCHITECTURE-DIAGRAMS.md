# VoxPress 架构可视化

基于 [ARCHITECTURE.md](./ARCHITECTURE.md) 的可视化补充。用 Mermaid 覆盖以下六个视角：

1. [进程拓扑与外部依赖](#一进程拓扑与外部依赖)
2. [数据模型关系](#二数据模型关系)
3. [任务端到端生命周期（时序图）](#三任务端到端生命周期时序图)
4. [Pipeline 四阶段内部流程](#四pipeline-四阶段内部流程)
5. [任务状态机](#五任务状态机)
6. [SSE 事件流：从 pg_notify 到浏览器](#六sse-事件流从-pg_notify-到浏览器)

> GitHub / VS Code Markdown 预览原生支持 Mermaid 渲染。本地用 `Obsidian`、`Typora` 也可直接查看。

---

## 一、进程拓扑与外部依赖

展示"谁和谁说话、谁拉起谁"。核心观察是 **API / Worker 完全解耦，只通过 Postgres 通信**。

```mermaid
flowchart TB
    FE["前端<br/>(Vite dev server)"]

    subgraph Procs["本机进程"]
        API["API 进程<br/>uvicorn · voxpress.main:app<br/>:8787"]
        Worker["Worker 进程<br/>python -m voxpress.worker"]
        Sub["转写子进程<br/>jobs/transcribe.py<br/>(按需 fork)"]
    end

    PG[("Postgres 16<br/>pgvector · pg_trgm<br/>业务数据 + 任务队列 + 事件总线")]

    subgraph Ext["外部依赖"]
        Douyin["Douyin / F2<br/>元信息 · 媒体直链"]
        OSS["OSS<br/>媒体长期归档"]
        Ollama["Ollama<br/>本地 LLM"]
        MLX["mlx-whisper<br/>Apple Silicon"]
    end

    FE -- "REST · SSE" --> API
    API -- "读写 · NOTIFY" --> PG
    PG -. "LISTEN task_events" .-> API
    Worker -- "FOR UPDATE SKIP LOCKED<br/>heartbeat · NOTIFY" --> PG
    Worker -- "fork / exec" --> Sub
    Worker --> Douyin
    Worker --> OSS
    Worker --> Ollama
    Sub --> MLX

    classDef api fill:#e3f2fd,stroke:#1976d2
    classDef worker fill:#fff3e0,stroke:#f57c00
    classDef state fill:#e8f5e9,stroke:#388e3c
    class API api
    class Worker,Sub worker
    class PG state
```

**拓扑要点**

| 角色 | 责任 | 崩溃影响 |
|---|---|---|
| API 进程 | REST + SSE + 写任务记录，**不执行 pipeline** | 前端掉线；任务仍在 DB 里，worker 不受影响 |
| Worker 进程 | 抢任务、执行四阶段、维持租约 | 任务 lease 超时后被其他 worker 续上；API 正常 |
| 转写子进程 | 每次任务启动一个、跑 mlx-whisper、JSON 输出 | 只杀自己；worker 主进程收到非零退出码后标记阶段失败 |
| Postgres | 业务库 + 任务队列 + 事件总线（NOTIFY/LISTEN）| 整个系统停摆——这是唯一的单点 |

---

## 二、数据模型关系

展示业务主表与任务相关表的连接方式。任务与业务数据通过 `video_id` / `creator_id` 绑定，中间产物挂在 `task_artifacts`。

```mermaid
erDiagram
    creators ||--o{ videos : "拥有"
    videos  ||--o| articles : "生成一篇"
    articles ||--o{ transcript_segments : "分段"
    videos  ||--o{ tasks : "触发"
    tasks   ||--o{ task_artifacts : "阶段产物"

    creators {
        bigint id PK
        text   platform
        text   platform_user_id
        text   nickname
        bigint follower_count
        jsonb  extra
    }
    videos {
        bigint id PK
        bigint creator_id FK
        text   platform_video_id
        text   title
        bigint like_count
        bigint comment_count
        text   media_url
    }
    articles {
        bigint id PK
        bigint video_id FK
        text   title
        text   body_md
        text   summary
        jsonb  tags
    }
    transcript_segments {
        bigint id PK
        bigint article_id FK
        int    index
        real   start_sec
        real   end_sec
        text   text
    }
    tasks {
        bigint    id PK
        text      stage
        text      status
        timestamptz run_after
        text      lease_owner
        timestamptz lease_expires_at
        timestamptz last_heartbeat_at
        int       attempt_count
    }
    task_artifacts {
        bigint task_id FK
        jsonb  transcript_segments
        jsonb  organized
    }
    settings {
        text  key PK
        jsonb value
    }
```

**为什么这么分**

- `task_artifacts` 把"中间产物"（逐字稿 JSON、整理后 JSON）从业务主表里剥离，这样**重跑任务不会污染已发布的文章**——`save` 成功才把最终结果写进 `articles` / `transcript_segments`。
- `tasks` 的租约字段（`lease_owner / lease_expires_at / last_heartbeat_at / attempt_count`）是整个可靠性机制的关键，单独组合成一块租约子模块。

---

## 三、任务端到端生命周期（时序图）

从"粘贴链接"到"文章可读"的完整链路。注意 **API 和 Worker 从来不直接通信**，全程靠 Postgres 转发。

```mermaid
sequenceDiagram
    actor U as 用户
    participant FE as 前端
    participant API as API 进程
    participant PG as Postgres
    participant W as Worker
    participant Sub as 转写子进程
    participant Ext as 外部服务<br/>(Douyin/Ollama/OSS)

    U->>FE: 粘贴抖音链接
    FE->>API: POST /api/tasks
    API->>PG: INSERT tasks (queued)
    API->>PG: pg_notify('task_events', create)
    PG-->>API: LISTEN 收到 create
    API-->>FE: SSE: task.create
    API-->>FE: 201 {task_id}

    Note over W,PG: worker 循环轮询
    W->>PG: SELECT ... FOR UPDATE SKIP LOCKED
    PG-->>W: 一条 queued 任务
    W->>PG: UPDATE stage=download, status=running,<br/>lease_owner=me, lease_expires=now+60s
    W->>PG: pg_notify (update)
    PG-->>FE: SSE: task.update (download)

    loop heartbeat 每 20s
        W->>PG: UPDATE last_heartbeat_at, lease_expires
    end

    W->>Ext: 拉元信息 + 下载 mp4
    W->>W: 抽音频 m4a
    W->>PG: upsert creator, video
    W->>PG: 推进 stage=transcribe
    PG-->>FE: SSE: task.update (transcribe)

    W->>Sub: fork (audio_path)
    Sub->>Ext: mlx-whisper 转写
    Sub-->>W: JSON segments
    W->>PG: task_artifacts.transcript_segments
    W->>PG: 推进 stage=organize
    PG-->>FE: SSE: task.update (organize)

    W->>Ext: Ollama 整理
    Ext-->>W: JSON {title, body, ...}
    W->>PG: task_artifacts.organized
    W->>PG: 推进 stage=save
    PG-->>FE: SSE: task.update (save)

    W->>PG: INSERT/UPDATE articles
    W->>PG: 重写 transcript_segments
    W->>PG: status=done, 清理 artifacts
    PG-->>FE: SSE: task.update (done)

    FE->>API: GET /api/articles/{id}
    API->>PG: SELECT
    API-->>FE: 文章 JSON
```

**关键观察**

- **heartbeat 循环**在任务全程持续，一旦 worker 崩溃或断网，lease 会超时，其他 worker 在下一轮轮询时重新抢占——这是自愈机制。
- 每次阶段推进都有一次 `pg_notify` + 一次 SSE 推送，前端进度条跟实际阶段严格同步。
- **API 从头到尾没执行任何 pipeline 代码**，也没跟 Worker 直接建连接。

---

## 四、Pipeline 四阶段内部流程

每个阶段的职责、输入、输出、外部依赖。

```mermaid
flowchart LR
    Q([queued]) --> D

    subgraph D["download"]
        D1[查 OSS/本地<br/>媒体缓存] --> D2{命中?}
        D2 -- 否 --> D3[f2 抓元信息]
        D3 --> D4[下载 mp4]
        D4 --> D5[提取 m4a]
        D2 -- 是 --> D5
        D5 --> D6[upsert<br/>creator · video]
    end

    subgraph T["transcribe"]
        T1[准备音频路径] --> T2[fork 子进程]
        T2 --> T3[mlx-whisper]
        T3 --> T4[写 task_artifacts<br/>.transcript_segments]
    end

    subgraph O["organize"]
        O1[读 transcript] --> O2[调 Ollama<br/>JSON 输出]
        O2 --> O3[写 task_artifacts<br/>.organized]
    end

    subgraph S["save"]
        S1[读 organized] --> S2[upsert articles]
        S2 --> S3[重写 transcript_segments]
        S3 --> S4[清理 artifacts]
    end

    D --> T --> O --> S --> Done([done])

    classDef stage fill:#fafafa,stroke:#616161
    class D,T,O,S stage
```

**阶段并发策略**（来自 [voxpress/config.py](./voxpress/config.py)）

| 阶段 | 默认并发 | 原因 |
|---|---|---|
| download | 4 | 网络 IO 密集，可并行 |
| **transcribe** | **1** | mlx-whisper 并发会触发 Metal 断言崩溃 |
| organize | 2 | 读设置里的 `llm.concurrency` 动态收敛 |
| save | 4 | 轻量 DB 写入 |

---

## 五、任务状态机

```mermaid
stateDiagram-v2
    [*] --> queued: POST /api/tasks
    queued --> running: worker 抢占<br/>(lease 建立)
    running --> running: 阶段推进<br/>(download→transcribe→organize→save)
    running --> queued: lease 过期<br/>(heartbeat 失联)
    running --> done: save 阶段完成
    running --> failed: 子进程/外部调用异常
    running --> canceled: 用户取消
    failed --> queued: 自动重试<br/>(规划中)
    done --> [*]
    failed --> [*]
    canceled --> [*]

    note right of running
        stage 字段在 running 状态内部推进：
        download → transcribe → organize → save
    end note

    note left of queued
        run_after 字段控制
        何时可被重新抢占
        (用于退避重试)
    end note
```

**状态转移规则**

- `queued → running`：基于 `FOR UPDATE SKIP LOCKED + run_after <= now()`，天然避免多 worker 抢同一条。
- `running → queued`：当 `lease_expires_at < now()`（heartbeat 超过阈值未续约），其他 worker 可直接重新 SKIP LOCKED 抢占，原持有者任何后续写入都会因 lease_owner 不匹配而失败。
- `failed → queued`：目前是手动重建任务；ARCHITECTURE.md §10.2 列为待办。

---

## 六、SSE 事件流：从 pg_notify 到浏览器

新架构里 **SSE 不再依赖 API 进程内的 asyncio.Queue**，而是基于 Postgres 的 `LISTEN/NOTIFY`。这让 API 和 Worker 两个进程都能作为事件发布方，前端只订阅一次。

```mermaid
sequenceDiagram
    participant API as API 进程
    participant Worker as Worker 进程
    participant PG as Postgres
    participant FE as 前端 EventSource

    Note over API: 启动时
    API->>PG: LISTEN task_events

    Note over FE: 用户打开页面
    FE->>API: GET /api/tasks/stream
    API-->>FE: 保持连接 (SSE)

    par API 创建任务
        API->>PG: INSERT tasks
        API->>PG: pg_notify('task_events', '{"kind":"create",...}')
    and Worker 推进阶段
        Worker->>PG: UPDATE tasks SET stage=...
        Worker->>PG: pg_notify('task_events', '{"kind":"update",...}')
    end

    PG-->>API: 通过 LISTEN 通道推送 payload
    API->>API: 解析 payload, 定向或广播
    API-->>FE: SSE event: task.create
    API-->>FE: SSE event: task.update
    API-->>FE: SSE event: task.remove
```

**三类事件**

| 事件 | 触发时机 | 前端行为 |
|---|---|---|
| `task.create` | 新任务入库 | 列表里插入一行 |
| `task.update` | 阶段推进、状态变化、心跳 | 更新进度条、状态标签 |
| `task.remove` | 任务被清理 | 从列表移除 |

**为什么不用内存 Queue**

- 多进程广播：API 用 gunicorn 或多 worker 启动时，内存 Queue 就跨不了进程
- 外部写入：未来定时任务、CLI 工具、甚至 SQL 脚本改任务，都能统一触发 SSE
- 重启恢复：API 重启不会丢事件通道，只要重新 LISTEN 就继续工作

---

## 七、一张图看懂"为什么这样设计"

把 ARCHITECTURE.md §1 的"核心设计目标"画成决策路径：

```mermaid
flowchart TD
    P1[核心痛点]
    P1 --> Q1[mlx-whisper 偶发<br/>Metal 崩溃会连带<br/>打死 API]
    P1 --> Q2[进程内内存队列<br/>重启即丢任务]
    P1 --> Q3[API / 重任务<br/>职责混杂]

    Q1 --> S1[转写跑在子进程<br/>主进程只接收 JSON]
    Q2 --> S2[任务持久化到 Postgres<br/>带租约 + heartbeat]
    Q3 --> S3[API / Worker 分进程<br/>通过 DB 解耦]

    S1 --> R1[单次转写崩溃<br/>只影响当前任务]
    S2 --> R2[任何进程重启<br/>任务继续跑]
    S3 --> R3[API 可安全重启部署<br/>不中断正在跑的任务]

    style P1 fill:#ffebee,stroke:#c62828
    style R1 fill:#e8f5e9,stroke:#388e3c
    style R2 fill:#e8f5e9,stroke:#388e3c
    style R3 fill:#e8f5e9,stroke:#388e3c
```

---

## 附：图例索引

| 图编号 | 类型 | 回答什么问题 |
|---|---|---|
| 图一 | flowchart | 有哪些进程 / 跟谁说话 |
| 图二 | ER | 数据怎么组织 |
| 图三 | sequence | 一条任务的完整命运 |
| 图四 | flowchart | 每个阶段内部发生什么 |
| 图五 | state | 任务可以处于哪些状态、怎么迁移 |
| 图六 | sequence | 实时事件怎么从后端传到前端 |
| 图七 | flowchart | 每个设计决策对应解决了什么问题 |

---

**文档维护**：若 ARCHITECTURE.md 中的阶段顺序、并发配置或表结构变动，同步更新对应图（图三、图四、图二）。Mermaid 源码直接写在本文件里，不引入图床。
