import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Page, PageHead } from '@/layouts/AppShell';
import { TaskDrawer } from '@/components/Task/TaskDrawer';
import { Avatar, ConfirmDialog, Icon } from '@/components/primitives';
import { api } from '@/lib/api';
import { thumbGradient } from '@/lib/gradients';
import { mediaCandidates } from '@/lib/media';
import { formatCount, formatDate, formatDuration, formatRelative } from '@/lib/format';
import type {
  Article,
  Creator,
  Page as ApiPage,
  Task,
  TaskCancelResult,
  TaskRerunResult,
} from '@/types/api';
import s from './Articles.module.css';

type TimeFilter = 'all' | '7d' | '30d' | '90d';
type RebuildStage = 'auto' | 'download' | 'transcribe' | 'correct' | 'organize';

const REBUILD_STAGE_OPTIONS: { v: RebuildStage; label: string }[] = [
  { v: 'auto', label: '自动(有缓存从转写,否则从下载)' },
  { v: 'download', label: '从下载开始' },
  { v: 'transcribe', label: '从转写开始' },
  { v: 'correct', label: '从校对开始' },
  { v: 'organize', label: '从整理开始' },
];

const TIME_OPTIONS: { v: TimeFilter; label: string }[] = [
  { v: 'all', label: '全部' },
  { v: '7d', label: '近 7 天' },
  { v: '30d', label: '近 30 天' },
  { v: '90d', label: '近 90 天' },
];

