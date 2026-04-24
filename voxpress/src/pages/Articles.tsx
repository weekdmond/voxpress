import { useCallback, useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Page, PageHead } from '@/layouts/AppShell';
import { ClaudeShareDialog } from '@/components/ClaudeShare/ClaudeShareDialog';
import { TaskDrawer } from '@/components/Task/TaskDrawer';
import { useCrossPageSelection } from '@/hooks/useCrossPageSelection';
import { Avatar, ConfirmDialog, Icon } from '@/components/primitives';
import { api, apiUrl } from '@/lib/api';
import {
  ARTICLE_PAGE_SIZE,
  ARTICLE_SORT_OPTIONS,
  ARTICLE_TIME_OPTIONS,
  DEFAULT_ARTICLE_LIST_STATE,
  buildArticleListApiParams,
  buildArticleListSearchParams,
  parseArticleListState,
} from '@/lib/articleList';
import { thumbGradient } from '@/lib/gradients';
import { mediaCandidates } from '@/lib/media';
import { formatCount, formatDateTime, formatDuration } from '@/lib/format';
import type {
  Article,
  Creator,
  Page as ApiPage,
  Task,
  TaskCancelResult,
  TaskRerunResult,
} from '@/types/api';
import s from './Articles.module.css';

type RebuildStage = 'auto' | 'download' | 'transcribe' | 'correct' | 'organize';

const REBUILD_STAGE_OPTIONS: { v: RebuildStage; label: string }[] = [
  { v: 'auto', label: '自动(有缓存从转写,否则从下载)' },
  { v: 'download', label: '从下载开始' },
  { v: 'transcribe', label: '从转写开始' },
  { v: 'correct', label: '从校对开始' },
  { v: 'organize', label: '从整理开始' },
];

