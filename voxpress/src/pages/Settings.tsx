import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Page, PageHead } from '@/layouts/AppShell';
import { Box, Button, Chip, Divider, Field, Input, Row, Select, Textarea } from '@/components/primitives';
import { api } from '@/lib/api';
import type { Settings as SettingsT } from '@/types/api';

export function SettingsPage() {
  const qc = useQueryClient();
  const cookieInputRef = useRef<HTMLInputElement>(null);
  const [cookieFile, setCookieFile] = useState<File | null>(null);
  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.get<SettingsT>('/api/settings'),
  });
  const { data: models } = useQuery({
    queryKey: ['models'],
    queryFn: () => api.get<{ llm: string[]; corrector: string[]; transcribe: string[] }>('/api/models'),
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

  const testCookie = useMutation({
    mutationFn: async () => {
      if (cookieFile) {
        const form = new FormData();
        form.append('file', cookieFile);
        await api.postForm('/api/cookie', form);
      } else if (!settings?.cookie.source_name) {
        throw new Error('请先选择 cookies.txt 文件');
      }
      return api.post<{ status: string; detail?: string }>('/api/cookie/test');
    },
    onSuccess: (r) =>
      r.status === 'ok'
        ? toast.success(r.detail ? `Cookie 测试通过 · ${r.detail}` : 'Cookie 测试通过')
        : toast.error('Cookie 已过期'),
    onError: (err: Error) => toast.error(err.message || 'Cookie 测试失败'),
    onSettled: async () => {
      setCookieFile(null);
      if (cookieInputRef.current) cookieInputRef.current.value = '';
      await qc.invalidateQueries({ queryKey: ['settings'] });
    },
  });

  const [promptDraft, setPromptDraft] = useState('');
  const [correctorDraft, setCorrectorDraft] = useState('');
  const [dashscopeBaseUrlDraft, setDashscopeBaseUrlDraft] = useState('');
  const [dashscopeApiKeyDraft, setDashscopeApiKeyDraft] = useState('');
  useEffect(() => {
    if (!settings) return;
    setPromptDraft(settings.prompt.template);
    setCorrectorDraft(settings.corrector.template);
    setDashscopeBaseUrlDraft(settings.dashscope.base_url);
    setDashscopeApiKeyDraft('');
  }, [settings]);

  const exportSettings = () => {
    if (!settings) return;
    const payload = {
      exported_at: new Date().toISOString(),
      source: 'voxpress-settings',
      settings,
      available_models: models ?? null,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: 'application/json;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    const stamp = new Date().toISOString().replace(/[:]/g, '-').replace(/\.\d+Z$/, 'Z');
    link.href = url;
    link.download = `voxpress-settings-${stamp}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    toast.success('配置已导出为 JSON');
  };

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
  const dashscopeChip = settings.dashscope.configured ? (
    <Chip variant="ok">已配置</Chip>
  ) : (
    <Chip variant="warn">未配置</Chip>
  );
  const dashscopeDirty =
    dashscopeBaseUrlDraft !== settings.dashscope.base_url || dashscopeApiKeyDraft.trim().length > 0;
  const llmModelSuggestions = Array.from(new Set([settings.llm.model, ...(models?.llm ?? [])]));
  const whisperModelSuggestions = Array.from(new Set([settings.whisper.model, ...(models?.transcribe ?? [])]));
  const correctorModelSuggestions = Array.from(new Set([settings.corrector.model, ...(models?.corrector ?? [])]));

  const checkboxStyle = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 10,
    minHeight: 40,
    padding: '0 2px',
    fontSize: 13,
    color: 'var(--vp-ink)',
  } as const;

  return (
    <Page>
      <PageHead
        title="设置"
        meta={
          <>
            <span>VoxPress v0.4</span>
            <span>· DashScope 云端模式</span>
          </>
        }
      />

      <Box>
        <Row between>
          <div>
            <strong style={{ fontSize: 14 }}>配置导出</strong>
            <div style={{ color: 'var(--vp-ink-3)', fontSize: 11.5 }}>
              导出当前已保存的设置快照，格式为 JSON，便于分析和留档
            </div>
          </div>
          <Button variant="primary" onClick={exportSettings}>
            导出 JSON
          </Button>
        </Row>
      </Box>

      {/* LLM */}
      <Box>
        <Row between>
          <div>
            <strong style={{ fontSize: 14 }}>DashScope 连接</strong>
            <div style={{ color: 'var(--vp-ink-3)', fontSize: 11.5 }}>
              配置 API Key 和兼容接口 Base URL。已保存的密钥不会回显。
            </div>
          </div>
          {dashscopeChip}
        </Row>
        <Divider />
        <Field
          label="API Key"
          help={
            settings.dashscope.configured
              ? '当前已配置 DashScope 凭证；如需更换，输入新的 API Key 后保存'
              : '请输入 DashScope API Key，保存后写入后端 settings 表'
          }
        >
          <Input
            type="password"
            value={dashscopeApiKeyDraft}
            placeholder={settings.dashscope.configured ? '已配置，留空表示保持不变' : 'sk-...'}
            onChange={(e) => setDashscopeApiKeyDraft(e.target.value)}
            mono
          />
        </Field>
        <Field label="Base URL" help="默认使用 DashScope OpenAI 兼容接口地址">
          <Input
            value={dashscopeBaseUrlDraft}
            onChange={(e) => setDashscopeBaseUrlDraft(e.target.value)}
            placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1"
            mono
          />
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            <Button
              onClick={() => {
                setDashscopeBaseUrlDraft(settings.dashscope.base_url);
                setDashscopeApiKeyDraft('');
              }}
            >
              恢复当前
            </Button>
            <Button
              variant={dashscopeDirty ? 'primary' : 'default'}
              disabled={!dashscopeDirty || patch.isPending}
              onClick={() =>
                patch.mutate({
                  dashscope: {
                    base_url: dashscopeBaseUrlDraft.trim(),
                    ...(dashscopeApiKeyDraft.trim()
                      ? { api_key: dashscopeApiKeyDraft.trim() }
                      : {}),
                  },
                })
              }
            >
              保存
            </Button>
          </div>
        </Field>
      </Box>

      <Box>
        <Row between>
          <div>
            <strong style={{ fontSize: 14 }}>文章整理模型</strong>
            <div style={{ color: 'var(--vp-ink-3)', fontSize: 11.5 }}>
              通过 DashScope 兼容接口调用千问模型
            </div>
          </div>
          <Chip variant={settings.dashscope.configured ? 'ok' : 'warn'}>
            {settings.dashscope.configured ? 'DashScope · 已连接' : 'DashScope · 未配置'}
          </Chip>
        </Row>
        <Divider />
        <Field label="后端">
          <Select value={settings.llm.backend} disabled>
            <option value="dashscope">DashScope (阿里云百炼)</option>
          </Select>
        </Field>
        <Field label="模型" help="前端只提供推荐项选择；后端不会按白名单静默回退">
          <Select
            value={settings.llm.model}
            onChange={(e) =>
              patch.mutate({
                llm: {
                  ...settings.llm,
                  model: e.target.value,
                },
              })
            }
          >
            {llmModelSuggestions.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="并发数" help="同时发往 DashScope 的整理/纠错请求上限">
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
            <strong style={{ fontSize: 14 }}>Qwen ASR 转写</strong>
            <div style={{ color: 'var(--vp-ink-3)', fontSize: 11.5 }}>
              Qwen3-ASR-Flash-Filetrans · 云端异步文件转写
            </div>
          </div>
          <Chip variant={settings.dashscope.configured ? 'ok' : 'warn'}>
            {settings.dashscope.configured ? 'DashScope · 已连接' : 'DashScope · 未配置'}
          </Chip>
        </Row>
        <Divider />
        <Field label="模型" help="前端只显示推荐 ASR 模型；真实可用性以运行时报错为准">
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
            {whisperModelSuggestions.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
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
        <Field label="启用 initial_prompt" help="把视频标题和博主名注入 ASR corpus，提升专名和主题词命中率">
          <label style={checkboxStyle}>
            <input
              type="checkbox"
              checked={settings.whisper.enable_initial_prompt}
              onChange={(e) =>
                patch.mutate({
                  whisper: {
                    ...settings.whisper,
                    enable_initial_prompt: e.target.checked,
                  },
                })
              }
            />
            <span>{settings.whisper.enable_initial_prompt ? '已启用' : '已关闭'}</span>
          </label>
        </Field>
      </Box>

      {/* Corrector */}
      <Box>
        <Row between>
          <div>
            <strong style={{ fontSize: 14 }}>转写纠错</strong>
            <div style={{ color: 'var(--vp-ink-3)', fontSize: 11.5 }}>
              在转写与文章整理之间补一层中文 ASR 纠错
            </div>
          </div>
          <Chip variant={settings.corrector.enabled ? 'ok' : 'warn'}>
            {settings.corrector.enabled ? '已启用' : '已关闭'}
          </Chip>
        </Row>
        <Divider />
        <Field label="自动纠错" help="关闭后会直接用原始逐字稿进入整理阶段">
          <label style={checkboxStyle}>
            <input
              type="checkbox"
              checked={settings.corrector.enabled}
              onChange={(e) =>
                patch.mutate({
                  corrector: {
                    ...settings.corrector,
                    enabled: e.target.checked,
                  },
                })
              }
            />
            <span>{settings.corrector.enabled ? '自动运行 correct 阶段' : '跳过 correct 阶段'}</span>
          </label>
        </Field>
        <Field label="纠错模型" help="前端只显示推荐项；若后端服务不支持，会在调用时返回错误">
          <Select
            value={settings.corrector.model}
            onChange={(e) =>
              patch.mutate({
                corrector: {
                  ...settings.corrector,
                  model: e.target.value,
                },
              })
            }
          >
            {correctorModelSuggestions.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="纠错 Prompt" help="专注同音字、成语、专有名词修正，不负责重写全文">
          <Textarea value={correctorDraft} onChange={(e) => setCorrectorDraft(e.target.value)} rows={8} />
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            <Button onClick={() => setCorrectorDraft(settings.corrector.template)}>恢复当前</Button>
            <Button
              variant={correctorDraft === settings.corrector.template ? 'default' : 'primary'}
              disabled={correctorDraft === settings.corrector.template}
              onClick={() =>
                patch.mutate({
                  corrector: {
                    ...settings.corrector,
                    template: correctorDraft,
                  },
                })
              }
            >
              保存
            </Button>
          </div>
        </Field>
      </Box>

      {/* Organizer Prompt */}
      <Box>
        <Row between>
          <div>
            <strong style={{ fontSize: 14 }}>文章整理 Prompt</strong>
            <div style={{ color: 'var(--vp-ink-3)', fontSize: 11.5 }}>
              版本 {settings.prompt.version} · 作用于 organize 阶段
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

      {/* Article enhancement */}
      <Box>
        <Row between>
          <div>
            <strong style={{ fontSize: 14 }}>文章增强</strong>
            <div style={{ color: 'var(--vp-ink-3)', fontSize: 11.5 }}>
              对含有代称、隐语、背景简称的视频，补充可关闭的背景注
            </div>
          </div>
          <Chip variant={settings.article.generate_background_notes ? 'ok' : 'warn'}>
            {settings.article.generate_background_notes ? '生成背景注' : '不生成背景注'}
          </Chip>
        </Row>
        <Divider />
        <Field label="生成背景注" help="只追加到文章末尾，不替换正文原话">
          <label style={checkboxStyle}>
            <input
              type="checkbox"
              checked={settings.article.generate_background_notes}
              onChange={(e) =>
                patch.mutate({
                  article: {
                    ...settings.article,
                    generate_background_notes: e.target.checked,
                  },
                })
              }
            />
            <span>{settings.article.generate_background_notes ? '已启用' : '已关闭'}</span>
          </label>
        </Field>
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
          label="导入 cookies.txt"
          help={
            settings.cookie.last_tested_at
              ? `当前文件 ${settings.cookie.source_name ?? '已导入'} · 上次测试 ${new Date(settings.cookie.last_tested_at).toLocaleString('zh-CN')}`
              : settings.cookie.source_name
                ? `当前文件 ${settings.cookie.source_name} · 尚未测试`
                : '请上传当前 douyin.com 站点导出的 Netscape cookies.txt，不要用 Export All Cookies'
          }
        >
          <div style={{ display: 'grid', gap: 10 }}>
            <input
              ref={cookieInputRef}
              type="file"
              accept=".txt,text/plain"
              onChange={(e) => setCookieFile(e.target.files?.[0] ?? null)}
              style={{ display: 'none' }}
            />
            <div
              style={{
                minHeight: 44,
                display: 'flex',
                alignItems: 'center',
                padding: '0 12px',
                border: '1px dashed var(--vp-line)',
                borderRadius: 'var(--vp-radius)',
                background: 'var(--vp-soft)',
                color: 'var(--vp-ink-2)',
                fontFamily: 'var(--vp-font-mono)',
                fontSize: 12,
              }}
            >
              {cookieFile
                ? `已选择 ${cookieFile.name}`
                : settings.cookie.source_name
                  ? `当前已导入 ${settings.cookie.source_name}`
                  : '尚未选择 cookies.txt 文件'}
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Button onClick={() => cookieInputRef.current?.click()}>
                选择 cookies.txt
              </Button>
              <Button
                variant="primary"
                disabled={
                  testCookie.isPending ||
                  (!cookieFile && !settings.cookie.source_name)
                }
                onClick={() => testCookie.mutate()}
              >
                {testCookie.isPending ? '测试中…' : cookieFile ? '导入并测试' : '重新测试'}
              </Button>
            </div>
          </div>
        </Field>
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
