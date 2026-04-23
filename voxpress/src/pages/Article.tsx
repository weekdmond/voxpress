import { useState } from 'react';

type RebuildStage = 'auto' | 'download' | 'transcribe' | 'correct' | 'organize';
const REBUILD_STAGE_OPTIONS: { v: RebuildStage; label: string }[] = [
  { v: 'auto', label: '自动' },
  { v: 'download', label: '从下载' },
  { v: 'transcribe', label: '从转写' },
  { v: 'correct', label: '从校对' },
  { v: 'organize', label: '从整理' },
];
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Page } from '@/layouts/AppShell';
import { Avatar, Button, Chip, Icon } from '@/components/primitives';
import {
  BackgroundNotes,
  Drawer,
  Reader,
  ReaderArticle,
  ReaderBody,
  ReaderToolbar,
  SourceCard,
} from '@/components/Reader/Reader';
import { api } from '@/lib/api';
import { formatDuration } from '@/lib/format';
import type { ArticleDetail } from '@/types/api';

export function ArticlePage() {
  const { id = '' } = useParams<{ id: string }>();
  const [split, setSplit] = useState(true);
  const [fromStage, setFromStage] = useState<RebuildStage>('auto');

  const { data, isLoading } = useQuery({
    queryKey: ['article', id],
    queryFn: () => api.get<ArticleDetail>(`/api/articles/${id}`),
  });

  const rebuild = useMutation({
    mutationFn: (stage: RebuildStage) =>
      api.post<{ task_id: string }>(
        `/api/articles/${id}/rebuild`,
        stage === 'auto' ? {} : { from_stage: stage },
      ),
    onSuccess: () => toast.success('已加入重新整理队列'),
    onError: (err: Error) => toast.error(err.message || '重新整理失败'),
  });

  if (isLoading || !data) {
    return (
      <Page>
        <div style={{ color: 'var(--vp-ink-3)', fontFamily: 'var(--vp-font-mono)', fontSize: 12 }}>
          加载中…
        </div>
      </Page>
    );
  }

  const art = data;

  return (
    <Page>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          fontFamily: 'var(--vp-font-mono)',
          fontSize: 11.5,
          color: 'var(--vp-ink-3)',
        }}
      >
        <Link to="/articles" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <Icon name="arrow-left" size={12} /> 文章列表
        </Link>
        <span>/</span>
        <span style={{ color: 'var(--vp-ink-2)' }}>{art.source.creator_snapshot.name}</span>
      </div>

      <Reader>
        <ReaderToolbar
          left={
            <>
              <Avatar
                size="md"
                id={art.creator_id}
                initial={art.source.creator_snapshot.name[0] ?? '?'}
                src={art.source.creator_snapshot.avatar_url}
              />
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 2,
                  minWidth: 0,
                }}
              >
                <span style={{ fontWeight: 600, fontSize: 13.5 }}>{art.source.creator_snapshot.name}</span>
                <span className="mono" style={{ fontSize: 10.5, color: 'var(--vp-ink-3)' }}>
                  {formatDuration(art.source.duration_sec)} · {art.word_count} 字 ·{' '}
                  {new Date(art.published_at).toLocaleDateString('zh-CN')}
                </span>
              </div>
            </>
          }
          right={
            <>
              <Button size="sm" variant={split ? 'primary' : 'default'} onClick={() => setSplit((v) => !v)} icon={<Icon name="swap" size={12} />}>
                {split ? '隐藏原稿' : '显示原稿'}
              </Button>
              <select
                value={fromStage}
                onChange={(e) => setFromStage(e.target.value as RebuildStage)}
                disabled={rebuild.isPending}
                aria-label="起始阶段"
                style={{
                  height: 26,
                  padding: '0 22px 0 8px',
                  borderRadius: 6,
                  border: '1px solid var(--vp-border)',
                  background: 'var(--vp-bg)',
                  color: 'var(--vp-ink)',
                  fontFamily: 'inherit',
                  fontSize: 11.5,
                  cursor: 'pointer',
                  appearance: 'none',
                  WebkitAppearance: 'none',
                  backgroundImage:
                    "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'><path d='M2 4l3 3 3-3' stroke='%236b7280' stroke-width='1.2' fill='none' stroke-linecap='round'/></svg>\")",
                  backgroundRepeat: 'no-repeat',
                  backgroundPosition: 'right 6px center',
                }}
              >
                {REBUILD_STAGE_OPTIONS.map((o) => (
                  <option key={o.v} value={o.v}>
                    {o.label}
                  </option>
                ))}
              </select>
              <Button
                size="sm"
                onClick={() => {
                  if (confirm('当前文章会被覆盖,确认重新整理?')) rebuild.mutate(fromStage);
                }}
                icon={<Icon name="refresh" size={12} />}
              >
                重新整理
              </Button>
              <Button size="sm" icon={<Icon name="external" size={12} />}>
                导出 .md
              </Button>
              <Button size="sm" icon={<Icon name="tag" size={12} />}>
                标签
              </Button>
            </>
          }
        />

        <ReaderBody split={split}>
          <ReaderArticle>
            <h1>{art.title}</h1>
            {art.summary ? <p className="sum">{art.summary}</p> : null}
            <SourceCard source={art.source} />
            <div dangerouslySetInnerHTML={{ __html: art.content_html }} />
            <BackgroundNotes notes={art.background_notes} />
            <div style={{ marginTop: 24, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {art.tags.map((t) => (
                <Chip key={t} variant="accent">
                  #{t}
                </Chip>
              ))}
            </div>
          </ReaderArticle>
          {split ? (
            <Drawer
              segments={art.segments}
              rawText={art.raw_text}
              correctedText={art.corrected_text}
              correctionStatus={art.correction_status}
              corrections={art.corrections}
              whisperModel={art.whisper_model}
              whisperLanguage={art.whisper_language}
              correctorModel={art.corrector_model}
              initialPromptUsed={art.initial_prompt_used}
            />
          ) : null}
        </ReaderBody>
      </Reader>
    </Page>
  );
}
