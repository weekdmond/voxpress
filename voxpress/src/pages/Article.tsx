import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useLocation, useParams } from 'react-router-dom';

type RebuildStage = 'auto' | 'download' | 'transcribe' | 'correct' | 'organize';
const REBUILD_STAGE_OPTIONS: { v: RebuildStage; label: string }[] = [
  { v: 'auto', label: '自动选择' },
  { v: 'download', label: '从下载开始' },
  { v: 'transcribe', label: '从转写开始' },
  { v: 'correct', label: '从校对开始' },
  { v: 'organize', label: '从整理开始' },
];
import { toast } from 'sonner';
import { Page } from '@/layouts/AppShell';
import { ClaudeShareDialog } from '@/components/ClaudeShare/ClaudeShareDialog';
import { TaskDrawer } from '@/components/Task/TaskDrawer';
import { Avatar, Button, Chip, ConfirmDialog, Icon } from '@/components/primitives';
import {
  BackgroundNotes,
  Drawer,
  Reader,
  ReaderArticle,
  ReaderBody,
  ReaderToolbar,
  SourceCard,
} from '@/components/Reader/Reader';
import { api, apiUrl } from '@/lib/api';
import {
  ARTICLE_PAGE_SIZE,
  buildArticleListApiParams,
  buildArticleListSearchParams,
  parseArticleListState,
} from '@/lib/articleList';
import { formatDuration } from '@/lib/format';
import type { Article, ArticleDetail, Page as ApiPage, Task, TaskCancelResult, TaskRerunResult } from '@/types/api';

