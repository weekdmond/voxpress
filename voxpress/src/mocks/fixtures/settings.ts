import type { Settings } from '@/types/api';

export const defaultSettings: Settings = {
  llm: {
    backend: 'dashscope',
    model: 'qwen3.6-plus',
    concurrency: 4,
  },
  whisper: {
    model: 'qwen3-asr-flash-filetrans',
    language: 'zh',
    enable_initial_prompt: true,
  },
  corrector: {
    enabled: true,
    model: 'qwen-turbo-latest',
    template:
      '你是中文语音转写校对员，只修正明显的同音字和专有名词错误，不做润色。',
  },
  article: {
    generate_background_notes: true,
  },
  prompt: {
    version: 'v1.0',
    template:
      '你是一位严谨的中文编辑。把下面这段口播转写整理成一篇结构化的文章,保留原作者的语气,消除口头禅和重复。',
  },
  cookie: {
    status: 'missing',
    last_tested_at: null,
    source_name: null,
  },
  storage: {
    audio_retain_days: 7,
    used_bytes: 824_000_000,
  },
};

export const availableModels = {
  llm: ['qwen3.6-plus', 'qwen-plus', 'qwen-plus-latest', 'qwen-turbo', 'qwen-flash'],
  corrector: ['qwen-turbo-latest', 'qwen-turbo', 'qwen-flash', 'qwen3.6-plus', 'qwen-plus'],
  transcribe: ['qwen3-asr-flash-filetrans'],
};
