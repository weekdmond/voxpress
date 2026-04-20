import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Page, PageHead } from '@/layouts/AppShell';
import { Box, Button, Chip, Divider, Field, Row, Select, Textarea } from '@/components/primitives';
import { api } from '@/lib/api';
import type { Settings as SettingsT } from '@/types/api';

export function SettingsPage() {
  const qc = useQueryClient();
  const [cookieDraft, setCookieDraft] = useState('');
  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.get<SettingsT>('/api/settings'),
  });
  const { data: models } = useQuery({
    queryKey: ['models'],
    queryFn: () => api.get<{ ollama: string[] }>('/api/models'),
    staleTime: 5 * 60_000,
  });

  const patch = useMutation({
    mutationFn: (p: Partial<SettingsT>) => api.patch<SettingsT>('/api/settings', p),
    onSuccess: (s) => {
      qc.setQueryData(['settings'], s);
      toast.success('已保存');
    },
    onError: (err: Error) => toast.error(err.message || '保存失败'),
  });

  // One button = save-if-changed, then test. Empty draft with a stored cookie
  // still tests the stored one; empty draft with nothing stored errors as usual.
  const testCookie = useMutation({
    mutationFn: async () => {
      const draft = cookieDraft.trim();
      const stored = settings?.cookie.text ?? '';
      if (draft && draft !== stored) {
        await api.post('/api/cookie', { text: draft });
        await qc.invalidateQueries({ queryKey: ['settings'] });
      }
      return api.post<{ status: string }>('/api/cookie/test');
    },
    onSuccess: (r) =>
      r.status === 'ok' ? toast.success('Cookie 测试通过') : toast.error('Cookie 已过期'),
    onError: (err: Error) => toast.error(err.message || 'Cookie 测试失败'),
  });

  const [promptDraft, setPromptDraft] = useState('');
  useEffect(() => {
    if (settings) setPromptDraft(settings.prompt.template);
  }, [settings]);

  const cookieInited = useRef(false);
  useEffect(() => {
    // Populate the textarea with the stored cookie on first settings load.
    // After that the user owns the draft — we don't clobber their edits.
    if (settings && !cookieInited.current) {
      setCookieDraft(settings.cookie.text ?? '');
      cookieInited.current = true;
    }
  }, [settings]);

  if (!settings) {
    return (
      <Page>
        <div style={{ color: 'var(--vp-ink-3)' }}>加载中…</div>
      </Page>
    );
  }

  const cookieChip =
    settings.cookie.status === 'ok' ? (
      <Chip variant="ok">已连接</Chip>
    ) : settings.cookie.status === 'expired' ? (
      <Chip variant="warn">已过期</Chip>
    ) : (
      <Chip variant="warn">未导入</Chip>
    );

  return (
    <Page>
      <PageHead
        title="设置"
        meta={
          <>
            <span>VoxPress v0.4</span>
            <span>· 单机模式</span>
          </>
        }
      />

      {/* LLM 后端 */}
      <Box>
        <Row between>
          <div>
            <strong style={{ fontSize: 14 }}>LLM 后端</strong>
            <div style={{ color: 'var(--vp-ink-3)', fontSize: 11.5 }}>
              整理文章时使用的推理后端
            </div>
          </div>
          <Chip variant="ok">Ollama · 就绪</Chip>
        </Row>
        <Divider />
        <Field label="后端">
          <Select
            value={settings.llm.backend}
            onChange={(e) =>
              patch.mutate({ llm: { ...settings.llm, backend: e.target.value as 'ollama' | 'claude' } })
            }
          >
            <option value="ollama">Ollama (本地)</option>
            <option value="claude" disabled>
              Claude API (预留)
            </option>
          </Select>
        </Field>
        <Field label="模型" help="从 Ollama /api/tags 动态加载">
          <Select
            value={settings.llm.model}
            onChange={(e) => patch.mutate({ llm: { ...settings.llm, model: e.target.value } })}
          >
            {(models?.ollama ?? [settings.llm.model]).map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="并发数" help="同时整理的文章数量,M5 Max 推荐 1–2">
          <input
            type="number"
            min={1}
            max={20}
            value={settings.llm.concurrency}
            onChange={(e) =>
              patch.mutate({ llm: { ...settings.llm, concurrency: Number(e.target.value) || 1 } })
            }
            style={{
              width: 80,
              padding: '8px 10px',
              border: '1px solid var(--vp-line)',
              borderRadius: 'var(--vp-radius)',
              background: 'var(--vp-panel)',
              fontSize: 13,
            }}
          />
        </Field>
      </Box>

      {/* Whisper */}
      <Box>
        <Row between>
          <div>
            <strong style={{ fontSize: 14 }}>Whisper 转写</strong>
            <div style={{ color: 'var(--vp-ink-3)', fontSize: 11.5 }}>
              mlx-whisper · Apple Silicon 原生
            </div>
          </div>
          <Chip variant="ok">已就绪</Chip>
        </Row>
        <Divider />
        <Field label="模型">
          <Select
            value={settings.whisper.model}
            onChange={(e) =>
              patch.mutate({
                whisper: {
                  ...settings.whisper,
                  model: e.target.value as SettingsT['whisper']['model'],
                },
              })
            }
          >
            <option value="large-v3">large-v3(推荐)</option>
            <option value="medium">medium</option>
            <option value="small">small</option>
          </Select>
        </Field>
        <Field label="语言">
          <Select
            value={settings.whisper.language}
            onChange={(e) =>
              patch.mutate({
                whisper: {
                  ...settings.whisper,
                  language: e.target.value as SettingsT['whisper']['language'],
                },
              })
            }
          >
            <option value="zh">强制中文</option>
            <option value="auto">自动识别</option>
          </Select>
        </Field>
      </Box>

      {/* Prompt */}
      <Box>
        <Row between>
          <div>
            <strong style={{ fontSize: 14 }}>Prompt 模板</strong>
            <div style={{ color: 'var(--vp-ink-3)', fontSize: 11.5 }}>
              版本 {settings.prompt.version} · 作用于所有整理任务
            </div>
          </div>
          <Chip>{promptDraft === settings.prompt.template ? '已同步' : '未保存'}</Chip>
        </Row>
        <Divider />
        <Textarea
          value={promptDraft}
          onChange={(e) => setPromptDraft(e.target.value)}
          rows={6}
        />
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <Button onClick={() => setPromptDraft(settings.prompt.template)}>恢复默认</Button>
          <Button
            variant={promptDraft === settings.prompt.template ? 'default' : 'primary'}
            disabled={promptDraft === settings.prompt.template}
            onClick={() =>
              patch.mutate({ prompt: { ...settings.prompt, template: promptDraft } })
            }
          >
            保存
          </Button>
        </div>
      </Box>

      {/* Cookie */}
      <Box>
        <Row between>
          <div>
            <strong style={{ fontSize: 14 }}>抖音 Cookie</strong>
            <div style={{ color: 'var(--vp-ink-3)', fontSize: 11.5 }}>
              访问博主主页 / 下载视频需要
            </div>
          </div>
          {cookieChip}
        </Row>
        <Divider />
        <Field
          label="粘贴 Cookie"
          help={
            settings.cookie.last_tested_at
              ? `上次测试 ${new Date(settings.cookie.last_tested_at).toLocaleString('zh-CN')}`
              : '从浏览器 DevTools 复制 cookie 字符串'
          }
        >
          <Textarea
            placeholder="sessionid=xxx; passport_csrf_token=..."
            rows={3}
            value={cookieDraft}
            onChange={(e) => setCookieDraft(e.target.value)}
          />
        </Field>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button
            variant="primary"
            disabled={
              testCookie.isPending ||
              (!cookieDraft.trim() && !settings.cookie.text)
            }
            onClick={() => testCookie.mutate()}
          >
            {testCookie.isPending ? '测试中…' : '测试连接'}
          </Button>
        </div>
      </Box>

      {/* Storage */}
      <Box>
        <Row between>
          <div>
            <strong style={{ fontSize: 14 }}>存储</strong>
            <div style={{ color: 'var(--vp-ink-3)', fontSize: 11.5 }}>
              音频临时文件策略 · 已占用 {(settings.storage.used_bytes / 1_048_576).toFixed(0)} MB
            </div>
          </div>
          <Chip>数据库: Postgres 16</Chip>
        </Row>
        <Divider />
        <Field label="音频保留天数" help="0 = 处理后立即删除">
          <input
            type="number"
            min={0}
            max={365}
            value={settings.storage.audio_retain_days}
            onChange={(e) =>
              patch.mutate({
                storage: {
                  ...settings.storage,
                  audio_retain_days: Number(e.target.value) || 0,
                },
              })
            }
            style={{
              width: 80,
              padding: '8px 10px',
              border: '1px solid var(--vp-line)',
              borderRadius: 'var(--vp-radius)',
              background: 'var(--vp-panel)',
              fontSize: 13,
            }}
          />
        </Field>
      </Box>
    </Page>
  );
}