export function ArticlePage() {
  const { id = '' } = useParams<{ id: string }>();
  const location = useLocation();
  const qc = useQueryClient();
  const [split, setSplit] = useState(true);
  const [fromStage, setFromStage] = useState<RebuildStage>('auto');
  const [taskDrawerId, setTaskDrawerId] = useState<string | null>(null);
  const [confirmRebuild, setConfirmRebuild] = useState(false);
  const [claudeShareOpen, setClaudeShareOpen] = useState(false);
  const hasListContext = location.search.length > 1;
  const listState = parseArticleListState(location.search);
  const listParams = buildArticleListApiParams(listState).toString();

  const { data, isLoading } = useQuery({
    queryKey: ['article', id],
    queryFn: () => api.get<ArticleDetail>(`/api/articles/${id}`),
  });

  const { data: listPage } = useQuery({
    queryKey: ['articles', listParams],
    queryFn: () => api.get<ApiPage<Article>>(`/api/articles?${listParams}`),
    enabled: hasListContext,
  });

  const navItems = listPage?.items ?? [];
  const currentIndex = navItems.findIndex((item) => item.id === id);
  const totalItems = listPage?.total ?? navItems.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / ARTICLE_PAGE_SIZE));
  const needsPrevPage = hasListContext && currentIndex === 0 && listState.page > 1;
  const needsNextPage =
    hasListContext &&
    currentIndex === navItems.length - 1 &&
    navItems.length > 0 &&
    listState.page < totalPages;

  const prevPageState = { ...listState, page: Math.max(1, listState.page - 1) };
  const nextPageState = { ...listState, page: listState.page + 1 };
  const prevPageParams = buildArticleListApiParams(prevPageState).toString();
  const nextPageParams = buildArticleListApiParams(nextPageState).toString();

  const { data: prevPage } = useQuery({
    queryKey: ['articles', prevPageParams],
    queryFn: () => api.get<ApiPage<Article>>(`/api/articles?${prevPageParams}`),
    enabled: needsPrevPage,
  });

  const { data: nextPage } = useQuery({
    queryKey: ['articles', nextPageParams],
    queryFn: () => api.get<ApiPage<Article>>(`/api/articles?${nextPageParams}`),
    enabled: needsNextPage,
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

  const rerunOne = useMutation({
    mutationFn: ({ taskId, mode }: { taskId: string; mode: 'resume' | 'organize' | 'full' }) =>
      api.post<TaskRerunResult>('/api/tasks/rerun', { task_ids: [taskId], mode }),
    onSuccess: (res) => {
      toast.success(`已创建 ${res.processed} 条重跑任务`);
      qc.invalidateQueries({ queryKey: ['tasks'] });
      qc.invalidateQueries({ queryKey: ['article', id] });
    },
    onError: (err: Error) => toast.error(err.message || '重跑失败'),
  });

  const cancelOne = useMutation({
    mutationFn: (taskId: string) => api.post<Task | TaskCancelResult>(`/api/tasks/${taskId}/cancel`),
    onSuccess: () => {
      toast.success('任务已取消');
      qc.invalidateQueries({ queryKey: ['tasks'] });
      qc.invalidateQueries({ queryKey: ['article', id] });
    },
    onError: (err: Error) => toast.error(err.message || '取消失败'),
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
  const prevArticle =
    currentIndex > 0
      ? navItems[currentIndex - 1]
      : prevPage?.items?.[prevPage.items.length - 1] ?? null;
  const nextArticle =
    currentIndex >= 0 && currentIndex < navItems.length - 1
      ? navItems[currentIndex + 1]
      : nextPage?.items?.[0] ?? null;
  const backToArticles = `/articles${location.search}`;
  const articleHref = (articleId: string, page: number) => {
    const search = buildArticleListSearchParams({ ...listState, page }).toString();
    return search ? `/articles/${articleId}?${search}` : `/articles/${articleId}`;
  };

  return (
    <Page>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          flexWrap: 'wrap',
          fontFamily: 'var(--vp-font-mono)',
          fontSize: 11.5,
          color: 'var(--vp-ink-3)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <Link to={backToArticles} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <Icon name="arrow-left" size={12} /> 文章列表
          </Link>
          <span>/</span>
          <span style={{ color: 'var(--vp-ink-2)' }}>{art.source.creator_snapshot.name}</span>
        </div>
        {hasListContext ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
            {prevArticle ? (
              <Link
                to={articleHref(prevArticle.id, currentIndex > 0 ? listState.page : listState.page - 1)}
                title={prevArticle.title}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  minWidth: 0,
                  maxWidth: 240,
                  padding: '6px 10px',
                  borderRadius: 999,
                  border: '1px solid var(--vp-line)',
                  color: 'var(--vp-ink-2)',
                  background: 'var(--vp-panel)',
                }}
              >
                <Icon name="arrow-left" size={12} />
                <span
                  style={{
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  上一篇
                </span>
              </Link>
            ) : null}
            {nextArticle ? (
              <Link
                to={articleHref(
                  nextArticle.id,
                  currentIndex >= 0 && currentIndex < navItems.length - 1
                    ? listState.page
                    : listState.page + 1,
                )}
                title={nextArticle.title}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  minWidth: 0,
                  maxWidth: 240,
                  padding: '6px 10px',
                  borderRadius: 999,
                  border: '1px solid var(--vp-line)',
                  color: 'var(--vp-ink-2)',
                  background: 'var(--vp-panel)',
                }}
              >
                <span
                  style={{
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  下一篇
                </span>
                <Icon name="arrow-right" size={12} />
              </Link>
            ) : null}
          </div>
        ) : null}
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
                  setConfirmRebuild(true);
                }}
                icon={<Icon name="refresh" size={12} />}
              >
                重新整理
              </Button>
              <Button
                size="sm"
                onClick={() => {
                  if (!art.latest_task_id) {
                    toast.error('暂无关联任务记录');
                    return;
                  }
                  setTaskDrawerId(art.latest_task_id);
                }}
                icon={<Icon name="chevron" size={12} />}
              >
                任务面板
              </Button>
              <Button
                size="sm"
                onClick={() => setClaudeShareOpen(true)}
                icon={<Icon name="sparkle" size={12} />}
              >
                发给 Claude
              </Button>
              <Button
                size="sm"
                onClick={() => window.open(apiUrl(`/api/articles/${art.id}/export.md`), '_blank')}
                icon={<Icon name="external" size={12} />}
              >
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

      {taskDrawerId ? (
        <TaskDrawer
          taskId={taskDrawerId}
          onClose={() => setTaskDrawerId(null)}
          onRerun={(taskId, mode) => rerunOne.mutate({ taskId, mode })}
          onCancel={(taskId) => cancelOne.mutate(taskId)}
        />
      ) : null}

      <ClaudeShareDialog
        open={claudeShareOpen}
        articleIds={[art.id]}
        onClose={() => setClaudeShareOpen(false)}
      />

      <ConfirmDialog
        open={confirmRebuild}
        title="确认重新整理这篇文章？"
        description="当前文章内容会被新的整理结果覆盖，原始逐字稿和任务记录会保留。"
        confirmLabel="确认重新整理"
        cancelLabel="取消"
        pending={rebuild.isPending}
        onCancel={() => setConfirmRebuild(false)}
        onConfirm={() => {
          rebuild.mutate(fromStage, {
            onSuccess: () => setConfirmRebuild(false),
            onError: () => setConfirmRebuild(false),
          });
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <span
            style={{
              fontSize: 11.5,
              color: 'var(--vp-ink-3)',
              fontFamily: 'var(--vp-font-mono)',
            }}
          >
            从哪个阶段开始
          </span>
          <select
            value={fromStage}
            onChange={(e) => setFromStage(e.target.value as RebuildStage)}
            disabled={rebuild.isPending}
            aria-label="重新整理起始阶段"
            style={{
              height: 34,
              padding: '0 30px 0 10px',
              borderRadius: 10,
              border: '1px solid var(--vp-border)',
              background: 'var(--vp-bg)',
              color: 'var(--vp-ink)',
              fontFamily: 'inherit',
              fontSize: 12.5,
              cursor: 'pointer',
              appearance: 'none',
              WebkitAppearance: 'none',
              backgroundImage:
                "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'><path d='M2 4l3 3 3-3' stroke='%236b7280' stroke-width='1.2' fill='none' stroke-linecap='round'/></svg>\")",
              backgroundRepeat: 'no-repeat',
              backgroundPosition: 'right 10px center',
            }}
          >
            {REBUILD_STAGE_OPTIONS.map((o) => (
              <option key={o.v} value={o.v}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </ConfirmDialog>
    </Page>
  );
}
