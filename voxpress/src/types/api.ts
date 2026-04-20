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
  cover_url: string | null;
  source_url: string;
  article_id: string | null;
}

export interface Article {
  id: string;
  video_id: string;
  creator_id: number;
  title: string;
  summary: string;
  content_md: string;
  content_html: string;
  word_count: number;
  tags: string[];
  likes_snapshot: number;
  published_at: ISO8601;
  created_at: ISO8601;
  updated_at: ISO8601;
}

export interface ArticleSource {
  platform: Platform;
  source_url: string;
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
}

export type TaskStage = 'download' | 'transcribe' | 'organize' | 'save';
export type TaskStatus = 'queued' | 'running' | 'done' | 'failed' | 'canceled';

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
  error: string | null;
  started_at: ISO8601;
  updated_at: ISO8601;
  finished_at: ISO8601 | null;
}

export interface Settings {
  llm: {
    backend: 'ollama' | 'claude';
    model: string;
    concurrency: number;
  };
  whisper: {
    model: 'large-v3' | 'medium' | 'small';
    language: 'zh' | 'auto';
  };
  prompt: {
    version: string;
    template: string;
  };
  cookie: {
    status: 'missing' | 'ok' | 'expired';
    last_tested_at: ISO8601 | null;
    text: string | null;
  };
  storage: {
    audio_retain_days: number;
    used_bytes: number;
  };
}
