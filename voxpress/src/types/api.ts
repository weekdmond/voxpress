export type ISO8601 = string;
export type Platform = 'douyin';

export interface Page<T> {
  items: T[];
  cursor: string | null;
  total?: number;
}

export interface Creator {
  id: number;
  platform: Platform;
  handle: string;
  name: string;
  initial: string;
  bio: string | null;
  region: string | null;
  avatar_url?: string | null;
  verified: boolean;
  followers: number;
  total_likes: number;
  article_count: number;
  video_count: number;
  recent_update_at: ISO8601 | null;
  imported_at: ISO8601;
}

export interface Video {
  id: string;
  creator_id: number;
  title: string;
  duration_sec: number;
  likes: number;
  plays: number;
  comments: number;
  shares: number;
  collects: number;
  published_at: ISO8601;
  updated_at: ISO8601;
  cover_url: string | null;
  source_url: string;
  media_url: string | null;
  article_id: string | null;
}

export interface Article {
  id: string;
  video_id: string;
  creator_id: number;
  cover_url?: string | null;
  title: string;
  summary: string;
  content_md: string;
  content_html: string;
  word_count: number;
  tags: string[];
  background_notes?: BackgroundNotes | null;
  likes_snapshot: number;
  published_at: ISO8601;
  created_at: ISO8601;
  updated_at: ISO8601;
}

export interface ArticleBatchResult {
  requested: number;
  matched: number;
  processed: number;
  task_ids: string[];
  missing_ids: string[];
}

export interface BackgroundAlias {
  term: string;
  refers_to: string;
  confidence: 'high' | 'medium' | 'low';
}

export interface BackgroundNotes {
  aliases: BackgroundAlias[];
  context?: string;
}

export interface ArticleSource {
  platform: Platform;
  source_url: string;
  media_url?: string | null;
  duration_sec: number;
  metrics: {
    likes: number;
    comments: number;
    shares: number;
    collects: number;
    plays: number;
  };
  topics: string[];
  creator_snapshot: {
    name: string;
    handle: string;
    avatar_url?: string | null;
    followers: number;
    verified: boolean;
    region: string | null;
  };
}

export interface TranscriptSegment {
  ts_sec: number;
  text: string;
}

export interface ArticleDetail extends Article {
  source: ArticleSource;
  segments: TranscriptSegment[];
  raw_text: string | null;
  corrected_text: string | null;
  correction_status: 'pending' | 'ok' | 'skipped' | 'failed' | null;
  corrections: Array<{ from: string; to: string; reason: string }>;
  whisper_model?: string | null;
  whisper_language?: 'zh' | 'auto' | string | null;
  corrector_model?: string | null;
  initial_prompt_used?: string | null;
}

export type TaskStage = 'download' | 'transcribe' | 'correct' | 'organize' | 'save';
export type TaskStatus = 'queued' | 'running' | 'done' | 'failed' | 'canceled';
export type TaskTriggerKind = 'manual' | 'batch' | 'rerun';

export interface Task {
  id: string;
  source_url: string;
  title_guess: string;
  creator_id: number | null;
  creator_name: string | null;
  creator_initial: string | null;
  stage: TaskStage;
  status: TaskStatus;
  progress: number;
  eta_sec: number | null;
  detail: string | null;
  article_id: string | null;
  article_title: string | null;
  cover_url: string | null;
  error: string | null;
  trigger_kind: TaskTriggerKind;
  rerun_of_task_id: string | null;
  resume_from_stage: TaskStage | null;
  primary_model: string | null;
  elapsed_ms: number | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_cny: number;
  started_at: ISO8601;
  updated_at: ISO8601;
  finished_at: ISO8601 | null;
}

export interface TaskStageRun {
  stage: TaskStage;
  status: TaskStatus | 'skipped';
  provider: string | null;
  model: string | null;
  started_at: ISO8601 | null;
  finished_at: ISO8601 | null;
  duration_ms: number | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_cny: number;
  detail: string | null;
  error: string | null;
}

export interface TaskDetail extends Task {
  stage_runs: TaskStageRun[];
  available_rerun_modes: {
    resume?: boolean;
    organize?: boolean;
    full?: boolean;
  };
}

export interface TaskFacetItem {
  value: string;
  count: number;
}

export interface TaskSummary {
  today_tasks: number;
  today_success_rate: number;
  today_cost_cny: number;
  today_total_tokens: number;
  avg_elapsed_ms: number;
  status_counts: Record<string, number>;
  model_facets: TaskFacetItem[];
}

export interface TaskRerunResult {
  requested: number;
  processed: number;
  task_ids: string[];
  skipped_ids: string[];
}

export interface TaskCancelResult {
  requested: number;
  processed: number;
  skipped_ids: string[];
}

export interface Settings {
  llm: {
    backend: 'dashscope';
    model: string;
    concurrency: number;
  };
  whisper: {
    model: 'qwen3-asr-flash-filetrans';
    language: 'zh' | 'auto';
    enable_initial_prompt: boolean;
  };
  corrector: {
    enabled: boolean;
    model: string;
    template: string;
  };
  article: {
    generate_background_notes: boolean;
  };
  prompt: {
    version: string;
    template: string;
  };
  cookie: {
    status: 'missing' | 'ok' | 'expired';
    last_tested_at: ISO8601 | null;
    source_name: string | null;
  };
  storage: {
    audio_retain_days: number;
    used_bytes: number;
  };
}
