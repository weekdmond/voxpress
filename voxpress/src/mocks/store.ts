import type { Task, TaskStage } from '@/types/api';
import type { TaskStreamEvent } from '@/lib/sse';
import { creators } from './fixtures/creators';

type Listener = (e: TaskStreamEvent) => void;

const STAGES: TaskStage[] = ['download', 'transcribe', 'correct', 'organize', 'save'];

function makeTask(partial: Partial<Task> & { id: string; source_url: string }): Task {
  const now = new Date().toISOString();
  return {
    id: partial.id,
    source_url: partial.source_url,
    title_guess: partial.title_guess ?? '新任务',
    creator_id: partial.creator_id ?? null,
    creator_name: partial.creator_name ?? null,
    creator_initial: partial.creator_initial ?? null,
    stage: partial.stage ?? 'download',
    status: partial.status ?? 'running',
    progress: partial.progress ?? 0,
    eta_sec: partial.eta_sec ?? 420,
    detail: partial.detail ?? null,
    article_id: null,
    article_title: partial.article_title ?? null,
    duration_sec: partial.duration_sec ?? 0,
    cover_url: partial.cover_url ?? null,
    error: null,
    trigger_kind: partial.trigger_kind ?? 'manual',
    rerun_of_task_id: partial.rerun_of_task_id ?? null,
    resume_from_stage: partial.resume_from_stage ?? null,
    primary_model: partial.primary_model ?? null,
    elapsed_ms: partial.elapsed_ms ?? null,
    input_tokens: partial.input_tokens ?? 0,
    output_tokens: partial.output_tokens ?? 0,
    total_tokens: partial.total_tokens ?? 0,
    cost_cny: partial.cost_cny ?? 0,
    started_at: now,
    updated_at: now,
    finished_at: null,
  };
}

class MockStore {
  private tasks = new Map<string, Task>();
  private listeners = new Set<Listener>();
  private tickTimer: number | null = null;

  constructor() {
    // Seed a few running tasks
    const seeds: Task[] = [
      makeTask({
        id: 't_01',
        source_url: 'https://www.douyin.com/video/7291234567890123456',
        title_guess: 'M5 Max 本地跑 Qwen2.5-72B 的真实吞吐',
        creator_id: 1,
        creator_name: '老钱说AI',
        creator_initial: '老',
        stage: 'transcribe',
        progress: 62,
        detail: 'DashScope qwen3-asr-flash-filetrans · 已转写 5:12 / 8:32',
        eta_sec: 272,
        primary_model: 'qwen3-asr-flash-filetrans',
        total_tokens: 0,
        cost_cny: 0.07,
      }),
      makeTask({
        id: 't_02',
        source_url: 'https://v.douyin.com/iABcDef/',
        title_guess: '一个产品经理的周五',
        creator_id: 2,
        creator_name: '武侯科技',
        creator_initial: '武',
        stage: 'organize',
        progress: 79,
        detail: 'DashScope qwen-plus · 第 2/7 段',
        eta_sec: 148,
        primary_model: 'qwen-plus',
        total_tokens: 12840,
        cost_cny: 0.0124,
      }),
      makeTask({
        id: 't_03',
        source_url: 'https://www.douyin.com/video/7298765432109876543',
        title_guess: '二次创业者最难承认的三件事',
        creator_id: 3,
        creator_name: '南瓜CEO',
        creator_initial: '南',
        stage: 'download',
        progress: 8,
        detail: 'Douyin Web API · 读取视频',
        eta_sec: 520,
        primary_model: 'qwen3-asr-flash-filetrans',
      }),
    ];
    seeds.forEach((t) => this.tasks.set(t.id, t));
    this.ensureTimer();
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    this.ensureTimer();
    return () => {
      this.listeners.delete(listener);
    };
  }

  getLiveTasks(): Task[] {
    return Array.from(this.tasks.values()).filter((t) => t.status !== 'done');
  }

  getAllTasks(): Task[] {
    return Array.from(this.tasks.values());
  }

  getTask(id: string): Task | undefined {
    return this.tasks.get(id);
  }

  createTask(url: string): Task {
    const id = `t_${Math.random().toString(36).slice(2, 8)}`;
    const c = creators[Math.floor(Math.random() * creators.length)];
    const task = makeTask({
      id,
      source_url: url,
      title_guess: '解析中…',
      creator_id: c.id,
      creator_name: c.name,
      creator_initial: c.initial,
      stage: 'download',
      status: 'queued',
      progress: 0,
      detail: '等待调度',
      eta_sec: 480,
      trigger_kind: 'manual',
    });
    this.tasks.set(id, task);
    this.broadcast({ type: 'create', task });
    this.ensureTimer();
    return task;
  }

  cancelTask(id: string): Task | null {
    const t = this.tasks.get(id);
    if (!t) return null;
    t.status = 'canceled';
    t.updated_at = new Date().toISOString();
    this.broadcast({ type: 'update', task: t });
    setTimeout(() => {
      this.tasks.delete(id);
      this.broadcast({ type: 'remove', task: { id } });
    }, 300);
    return t;
  }

  private broadcast(e: TaskStreamEvent) {
    this.listeners.forEach((l) => l(e));
  }

  private ensureTimer() {
    if (this.tickTimer != null) return;
    this.tickTimer = window.setInterval(() => this.tick(), 900);
  }

  private tick() {
    if (this.tasks.size === 0) return;
    for (const t of this.tasks.values()) {
      if (t.status !== 'running') continue;
      const delta = 2 + Math.floor(Math.random() * 6);
      t.progress = Math.min(100, t.progress + delta);
      t.eta_sec = Math.max(0, (t.eta_sec ?? 0) - 6);
      t.updated_at = new Date().toISOString();
      t.elapsed_ms = (t.elapsed_ms ?? 0) + 900;
      // stage advance heuristic
      const idx = STAGES.indexOf(t.stage);
      const stageWindow = 100 / STAGES.length;
      const expectedStage = Math.min(STAGES.length - 1, Math.floor(t.progress / stageWindow));
      if (expectedStage > idx) {
        t.stage = STAGES[expectedStage];
        t.detail = stageDetail(t.stage);
      }
      if (t.progress >= 100) {
        t.status = 'done';
        t.stage = 'save';
        t.finished_at = new Date().toISOString();
        t.article_id = `a_new_${t.id}`;
        t.article_title = t.title_guess;
        this.broadcast({ type: 'update', task: { ...t } });
        setTimeout(() => {
          this.tasks.delete(t.id);
          this.broadcast({ type: 'remove', task: { id: t.id } });
        }, 1000);
      } else {
        this.broadcast({ type: 'update', task: { ...t } });
      }
    }
  }
}

function stageDetail(stage: TaskStage): string {
  switch (stage) {
    case 'download':
      return 'Douyin Web API · 下载中';
    case 'transcribe':
      return 'DashScope qwen3-asr-flash-filetrans';
    case 'correct':
      return 'DashScope qwen-turbo · 纠错中';
    case 'organize':
      return 'DashScope qwen-plus · 整理中';
    case 'save':
      return '写入数据库';
  }
}

export const mockStore = new MockStore();
