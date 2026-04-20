import type {
  Article,
  ArticleDetail,
  Page,
  Settings,
  Task,
  Video,
} from '@/types/api';
import { articles, articleDetails } from './fixtures/articles';
import { creators } from './fixtures/creators';
import { videosByCreator } from './fixtures/videos';
import { availableModels, defaultSettings } from './fixtures/settings';
import { mockStore } from './store';

let settings: Settings = JSON.parse(JSON.stringify(defaultSettings));

function page<T>(items: T[], cursor: string | null = null, total?: number): Page<T> {
  return { items, cursor, total: total ?? items.length };
}

function match(path: string, pattern: RegExp) {
  return path.match(pattern);
}

function delay<T>(value: T, ms = 120): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

type Method = 'GET' | 'POST' | 'PATCH' | 'DELETE';

export async function handleRequest(method: Method, rawPath: string, body?: unknown): Promise<unknown> {
  const [path, queryString = ''] = rawPath.split('?');
  const params = new URLSearchParams(queryString);

  // Health
  if (method === 'GET' && path === '/api/health') {
    return delay({ ok: true, version: '0.4.0', ollama: true, whisper: true, db: true });
  }

  // Creators
  if (method === 'GET' && path === '/api/creators') {
    const sort = params.get('sort') ?? 'followers:desc';
    const q = params.get('q')?.toLowerCase() ?? '';
    const verified = params.get('verified');
    let items = [...creators];
    if (q) {
      items = items.filter(
        (c) =>
          c.name.toLowerCase().includes(q) ||
          c.handle.toLowerCase().includes(q) ||
          (c.bio ?? '').toLowerCase().includes(q),
      );
    }
    if (verified === '1') items = items.filter((c) => c.verified);
    if (sort === 'followers:desc') items.sort((a, b) => b.followers - a.followers);
    return delay(page(items, null, items.length));
  }

  if (method === 'GET' && (match(path, /^\/api\/creators\/(\d+)$/))) {
    const m = path.match(/^\/api\/creators\/(\d+)$/)!;
    const id = Number(m[1]);
    const c = creators.find((c) => c.id === id);
    if (!c) throw apiError('creator_not_found', '博主不存在', 404);
    return delay(c);
  }

  if (method === 'POST' && path === '/api/creators/resolve') {
    const url = (body as { url?: string } | undefined)?.url ?? '';
    const c = creators[Math.abs(hashString(url)) % creators.length];
    return delay(c);
  }

  // Videos
  const videosMatch = match(path, /^\/api\/creators\/(\d+)\/videos$/);
  if (method === 'GET' && videosMatch) {
    const id = Number(videosMatch[1]);
    const all = videosByCreator[id] ?? [];
    const minDur = Number(params.get('min_dur') ?? 0);
    const minLikes = Number(params.get('min_likes') ?? 0);
    const since = params.get('since');
    let items: Video[] = all.filter((v) => v.duration_sec >= minDur && v.likes >= minLikes);
    if (since === '30d') {
      const cutoff = Date.now() - 30 * 86_400_000;
      items = items.filter((v) => Date.parse(v.published_at) >= cutoff);
    }
    return delay(page(items, null, items.length));
  }

  // Articles
  if (method === 'GET' && path === '/api/articles') {
    const q = params.get('q')?.toLowerCase() ?? '';
    const creatorId = params.get('creator_id');
    const tag = params.get('tag');
    const since = params.get('since');
    let items: Article[] = [...articles];
    if (q) items = items.filter((a) => a.title.toLowerCase().includes(q));
    if (creatorId) items = items.filter((a) => a.creator_id === Number(creatorId));
    if (tag) items = items.filter((a) => a.tags.includes(tag));
    if (since === '30d') {
      const cutoff = Date.now() - 30 * 86_400_000;
      items = items.filter((a) => Date.parse(a.published_at) >= cutoff);
    }
    items.sort((a, b) => Date.parse(b.published_at) - Date.parse(a.published_at));
    const limit = Number(params.get('limit') ?? items.length);
    return delay(page(items.slice(0, limit), null, articles.length));
  }

  const articleMatch = match(path, /^\/api\/articles\/([\w-]+)$/);
  if (method === 'GET' && articleMatch) {
    const id = articleMatch[1];
    const detail = articleDetails[id] as ArticleDetail | undefined;
    if (!detail) throw apiError('not_found', '文章不存在', 404);
    return delay(detail);
  }

  const rebuildMatch = match(path, /^\/api\/articles\/([\w-]+)\/rebuild$/);
  if (method === 'POST' && rebuildMatch) {
    const id = rebuildMatch[1];
    const detail = articleDetails[id];
    if (!detail) throw apiError('not_found', '文章不存在', 404);
    const task = mockStore.createTask(detail.source.source_url);
    return delay({ task_id: task.id });
  }

  // Tasks
  if (method === 'GET' && path === '/api/tasks') {
    const status = params.get('status');
    let items: Task[] = mockStore.getAllTasks();
    if (status) items = items.filter((t) => t.status === status);
    return delay(page(items, null, items.length));
  }

  if (method === 'POST' && path === '/api/tasks') {
    const url = (body as { url?: string } | undefined)?.url ?? '';
    if (!url) throw apiError('invalid_url', '链接不能为空', 400);
    const t = mockStore.createTask(url);
    return delay(t);
  }

  if (method === 'POST' && path === '/api/tasks/batch') {
    const b = body as { video_ids?: string[] } | undefined;
    const ids = b?.video_ids ?? [];
    const tasks = ids.map((vid) => mockStore.createTask(`https://www.douyin.com/video/${vid}`));
    return delay({ tasks });
  }

  const cancelMatch = match(path, /^\/api\/tasks\/([\w-]+)\/cancel$/);
  if (method === 'POST' && cancelMatch) {
    const t = mockStore.cancelTask(cancelMatch[1]);
    if (!t) throw apiError('task_not_found', '任务不存在', 404);
    return delay(t);
  }

  // Settings
  if (method === 'GET' && path === '/api/settings') return delay(settings);
  if (method === 'PATCH' && path === '/api/settings') {
    settings = deepMerge(settings, (body ?? {}) as Partial<Settings>);
    return delay(settings);
  }

  if (method === 'POST' && path === '/api/cookie') {
    const text = (body as { text?: string } | undefined)?.text ?? '';
    settings = deepMerge(settings, {
      cookie: { status: 'ok', last_tested_at: new Date().toISOString(), text },
    });
    return delay({ status: 'ok' });
  }

  if (method === 'POST' && path === '/api/cookie/test') {
    if (settings.cookie.status === 'missing') {
      throw apiError('cookie_missing', '未导入 Cookie', 403);
    }
    return delay({ status: 'ok', handle_sample: '@laoqian-ai' });
  }

  if (method === 'GET' && path === '/api/models') {
    return delay({ ollama: availableModels });
  }

  throw apiError('route_not_found', `Mock 未处理: ${method} ${rawPath}`, 404);
}

function apiError(code: string, message: string, status: number) {
  const err = new Error(message) as Error & { code: string; status: number };
  err.code = code;
  err.status = status;
  return err;
}

function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return h;
}

function deepMerge<T>(target: T, patch: Partial<T>): T {
  const out: Record<string, unknown> = { ...(target as Record<string, unknown>) };
  for (const [k, v] of Object.entries(patch as Record<string, unknown>)) {
    const existing = out[k];
    if (v != null && typeof v === 'object' && !Array.isArray(v) && typeof existing === 'object' && existing != null) {
      out[k] = deepMerge(existing as T, v as Partial<T>);
    } else {
      out[k] = v;
    }
  }
  return out as T;
}

export type { Method };
