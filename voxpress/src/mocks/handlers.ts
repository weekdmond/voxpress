import type {
  Article,
  ArticleDetail,
  Page,
  Settings,
  TaskCancelResult,
  TaskDetail,
  TaskRerunResult,
  TaskSummary,
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
    return delay({
      ok: true,
      version: '0.4.0',
      ollama: true,
      whisper: true,
      db: true,
      deploy_commit: 'mock123',
      deploy_branch: 'main',
      deployed_at: new Date().toISOString(),
    });
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
    if (!c) throw apiError('creator_not_found', '创作者不存在', 404);
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
  if (method === 'GET' && path === '/api/articles/facets') {
    const q = params.get('q')?.toLowerCase() ?? '';
    const creatorId = params.get('creator_id');
    const tag = params.get('tag');
    const topic = params.get('topic');
    const since = params.get('since');
    let base: Article[] = [...articles];
    if (q) base = base.filter((a) => a.title.toLowerCase().includes(q) || a.summary.toLowerCase().includes(q) || a.content_md.toLowerCase().includes(q));
    if (creatorId) base = base.filter((a) => a.creator_id === Number(creatorId));
    if (since && since.endsWith('d')) {
      const days = Number(since.slice(0, -1));
      if (days > 0) {
        const cutoff = Date.now() - days * 86_400_000;
        base = base.filter((a) => Date.parse(a.published_at) >= cutoff);
      }
    }
    const topicItems = tag ? base.filter((a) => a.tags.includes(tag)) : base;
    const tagItems = topic ? base.filter((a) => a.topics.includes(topic)) : base;
    const countValues = (items: Article[], key: 'tags' | 'topics') => {
      const counts = new Map<string, number>();
      items.forEach((a) => a[key].forEach((value) => counts.set(value, (counts.get(value) ?? 0) + 1)));
      return Array.from(counts.entries())
        .sort(([, a], [, b]) => b - a)
        .map(([value, count]) => ({ value, count }));
    };
    return delay({
      topics: countValues(topicItems, 'topics'),
      tags: countValues(tagItems, 'tags'),
    });
  }

  if (method === 'GET' && path === '/api/articles') {
    const q = params.get('q')?.toLowerCase() ?? '';
    const creatorId = params.get('creator_id');
    const tag = params.get('tag');
    const topic = params.get('topic');
    const since = params.get('since');
    let items: Article[] = [...articles];
    if (q) items = items.filter((a) => a.title.toLowerCase().includes(q) || a.summary.toLowerCase().includes(q) || a.content_md.toLowerCase().includes(q));
    if (creatorId) items = items.filter((a) => a.creator_id === Number(creatorId));
    if (tag) items = items.filter((a) => a.tags.includes(tag));
    if (topic) items = items.filter((a) => a.topics.includes(topic));
    if (since && since.endsWith('d')) {
      const days = Number(since.slice(0, -1));
      if (days > 0) {
        const cutoff = Date.now() - days * 86_400_000;
        items = items.filter((a) => Date.parse(a.published_at) >= cutoff);
      }
    }
    items.sort((a, b) => Date.parse(b.published_at) - Date.parse(a.published_at));
    const total = items.length;
    const limit = Number(params.get('limit') ?? items.length);
    return delay(page(items.slice(0, limit), null, total));
  }

  if (method === 'POST' && path === '/api/articles/share/claude') {
    const ids = ((body as { article_ids?: string[] } | undefined)?.article_ids ?? []).filter(Boolean);
    const matched = ids
      .map((id) => articleDetails[id])
      .filter((article): article is ArticleDetail => Boolean(article));
    const shareId = Math.random().toString(36).slice(2, 10);
    return delay({
      share_id: shareId,
      file_name: `speechfolio-source-pack-demo-${shareId}.md`,
      article_count: matched.length,
      download_url: `/api/articles/share/s/${shareId}`,
      writeback_url: `/api/articles/share/s/${shareId}/writeback`,
      local_file_path: `/tmp/voxpress/shares/${shareId}.md`,
      created_at: new Date().toISOString(),
      articles: matched.map((article) => ({
        id: article.id,
        title: article.title,
        creator_name: article.source.creator_snapshot.name,
      })),
      missing_ids: ids.filter((id) => !articleDetails[id]),
    });
  }

  const articleMatch = match(path, /^\/api\/articles\/([\w-]+)$/);
  if (method === 'GET' && articleMatch) {
    const id = articleMatch[1];
    const detail = articleDetails[id] as ArticleDetail | undefined;
    if (!detail) throw apiError('not_found', '文章不存在', 404);
    return delay(detail);
  }

  if (method === 'POST' && path === '/api/articles/batch/rebuild') {
    const ids = ((body as { article_ids?: string[] } | undefined)?.article_ids ?? []).filter(Boolean);
    const matched = ids.filter((id) => articleDetails[id]);
    const task_ids = matched.map((id) => {
      const detail = articleDetails[id];
      return mockStore.createTask(detail?.source.source_url ?? `https://www.douyin.com/video/${id}`).id;
    });
    return delay({
      requested: ids.length,
      matched: matched.length,
      processed: task_ids.length,
      task_ids,
      missing_ids: ids.filter((id) => !articleDetails[id]),
    });
  }

  if (method === 'POST' && path === '/api/articles/batch/delete') {
    const ids = new Set(((body as { article_ids?: string[] } | undefined)?.article_ids ?? []).filter(Boolean));
    const matchedIds = articles.filter((article) => ids.has(article.id)).map((article) => article.id);

    for (let i = articles.length - 1; i >= 0; i -= 1) {
      if (ids.has(articles[i].id)) articles.splice(i, 1);
    }
    matchedIds.forEach((id) => {
      delete articleDetails[id];
    });

    return delay({
      requested: ids.size,
      matched: matchedIds.length,
      processed: matchedIds.length,
      task_ids: [],
      missing_ids: Array.from(ids).filter((id) => !matchedIds.includes(id)),
    });
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
    const stage = params.get('stage');
    const model = params.get('model');
    const q = params.get('q')?.toLowerCase() ?? '';
    const pageNum = Number(params.get('page') ?? 1);
    const limit = Number(params.get('limit') ?? 20);
    let items: Task[] = mockStore.getAllTasks();
    if (status === 'active') items = items.filter((t) => t.status === 'running' || t.status === 'queued');
    else if (status) items = items.filter((t) => t.status === status);
    if (stage) items = items.filter((t) => t.stage === stage);
    if (model) items = items.filter((t) => t.primary_model === model);
    if (q) items = items.filter((t) => `${t.id} ${t.title_guess} ${t.article_title ?? ''} ${t.creator_name ?? ''}`.toLowerCase().includes(q));
    items.sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at));
    const total = items.length;
    const start = Math.max(0, (pageNum - 1) * limit);
    return delay(page(items.slice(start, start + limit), null, total));
  }

  if (method === 'GET' && path === '/api/tasks/summary') {
    const items: Task[] = mockStore.getAllTasks();
    const summary: TaskSummary = {
      today_tasks: items.length,
      today_success_rate: 95.8,
      today_cost_cny: 4.12,
      today_total_tokens: 287000,
      avg_elapsed_ms: 52000,
      status_counts: {
        running: items.filter((item) => item.status === 'running').length,
        queued: items.filter((item) => item.status === 'queued').length,
        done: items.filter((item) => item.status === 'done').length,
        failed: items.filter((item) => item.status === 'failed').length,
        canceled: items.filter((item) => item.status === 'canceled').length,
      },
      model_facets: [
        { value: 'qwen-turbo', count: items.length },
        { value: 'qwen-plus', count: items.length },
        { value: 'qwen3-asr-flash-filetrans', count: items.length },
      ],
    };
    summary.status_counts.active = summary.status_counts.running + summary.status_counts.queued;
    return delay(summary);
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

  const taskDetailMatch = match(path, /^\/api\/tasks\/([\w-]+)\/detail$/);
  if (method === 'GET' && taskDetailMatch) {
    const task = mockStore.getTask(taskDetailMatch[1]);
    if (!task) throw apiError('task_not_found', '任务不存在', 404);
    const detail: TaskDetail = {
      ...task,
      stage_runs: ['download', 'transcribe', 'correct', 'organize', 'save'].map((stage, index) => ({
        stage: stage as TaskDetail['stage_runs'][number]['stage'],
        status: index < ['download', 'transcribe', 'correct', 'organize', 'save'].indexOf(task.stage)
          ? 'done'
          : stage === task.stage
          ? task.status
          : 'queued',
        provider: stage === 'download' ? 'douyin' : stage === 'save' ? 'database' : 'dashscope',
        model:
          stage === 'transcribe'
            ? 'qwen3-asr-flash-filetrans'
            : stage === 'correct'
            ? 'qwen-turbo'
            : stage === 'organize'
            ? 'qwen-plus'
            : null,
        started_at: task.started_at,
        finished_at: task.finished_at,
        duration_ms: task.elapsed_ms,
        input_tokens: stage === 'organize' ? 11000 : 0,
        output_tokens: stage === 'organize' ? 1900 : 0,
        total_tokens: stage === 'organize' ? 12900 : 0,
        cost_cny: stage === 'organize' ? 0.0124 : 0,
        detail: task.detail,
        error: task.error,
      })),
      available_rerun_modes: { resume: true, organize: true, full: true },
    };
    return delay(detail);
  }

  if (method === 'POST' && path === '/api/tasks/rerun') {
    const payload = body as { task_ids?: string[]; mode?: 'resume' | 'organize' | 'full' } | undefined;
    const ids = payload?.task_ids ?? [];
    const created = ids.map((id) => mockStore.createTask(`https://www.douyin.com/video/rerun-${id}`));
    const res: TaskRerunResult = {
      requested: ids.length,
      processed: created.length,
      task_ids: created.map((task) => task.id),
      skipped_ids: [],
    };
    return delay(res);
  }

  if (method === 'POST' && path === '/api/tasks/cancel') {
    const ids = ((body as { task_ids?: string[] } | undefined)?.task_ids ?? []).filter(Boolean);
    ids.forEach((id) => mockStore.cancelTask(id));
    const res: TaskCancelResult = {
      requested: ids.length,
      processed: ids.length,
      skipped_ids: [],
    };
    return delay(res);
  }

  if (method === 'GET' && path === '/api/tasks/export') {
    return delay('任务 ID,状态,阶段,文章标题,创作者,触发方式,开始,结束,耗时(ms),tokens,成本(¥),错误信息\n');
  }

  if (method === 'POST' && path === '/api/system-jobs/creator_backfill/run') {
    const creatorId = Number(params.get('creator_id') ?? 0);
    const creator = creators.find((item) => item.id === creatorId) ?? creators[0];
    const now = new Date().toISOString();
    return delay({
      id: `sj_${Math.random().toString(36).slice(2, 8)}`,
      job_key: 'creator_backfill',
      job_name: '来源作品补齐',
      trigger_kind: 'manual',
      status: 'running',
      scope: `${creator.name} · 全量作品`,
      detail: '手动补齐来源作品',
      error: null,
      total_items: creator.video_count,
      processed_items: 0,
      failed_items: 0,
      skipped_items: 0,
      duration_ms: null,
      started_at: now,
      updated_at: now,
      finished_at: null,
    });
  }

  // Settings
  if (method === 'GET' && path === '/api/settings') return delay(settings);
  if (method === 'PATCH' && path === '/api/settings') {
    settings = deepMerge(settings, (body ?? {}) as Partial<Settings>);
    return delay(settings);
  }

  if (method === 'POST' && path === '/api/cookie') {
    let sourceName = 'cookies.txt';
    if (typeof FormData !== 'undefined' && body instanceof FormData) {
      const file = body.get('file');
      if (typeof File !== 'undefined' && file instanceof File) sourceName = file.name;
    }
    settings = deepMerge(settings, {
      cookie: { status: 'ok', source_name: sourceName, last_tested_at: settings.cookie.last_tested_at },
    });
    return delay({ status: 'ok', source_name: sourceName });
  }

  if (method === 'POST' && path === '/api/cookie/test') {
    if (settings.cookie.status === 'missing') {
      throw apiError('cookie_missing', '未导入 Cookie', 403);
    }
    settings = deepMerge(settings, {
      cookie: {
        status: 'ok',
        source_name: settings.cookie.source_name,
        last_tested_at: new Date().toISOString(),
      },
    });
    return delay({ status: 'ok', detail: '创作者主页抓取和视频读取都通过' });
  }

  if (method === 'GET' && path === '/api/models') {
    return delay(availableModels);
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
