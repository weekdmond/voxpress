import type { Settings } from '@/types/api';

export const defaultSettings: Settings = {
  llm: {
    backend: 'ollama',
    model: 'qwen2.5:72b',
    concurrency: 2,
  },
  whisper: {
    model: 'large-v3',
    language: 'zh',
  },
  prompt: {
    version: 'v1.0',
    template:
      '你是一位严谨的中文编辑。把下面这段口播转写整理成一篇结构化的文章,保留原作者的语气,消除口头禅和重复。',
  },
  cookie: {
    status: 'missing',
    last_tested_at: null,
    text: null,
  },
  storage: {
    audio_retain_days: 7,
    used_bytes: 824_000_000,
  },
};

export const availableModels = ['qwen2.5:72b', 'qwen2.5:32b', 'deepseek-r1:70b', 'llama3.1:70b'];
