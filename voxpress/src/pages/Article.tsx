import { useState } from 'react';
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

  const { data, isLoading } = useQuery({
    queryKey: ['article', id],
    queryFn: () => api.get<ArticleDetail>(`/api/articles/${id}`),
  });

  const rebuild = useMutation({
    mutationFn: () => api.post<{ task_id: string }>(`/api/articles/${id}/rebuild`),
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
              <Button
                size="sm"
                onClick={() => {
                  if (confirm('当前文章会被覆盖,确认重新整理?')) rebuild.mutate();
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
