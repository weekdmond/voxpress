# 05 · API Schema

> Base URL：`VITE_API_BASE`（默认 `http://localhost:8787`）
> 所有响应：`application/json`（除 SSE）
> 错误包络：`{ error: { code: string, message: string, detail?: any } }`

## TypeScript 类型

以下类型既是前端 `src/types/api.ts`，也是后端（OpenAPI）契约。

```ts
// ═══════════════════════════════════════════════════════
// Shared
// ═══════════════════════════════════════════════════════
export type ISO8601 = string;    // e.g. "2026-04-15T19:23:00Z"
export type Platform = 'douyin'; // MVP only

export interface Page<T> {
  items: T[];
  cursor: string | null;  // null = no more
  total?: number;         // optional count
}

// ═══════════════════════════════════════════════════════
// Creator
// ═══════════════════════════════════════════════════════
export interface Creator {
  id: number;
  platform: Platform;
  handle: string;                // "@laoqian-ai"
  name: string;                  // "老钱说AI"
  initial: string;               // "老" — derived, first grapheme
  bio: string | null;
  region: string | null;         // "北京"
  verified: boolean;             // 蓝V
  followers: number;
  total_likes: number;
  article_count: number;         // 已整理文章数
  video_count: number;           // 已发现视频数
  recent_update_at: ISO8601 | null;
  imported_at: ISO8601;
}

// ═══════════════════════════════════════════════════════
// Video (from creator's page, before processing)
// ═══════════════════════════════════════════════════════
export interface Video {
  id: string;                    // platform video id
  creator_id: number;
  title: string;
  duration_sec: number;          // 512 → rendered as "8:32"
  likes: number;
  plays: number;
  comments: number;
  shares: number;
  collects: number;
  published_at: ISO8601;
  cover_url: string | null;      // we don't fetch, only pass through
  source_url: string;            // canonical douyin.com/video/...
  article_id: string | null;     // if already processed
}

// ═══════════════════════════════════════════════════════
// Article
// ═══════════════════════════════════════════════════════
export interface Article {
  id: string;                    // uuid
  video_id: string;
  creator_id: number;
  title: string;
  summary: string;
  content_md: string;            // markdown source
  content_html: string;          // server-rendered + sanitized
  word_count: number;
  tags: string[];
  likes_snapshot: number;        // from video at processing time
  published_at: ISO8601;         // video's published_at
  created_at: ISO8601;           // our processing time
  updated_at: ISO8601;
}

export interface ArticleDetail extends Article {
  source: ArticleSource;
  segments: TranscriptSegment[];
}

export interface ArticleSource {
  platform: Platform;
  source_url: string;
  duration_sec: number;
  metrics: {
    likes: number; comments: number; shares: number; collects: number; plays: number;
  };
  topics: string[];             // ["AI", "职场", "科技观察"]
  creator_snapshot: {
    name: string; handle: string; followers: number; verified: boolean; region: string | null;
  };
}

export interface TranscriptSegment {
  ts_sec: number;               // start timestamp in seconds
  text: string;
}

// ═══════════════════════════════════════════════════════
// Task
// ═══════════════════════════════════════════════════════
export type TaskStage = 'download' | 'transcribe' | 'organize' | 'save';
export type TaskStatus = 'queued' | 'running' | 'done' | 'failed' | 'canceled';

export interface Task {
  id: string;                   // uuid
  source_url: string;
  title_guess: string;          // filled ASAP from metadata
  creator_id: number | null;    // filled after resolve
  creator_name: string | null;
  creator_initial: string | null;
  stage: TaskStage;
  status: TaskStatus;
  progress: number;             // 0–100
  eta_sec: number | null;
  detail: string | null;        // "mlx-whisper large-v3"
  article_id: string | null;    // filled on completion
  error: string | null;
  started_at: ISO8601;
  updated_at: ISO8601;
  finished_at: ISO8601 | null;
}

// ═══════════════════════════════════════════════════════
// Settings
// ═══════════════════════════════════════════════════════
export interface Settings {
  llm: {
    backend: 'ollama' | 'claude';
    model: string;               // "qwen2.5:72b"
    concurrency: number;         // 1–20
  };
  whisper: {
    model: 'large-v3' | 'medium' | 'small';
    language: 'zh' | 'auto';
  };
  prompt: {
    version: string;             // "v1.0"
    template: string;             // free-form
  };
  cookie: {
    status: 'missing' | 'ok' | 'expired';
    last_tested_at: ISO8601 | null;
  };
  storage: {
    audio_retain_days: number;   // 0 = delete immediately
    used_bytes: number;
  };
}
```

## REST Endpoints

### Health
- `GET /api/health` → `{ ok: true, version: "0.4.0", ollama: true, whisper: true, db: true }`

### Creators

| Method | Path | Body / Query | Response |
|---|---|---|---|
| GET | `/api/creators` | `?sort=followers:desc&cursor=...` | `Page<Creator>` |
| GET | `/api/creators/:id` | — | `Creator` |
| POST | `/api/creators/resolve` | `{ url: string }` | `Creator` (从主页 URL 解析) |
| DELETE | `/api/creators/:id` | — | `204` |