const PAGE_SIZE = 20;

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
  const qc = useQueryClient();

  const [creatorFilter, setCreatorFilter] = useState<string>('all');
  const [time, setTime] = useState<TimeFilter>('all');
  const [tagFilter, setTagFilter] = useState<string>('all');
  const [qDraft, setQDraft] = useState('');
  const [q, setQ] = useState('');
  useEffect(() => {
    const id = setTimeout(() => setQ(qDraft.trim()), 250);
    return () => clearTimeout(id);
  }, [qDraft]);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [openDrop, setOpenDrop] = useState<string | null>(null);
  const [rebuildStage, setRebuildStage] = useState<RebuildStage>('auto');
  const [taskDrawerId, setTaskDrawerId] = useState<string | null>(null);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);

  useEffect(() => {
    if (!openDrop) return;
    const onDoc = () => setOpenDrop(null);
    document.addEventListener('click', onDoc);
    return () => document.removeEventListener('click', onDoc);
  }, [openDrop]);

  useEffect(() => {
    setSelected(new Set());
    setPage(1);
  }, [creatorFilter, time, tagFilter, q]);

  const listParams = useMemo(() => {
    const p = new URLSearchParams();
    if (creatorFilter !== 'all') p.set('creator_id', creatorFilter);
    if (tagFilter !== 'all') p.set('tag', tagFilter);
    if (time !== 'all') p.set('since', time);
    if (q) p.set('q', q);
    p.set('limit', String(PAGE_SIZE));
    p.set('offset', String((page - 1) * PAGE_SIZE));
    return p.toString();
  }, [creatorFilter, tagFilter, time, q, page]);

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
  const totalPages = Math.max(1, Math.ceil(listTotal / PAGE_SIZE));

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
      setSelected(new Set());
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
      setSelected(new Set());
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
    window.open(`/api/articles/${id}/export.md`, '_blank');
  };

  const pageIds = articles.map((a) => a.id);
  const allOnPageSelected =
    pageIds.length > 0 && pageIds.every((id) => selected.has(id));
  const someOnPageSelected = pageIds.some((id) => selected.has(id));
  const allCbxCls = !someOnPageSelected
    ? s.cbx
    : allOnPageSelected
    ? [s.cbx, s.cbxOn].join(' ')
    : [s.cbx, s.cbxIndet].join(' ');

  const toggleOne = (id: string) => {
    setSelected((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  };
  const toggleAll = () => {
    setSelected((prev) => {
      if (allOnPageSelected) {
        const n = new Set(prev);
        pageIds.forEach((id) => n.delete(id));
        return n;
      }
      const n = new Set(prev);
      pageIds.forEach((id) => n.add(id));
      return n;
    });
  };

  const clearAll = () => {
    setCreatorFilter('all');
    setTime('all');
    setTagFilter('all');
    setQDraft('');
    setQ('');
  };

  const creatorLabel =
    creatorFilter === 'all'
      ? '全部'
      : creatorMap.get(Number(creatorFilter))?.name ?? `#${creatorFilter}`;
  const activeFilters: { k: string; label: string; reset: () => void }[] = [
    ...(creatorFilter !== 'all'
      ? [{ k: '创作者', label: creatorLabel, reset: () => setCreatorFilter('all') }]
      : []),
    ...(time !== 'all'
      ? [
          {
            k: '时间',
            label: TIME_OPTIONS.find((o) => o.v === time)!.label,
            reset: () => setTime('all'),
          },
        ]
      : []),
    ...(tagFilter !== 'all'
      ? [{ k: '标签', label: `#${tagFilter}`, reset: () => setTagFilter('all') }]
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

  const selCount = selected.size;
  const selectedIds = Array.from(selected);

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
          onSelect={setCreatorFilter}
        />
        <Dropdown
          id="time"
          k="时间"
          value={time}
          options={TIME_OPTIONS.map((o) => ({ v: o.v, label: o.label }))}
          openId={openDrop}
          setOpenId={setOpenDrop}
          onSelect={setTime}
        />
        <Dropdown
          id="tag"
          k="标签"
          value={tagFilter}
          options={tagOptions}
          openId={openDrop}
          setOpenId={setOpenDrop}
          onSelect={setTagFilter}
          headerLabel={tagFacets.length ? '高频标签' : undefined}
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
          按日期倒序 · 第 {page} 页 / 共 {totalPages} 页
        </span>
      </div>

      <div className={s.table}>
        <div className={s.tableScroll}>
          <div className={s.tHead}>
            <span>
              <button className={allCbxCls} onClick={toggleAll} aria-label="全选" />
            </span>
            <span>文章</span>
            <span>博主</span>
            <span>标签</span>
            <span>指标</span>
            <span>发布</span>
            <span>更新</span>
            <span />
          </div>
          {articles.length === 0 ? (
            <div className={s.emptyBlock}>暂无文章 · 从首页提交第一条链接 →</div>
          ) : (
            articles.map((a, i) => {
              const c = creatorMap.get(a.creator_id);
              const isSel = selected.has(a.id);
              return (
                <div
                  key={a.id}
                  className={[s.tRow, isSel ? s.tRowSelected : ''].join(' ')}
                  onClick={(e) => {
                    const tgt = e.target as HTMLElement;
                    if (tgt.closest('button')) return;
                    navigate(`/articles/${a.id}`);
                  }}
                >
                  <span>
                    <button
                      className={[s.cbx, isSel ? s.cbxOn : ''].join(' ')}
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleOne(a.id);
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
                  <span className={s.dateCell} title={formatDate(a.published_at)}>
                    {formatRelative(a.published_at)}
                  </span>
                  <span
                    className={s.dateCell}
                    title={new Date(a.updated_at).toLocaleString('zh-CN')}
                  >
                    {formatRelative(a.updated_at)}
                  </span>
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
            共 {totalPages} 页 · 每页 {PAGE_SIZE} 条
          </span>
          <div className={s.pagerBtns}>
            <button disabled={page <= 1} onClick={() => setPage(page - 1)}>
              ‹
            </button>
            {buildPageNumbers(page, totalPages).map((p, i) =>
              p === '...' ? (
                <button key={`e${i}`} disabled>
                  …
                </button>
              ) : (
                <button
                  key={p}
                  className={p === page ? s.pagerBtnOn : ''}
                  onClick={() => setPage(p)}
                >
                  {p}
                </button>
              ),
            )}
            <button disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
              ›
            </button>
          </div>
        </div>
      ) : null}

      {selCount > 0 ? (
        <div className={s.stickyBar}>
          <span className={s.stickyCount}>
            <b>{selCount}</b>篇已选中
          </span>
          <span className={s.stickySpacer} />
          <button className={s.stickyGhost} onClick={() => setSelected(new Set())}>
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