function labelFromTitle(title: string): string {
  const clean = title.replace(/[#《》「」"'"'，。、！？,.:;]/g, '').trim();
  const m = clean.match(/[\u4e00-\u9fffA-Z0-9]{1,3}/);
  return m ? m[0] : 'A';
}

function buildPageNumbers(current: number, total: number): (number | '...')[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const out: (number | '...')[] = [1];
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  if (start > 2) out.push('...');
  for (let i = start; i <= end; i++) out.push(i);
  if (end < total - 1) out.push('...');
  out.push(total);
  return out;
}

function ArticleCover({
  seed,
  label,
  src,
}: {
  seed: number;
  label: string;
  src?: string | null;
}) {
  const [attempt, setAttempt] = useState(0);
  useEffect(() => setAttempt(0), [src]);
  const candidates = mediaCandidates(src ?? null);
  const resolved = candidates[attempt];
  return (
    <div className={s.cover} style={{ background: thumbGradient(seed) }} aria-hidden>
      {resolved ? (
        <img
          src={resolved}
          alt=""
          referrerPolicy="no-referrer"
          onError={() => setAttempt((v) => v + 1)}
        />
      ) : null}
      <span className={s.coverLabel}>{label}</span>
    </div>
  );
}

interface DropdownProps<T extends string> {
  id: string;
  k: string;
  value: T;
  options: { v: T; label: string; count?: number }[];
  openId: string | null;
  setOpenId: (v: string | null) => void;
  onSelect: (v: T) => void;
  headerLabel?: string;
}

function Dropdown<T extends string>({
  id,
  k,
  value,
  options,
  openId,
  setOpenId,
  onSelect,
  headerLabel,
}: DropdownProps<T>) {
  const open = openId === id;
  const isEmpty = value === ('all' as T);
  const curr = options.find((o) => o.v === value) ?? options[0];
  return (
    <div className={[s.drop, isEmpty ? s.dropEmpty : ''].join(' ')}>
      <button
        className={s.dropBtn}
        onClick={(e) => {
          e.stopPropagation();
          setOpenId(open ? null : id);
        }}
      >
        <span className={s.dropKey}>{k}</span>
        <span className={s.dropVal}>{curr.label}</span>
        <span className={s.dropCaret}>▾</span>
      </button>
      {open ? (
        <div className={s.dropMenu} onClick={(e) => e.stopPropagation()}>
          {headerLabel ? <div className={s.dropHead}>{headerLabel}</div> : null}
          {options.map((o) => (
            <div
              key={o.v}
              className={[s.dropItem, o.v === value ? s.dropItemOn : ''].join(' ')}
              onClick={() => {
                onSelect(o.v);
                setOpenId(null);
              }}
            >
              <span>{o.label}</span>
              {o.count != null ? <span className={s.dropItemCount}>{o.count}</span> : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function ArticlesPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const qc = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const listState = useMemo(() => parseArticleListState(searchParams), [searchParams]);
  const { creatorFilter, time, tagFilter, sort, q, page } = listState;
  const [qDraft, setQDraft] = useState(q);
  const [openDrop, setOpenDrop] = useState<string | null>(null);
  const [rebuildStage, setRebuildStage] = useState<RebuildStage>('auto');
  const [taskDrawerId, setTaskDrawerId] = useState<string | null>(null);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [claudeShareOpen, setClaudeShareOpen] = useState(false);

  useEffect(() => {
    setQDraft(q);
  }, [q]);

  useEffect(() => {
    if (!openDrop) return;
    const onDoc = () => setOpenDrop(null);
    document.addEventListener('click', onDoc);
    return () => document.removeEventListener('click', onDoc);
  }, [openDrop]);

  const updateListState = useCallback(
    (patch: Partial<typeof listState>, options?: { resetPage?: boolean }) => {
      setSearchParams(
        (current) => {
          const currentState = parseArticleListState(current);
          const next = {
            ...currentState,
            ...patch,
            page: options?.resetPage ? 1 : (patch.page ?? currentState.page),
          };
          return buildArticleListSearchParams(next);
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  useEffect(() => {
    const id = window.setTimeout(() => {
      const nextQ = qDraft.trim();
      if (nextQ !== q) {
        updateListState({ q: nextQ }, { resetPage: true });
      }
    }, 250);
    return () => window.clearTimeout(id);
  }, [qDraft, q, updateListState]);

  const listParams = useMemo(() => {
    return buildArticleListApiParams(listState).toString();
  }, [listState]);

  const { data: listPage } = useQuery({
    queryKey: ['articles', listParams],
    queryFn: () => api.get<ApiPage<Article>>(`/api/articles?${listParams}`),
  });

  const { data: creatorsPage } = useQuery({
    queryKey: ['creators', 'map'],
    queryFn: () => api.get<ApiPage<Creator>>('/api/creators'),
    staleTime: 60_000,
  });
  const creatorMap = useMemo(() => {
    const map = new Map<number, Creator>();
    creatorsPage?.items.forEach((c) => map.set(c.id, c));
    return map;
  }, [creatorsPage]);

  const articles = listPage?.items ?? [];
  const listTotal = listPage?.total ?? articles.length;
  const totalPages = Math.max(1, Math.ceil(listTotal / ARTICLE_PAGE_SIZE));
  const selectionScope = useMemo(
    () => JSON.stringify({ creatorFilter, time, tagFilter, q, sort }),
    [creatorFilter, time, tagFilter, q, sort],
  );
  const selection = useCrossPageSelection(selectionScope, articles);

  const tagFacets = useMemo(() => {
    const counts = new Map<string, number>();
    articles.forEach((a) => a.tags.forEach((t) => counts.set(t, (counts.get(t) ?? 0) + 1)));
    return Array.from(counts.entries())
      .sort(([, a], [, b]) => b - a)
      .slice(0, 12);
  }, [articles]);

  const rebuildMut = useMutation({
    mutationFn: async ({ ids, fromStage }: { ids: string[]; fromStage: RebuildStage }) => {
      const body = fromStage === 'auto' ? {} : { from_stage: fromStage };
      const res = await api.post<{ requested: number; matched: number; processed: number }>(
        `/api/articles/batch/rebuild`,
        { article_ids: ids, ...body },
      );
      return res.processed ?? ids.length;
    },
    onSuccess: (n) => {
      toast.success(`已加入重新整理队列 · ${n} 篇`);
      selection.clearSelection();
      qc.invalidateQueries({ queryKey: ['articles'] });
      qc.invalidateQueries({ queryKey: ['tasks'] });
    },
    onError: (e: Error) => toast.error(e.message || '提交失败'),
  });

  const deleteMut = useMutation({
    mutationFn: async (ids: string[]) => {
      const results = await Promise.all(
        ids.map((id) =>
          api
            .del(`/api/articles/${id}`)
            .then(() => true)
            .catch(() => false),
        ),
      );
      return results.filter(Boolean).length;
    },
    onSuccess: (n) => {
      toast.success(`已删除 ${n} 篇`);
      selection.clearSelection();
      qc.invalidateQueries({ queryKey: ['articles'] });
    },
    onError: (e: Error) => toast.error(e.message || '删除失败'),
  });

  const rerunOne = useMutation({
    mutationFn: ({ id, mode }: { id: string; mode: 'resume' | 'organize' | 'full' }) =>
      api.post<TaskRerunResult>('/api/tasks/rerun', { task_ids: [id], mode }),
    onSuccess: (res) => {
      toast.success(`已创建 ${res.processed} 条重跑任务`);
      qc.invalidateQueries({ queryKey: ['tasks'] });
      qc.invalidateQueries({ queryKey: ['articles'] });
    },
    onError: (e: Error) => toast.error(e.message || '重跑失败'),
  });

  const cancelOne = useMutation({
    mutationFn: (id: string) => api.post<Task | TaskCancelResult>(`/api/tasks/${id}/cancel`),
    onSuccess: () => {
      toast.success('任务已取消');
      qc.invalidateQueries({ queryKey: ['tasks'] });
      qc.invalidateQueries({ queryKey: ['articles'] });
    },
    onError: (e: Error) => toast.error(e.message || '取消失败'),
  });

  const exportOne = (id: string) => {
    window.open(apiUrl(`/api/articles/${id}/export.md`), '_blank');
  };

  const allCbxCls = !selection.someOnPageSelected
    ? s.cbx
    : selection.allOnPageSelected
    ? [s.cbx, s.cbxOn].join(' ')
    : [s.cbx, s.cbxIndet].join(' ');

  const clearAll = () => {
    setSearchParams(buildArticleListSearchParams(DEFAULT_ARTICLE_LIST_STATE), { replace: true });
    setQDraft('');
  };

  const pageHref = (targetPage: number) => {
    const params = buildArticleListSearchParams({ ...listState, page: targetPage }).toString();
    return params ? `/articles?${params}` : '/articles';
  };

  const currentSortLabel = ARTICLE_SORT_OPTIONS.find((o) => o.v === sort)?.label ?? '发布时间';

  const creatorLabel =
    creatorFilter === 'all'
      ? '全部'
      : creatorMap.get(Number(creatorFilter))?.name ?? `#${creatorFilter}`;
  const activeFilters: { k: string; label: string; reset: () => void }[] = [
    ...(creatorFilter !== 'all'
      ? [
          {
            k: '创作者',
            label: creatorLabel,
            reset: () => updateListState({ creatorFilter: 'all' }, { resetPage: true }),
          },
        ]
      : []),
    ...(time !== 'all'
      ? [
          {
            k: '时间',
            label: ARTICLE_TIME_OPTIONS.find((o) => o.v === time)!.label,
            reset: () => updateListState({ time: 'all' }, { resetPage: true }),
          },
        ]
      : []),
    ...(tagFilter !== 'all'
      ? [{ k: '标签', label: `#${tagFilter}`, reset: () => updateListState({ tagFilter: 'all' }, { resetPage: true }) }]
      : []),
  ];

  const creatorOptions = useMemo(() => {
    const opts: { v: string; label: string; count?: number }[] = [
      { v: 'all', label: '全部', count: listTotal },
    ];
    creatorsPage?.items.forEach((c) => {
      opts.push({ v: String(c.id), label: c.name, count: c.article_count });
    });
    return opts;
  }, [creatorsPage, listTotal]);

  const tagOptions = useMemo(() => {
    const opts: { v: string; label: string; count?: number }[] = [
      { v: 'all', label: '全部', count: listTotal },
    ];
    tagFacets.forEach(([t, c]) => opts.push({ v: t, label: `#${t}`, count: c }));
    return opts;
  }, [tagFacets, listTotal]);

  const selCount = selection.selectedCount;
  const selectedIds = selection.selectedIds;

  return (
    <Page>
      <PageHead
        title="文章列表"
        meta={
          <>
            <span>{listTotal} 篇已整理</span>
            <span>· 支持按创作者、标签、时间筛选</span>
          </>
        }
      />

      <div className={s.filterBar}>
        <span className={s.fbLabel}>筛选</span>
        <Dropdown
          id="author"
          k="创作者"
          value={creatorFilter}
          options={creatorOptions}
          openId={openDrop}
          setOpenId={setOpenDrop}
          onSelect={(value) => updateListState({ creatorFilter: value }, { resetPage: true })}
        />
        <Dropdown
          id="time"
          k="时间"
          value={time}
          options={ARTICLE_TIME_OPTIONS.map((o) => ({ v: o.v, label: o.label }))}
          openId={openDrop}
          setOpenId={setOpenDrop}
          onSelect={(value) => updateListState({ time: value }, { resetPage: true })}
        />
        <Dropdown
          id="tag"
          k="标签"
          value={tagFilter}
          options={tagOptions}
          openId={openDrop}
          setOpenId={setOpenDrop}
          onSelect={(value) => updateListState({ tagFilter: value }, { resetPage: true })}
          headerLabel={tagFacets.length ? '高频标签' : undefined}
        />
        <Dropdown
          id="sort"
          k="排序"
          value={sort}
          options={ARTICLE_SORT_OPTIONS}
          openId={openDrop}
          setOpenId={setOpenDrop}
          onSelect={(value) => updateListState({ sort: value }, { resetPage: true })}
        />
        <div className={s.fbDivider} />
        <div className={s.search}>
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
          <input
            placeholder="搜索标题、摘要或正文关键词…"
            value={qDraft}
            onChange={(e) => setQDraft(e.target.value)}
          />
        </div>
        <span className={s.fbSpacer} />
        <button className={[s.btn, s.btnGhost].join(' ')} onClick={clearAll}>
          重置
        </button>
      </div>

      {activeFilters.length > 0 ? (
        <div className={s.activeStrip}>
          <span className={s.activeLbl}>已选</span>
          {activeFilters.map((f) => (
            <span key={f.k} className={s.activePill}>
              {f.k}:{f.label}
              <button onClick={f.reset} aria-label={`移除${f.k}`}>
                ×
              </button>
            </span>
          ))}
          <button className={s.activeClear} onClick={clearAll}>
            清除全部
          </button>
        </div>
      ) : null}

      <div className={s.listHead}>
        <h2>
          全部文章
          <span className={s.listHeadMeta} style={{ marginLeft: 6 }}>
            {listTotal.toLocaleString()} 篇
          </span>
        </h2>
        <span className={s.listHeadMeta}>
          按{currentSortLabel}倒序 · 第 {page} 页 / 共 {totalPages} 页
        </span>
      </div>

      <div className={s.table}>
        <div className={s.tableScroll}>
          <div className={s.tHead}>
            <span>
              <button className={allCbxCls} onClick={selection.toggleAllOnPage} aria-label="全选" />
            </span>
            <span>文章</span>
            <span>博主</span>
            <span>标签</span>
            <span>指标</span>
            <span>时间</span>
            <span />
          </div>
          {articles.length === 0 ? (
            <div className={s.emptyBlock}>暂无文章 · 从首页提交第一条链接 →</div>
          ) : (
            articles.map((a, i) => {
              const c = creatorMap.get(a.creator_id);
                const isSel = selection.isSelected(a.id);
                return (
                <div
                  key={a.id}
                  className={[s.tRow, isSel ? s.tRowSelected : ''].join(' ')}
                  onClick={(e) => {
                    const tgt = e.target as HTMLElement;
                    if (tgt.closest('button')) return;
                    navigate({
                      pathname: `/articles/${a.id}`,
                      search: location.search,
                    });
                  }}
                >
                  <span>
                    <button
                        className={[s.cbx, isSel ? s.cbxOn : ''].join(' ')}
                        onClick={(e) => {
                          e.stopPropagation();
                          selection.toggleOne(a);
                        }}
                        aria-label="选择"
                      />
                  </span>
                  <div className={s.artCell}>
                    <ArticleCover
                      seed={a.creator_id + i}
                      label={labelFromTitle(a.title)}
                      src={a.cover_url}
                    />
                    <div className={s.artText}>
                      <span className={s.artTitle}>{a.title}</span>
                      <span className={s.artDesc}>{a.summary || '—'}</span>
                    </div>
                  </div>
                  <div className={s.author}>
                    {c ? (
                      <Avatar size="sm" id={c.id} initial={c.initial} src={c.avatar_url} />
                    ) : null}
                    <div className={s.authorText}>
                      <span className={s.authorName}>{c?.name ?? '—'}</span>
                      <span className={s.authorHandle}>{c?.handle ?? ''}</span>
                    </div>
                  </div>
                  <div className={s.tags}>
                    {a.tags.slice(0, 2).map((t) => (
                      <span key={t} className={s.tag}>
                        #{t}
                      </span>
                    ))}
                    {a.tags.length > 2 ? (
                      <span className={s.tagMore}>+{a.tags.length - 2}</span>
                    ) : null}
                  </div>
                  <div className={s.metricsCell}>
                    <span className={s.metric} title="视频时长">
                      <Icon name="clock" size={11} />
                      {a.duration_sec ? formatDuration(a.duration_sec) : '—'}
                    </span>
                    <span className={s.metric} title="字数">
                      <Icon name="doc" size={11} />
                      {a.word_count.toLocaleString()}
                    </span>
                    <span className={s.metric} title="生成成本">
                      <span className={s.yuan}>¥</span>
                      {(a.cost_cny ?? 0).toFixed(3)}
                    </span>
                    <span className={s.metric} title="点赞数">
                      <Icon name="heart" size={11} />
                      {formatCount(a.likes_snapshot)}
                    </span>
                  </div>
                  <div
                    className={s.timeCell}
                    title={`发布 ${formatDateTime(a.published_at)}\n更新 ${formatDateTime(a.updated_at)}`}
                  >
                    <span className={s.timeLine}>
                      <span className={s.timeLabel}>发</span>
                      <span className={s.dateCell}>{formatDateTime(a.published_at)}</span>
                    </span>
                    <span className={s.timeLine}>
                      <span className={s.timeLabel}>更</span>
                      <span className={s.dateCell}>{formatDateTime(a.updated_at)}</span>
                    </span>
                  </div>
                  <button
                    className={s.rowAct}
                    title="查看任务"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (!a.latest_task_id) {
                        toast.error('暂无关联任务记录');
                        return;
                      }
                      setTaskDrawerId(a.latest_task_id);
                    }}
                  >
                    <Icon name="chevron" size={13} />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>

      {totalPages > 1 ? (
        <div className={s.pager}>
          <span>
            共 {totalPages} 页 · 每页 {ARTICLE_PAGE_SIZE} 条
          </span>
          <div className={s.pagerBtns}>
            {page <= 1 ? (
              <span className={s.pagerDisabled}>‹</span>
            ) : (
              <Link to={pageHref(page - 1)}>‹</Link>
            )}
            {buildPageNumbers(page, totalPages).map((p, i) =>
              p === '...' ? (
                <span key={`e${i}`} className={s.pagerDisabled}>
                  …
                </span>
              ) : (
                <Link
                  key={p}
                  className={p === page ? s.pagerBtnOn : undefined}
                  to={pageHref(p)}
                  aria-current={p === page ? 'page' : undefined}
                >
                  {p}
                </Link>
              ),
            )}
            {page >= totalPages ? (
              <span className={s.pagerDisabled}>›</span>
            ) : (
              <Link to={pageHref(page + 1)}>›</Link>
            )}
          </div>
        </div>
      ) : null}

      {selCount > 0 ? (
        <div className={s.stickyBar}>
          <span className={s.stickyCount}>
            <b>{selCount}</b>篇已选中 · 当前页 {selection.pageSelectedCount}
          </span>
          <span className={s.stickySpacer} />
          <button className={s.stickyGhost} onClick={selection.clearSelection}>
            取消选择
          </button>
          <select
            className={s.stickySelect}
            value={rebuildStage}
            onChange={(e) => setRebuildStage(e.target.value as RebuildStage)}
            disabled={rebuildMut.isPending}
            aria-label="起始阶段"
          >
            {REBUILD_STAGE_OPTIONS.map((o) => (
              <option key={o.v} value={o.v}>
                {o.label}
              </option>
            ))}
          </select>
          <button
            className={s.stickyGhost}
            onClick={() => rebuildMut.mutate({ ids: selectedIds, fromStage: rebuildStage })}
            disabled={rebuildMut.isPending}
          >
            重新整理
          </button>
          <button
            className={[s.stickyGhost, s.stickyDanger].join(' ')}
            onClick={() => {
              setConfirmDeleteOpen(true);
            }}
            disabled={deleteMut.isPending}
          >
            删除
          </button>
          <button className={s.stickyGhost} onClick={() => setClaudeShareOpen(true)}>
            发给 Claude
          </button>
          <button
            className={s.stickyPrimary}
            onClick={() => selectedIds.forEach((id) => exportOne(id))}
          >
            导出 <Icon name="arrow-right" size={12} />
          </button>
        </div>
      ) : null}

      {taskDrawerId ? (
        <TaskDrawer
          taskId={taskDrawerId}
          onClose={() => setTaskDrawerId(null)}
          onRerun={(id, mode) => rerunOne.mutate({ id, mode })}
          onCancel={(id) => cancelOne.mutate(id)}
        />
      ) : null}

      <ClaudeShareDialog
        open={claudeShareOpen}
        articleIds={selectedIds}
        onClose={() => setClaudeShareOpen(false)}
      />

      <ConfirmDialog
        open={confirmDeleteOpen}
        title={`确认删除 ${selCount} 篇文章？`}
        description="删除后文章内容和关联的逐字稿分段会一起移除，这个操作不可撤销。"
        confirmLabel="确认删除"
        cancelLabel="取消"
        pending={deleteMut.isPending}
        onCancel={() => setConfirmDeleteOpen(false)}
        onConfirm={() => {
          deleteMut.mutate(selectedIds, {
            onSuccess: () => setConfirmDeleteOpen(false),
            onError: () => setConfirmDeleteOpen(false),
          });
        }}
      />
    </Page>
  );
}