### Videos

| Method | Path | Query | Response |
|---|---|---|---|
| GET | `/api/creators/:id/videos` | `?min_dur=180&min_likes=10000&since=30d&cursor=...` | `Page<Video>` |
| POST | `/api/creators/:id/refresh` | — | `{ queued: true }` — 异步刷新视频列表 |

### Articles

| Method | Path | Body / Query | Response |
|---|---|---|---|
| GET | `/api/articles` | `?q=&creator_id=&tag=&since=30d&cursor=` | `Page<Article>` |
| GET | `/api/articles/:id` | — | `ArticleDetail` |
| PATCH | `/api/articles/:id` | `{ title?, tags?, content_md? }` | `Article` |
| DELETE | `/api/articles/:id` | — | `204` |
| POST | `/api/articles/:id/rebuild` | — | `{ task_id: string }` |
| GET | `/api/articles/:id/export.md` | — | `text/markdown` 下载 |

### Tasks

| Method | Path | Body / Query | Response |
|---|---|---|---|
| POST | `/api/tasks` | `{ url: string }` | `Task` — 单条视频 |
| POST | `/api/tasks/batch` | `{ video_ids: string[] }` 或 `{ creator_id, filter: {...} }` | `{ tasks: Task[] }` |
| GET | `/api/tasks` | `?status=running\|queued\|done&limit=50` | `Page<Task>` |
| GET | `/api/tasks/:id` | — | `Task` |
| POST | `/api/tasks/:id/cancel` | — | `Task` |

### Settings

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/settings` | — | `Settings` |
| PATCH | `/api/settings` | `Partial<Settings>` | `Settings` |
| POST | `/api/cookie` | multipart `file` 或 `{ text: string }` | `{ status: 'ok'\|'invalid' }` |
| POST | `/api/cookie/test` | — | `{ status: 'ok'\|'expired', handle_sample?: string }` |
| GET | `/api/models` | — | `{ ollama: string[] }` — 调 `/api/tags` |

## SSE — 任务进度推送

**Endpoint**：`GET /api/tasks/stream` · `Content-Type: text/event-stream`

- 新连接：立即 replay 当前所有 `running` 和 `queued` 任务（快照）
- 后续推送：任何 `Task` 字段变更都发送一次完整 `Task` 对象
- 心跳：每 20s 一个 `: heartbeat\n\n`（注释行）

### 事件格式

```
event: task.update
data: {"id":"t_47","status":"running","stage":"transcribe","progress":62,"detail":"mlx-whisper large-v3","eta_sec":272,...}

event: task.create
data: {"id":"t_50","status":"queued",...}

event: task.remove
data: {"id":"t_46"}   // 完成/失败后从流中移除（前端把它移到「最近完成」）
```

### 客户端实现

```ts
// src/lib/sse.ts
export function subscribeTasks(onEvent: (e: {type: 'update'|'create'|'remove', task: Task | {id: string}}) => void) {
  const es = new EventSource(`${import.meta.env.VITE_SSE_BASE}/api/tasks/stream`);
  ['update','create','remove'].forEach(type => {
    es.addEventListener(`task.${type}`, (ev) => {
      onEvent({ type: type as any, task: JSON.parse((ev as MessageEvent).data) });
    });
  });
  return () => es.close();
}
```

### 与 TanStack Query 协同

```ts
// useRunningTasks.ts
export function useRunningTasks() {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ['tasks', 'running'],
    queryFn: () => api.get<Page<Task>>('/api/tasks?status=running').then(r => r.items),
  });
  useEffect(() => subscribeTasks(({type, task}) => {
    qc.setQueryData<Task[]>(['tasks', 'running'], (old = []) => {
      if (type === 'remove') return old.filter(t => t.id !== task.id);
      if (type === 'create') return [task as Task, ...old];
      return old.map(t => t.id === (task as Task).id ? task as Task : t);
    });
  }), [qc]);
  return query;
}
```

## 错误码

| Code | HTTP | 含义 |
|---|---|---|
| `invalid_url` | 400 | URL 无法识别 / 非抖音域名 |
| `creator_not_found` | 404 | resolve 后不存在的博主主页 |
| `cookie_missing` | 403 | 博主主页操作，但未导入 Cookie |
| `cookie_expired` | 403 | Cookie 过期 |
| `ollama_unavailable` | 502 | 后端下游 Ollama 不可达 |
| `whisper_failed` | 500 | 转写失败 |
| `task_not_found` | 404 | |
| `already_processed` | 409 | 提交的视频已有对应文章 |

## Demo / Mock

开发期可跑一个 `miragejs` 或 `msw` 的 mock：把 `VoxPress v3 (高保真).html` 里 `creators` / `articles` / `runningTasks` 三个数组导出成 JSON 放到 `src/mocks/fixtures/`，handlers 按此文档 shape 返回。
