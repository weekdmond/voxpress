import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Page, PageHead } from '@/layouts/AppShell';
import { Icon } from '@/components/primitives';
import { TaskChainBar, STAGE_LABEL } from '@/components/Task/TaskChainBar';
import { TaskCover } from '@/components/Task/TaskCover';
import { TaskDrawer } from '@/components/Task/TaskDrawer';
import { api } from '@/lib/api';
import { formatDuration, formatRelative } from '@/lib/format';
import { subscribeTasks } from '@/lib/sse';
import type {
  Page as ApiPage,
  SystemJobRun,
  SystemJobStatus,
  SystemJobSummary,
  Task,
  TaskCancelResult,
  TaskRerunResult,
  TaskStatus,
  TaskSummary,
} from '@/types/api';
import s from './Tasks.module.css';

const SCOPE_TABS: { key: 'content' | 'system'; label: string }[] = [
  { key: 'content', label: '内容任务' },
  { key: 'system', label: '系统任务' },
];

const CONTENT_STATUS_TABS: { key: string; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'running', label: '运行中' },
  { key: 'queued', label: '排队' },
  { key: 'done', label: '成功' },
  { key: 'failed', label: '失败' },
];

const SYSTEM_STATUS_TABS: { key: string; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'running', label: '运行中' },
  { key: 'done', label: '成功' },
  { key: 'failed', label: '失败' },
  { key: 'skipped', label: '跳过' },
];

const TIME_OPTIONS = [
  { v: 'all', label: '全部' },
  { v: '1h', label: '近 1 小时' },
  { v: '24h', label: '今日' },
  { v: '7d', label: '近 7 天' },
  { v: '30d', label: '近 30 天' },
];

const STAGE_OPTIONS = [
  { v: 'all', label: '全部' },
  { v: 'download', label: 'download' },
  { v: 'transcribe', label: 'transcribe' },
  { v: 'correct', label: 'correct' },
  { v: 'organize', label: 'organize' },
  { v: 'save', label: 'save' },
];

const PAGE_SIZE = 20;

function fmtTokens(n: number): string {
  if (!n) return '—';
  if (n >= 10000) return `${(n / 10000).toFixed(1)}w`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function fmtCost(n: number | null | undefined): string {
  if (n == null || n === 0) return '¥0.000';
  return `¥${n.toFixed(3)}`;
}

function fmtElapsed(ms: number | null | undefined): string {
  if (!ms || ms < 0) return '—';
  return formatDuration(Math.round(ms / 1000));
}

function labelFromTitle(t: string): string {
  const m = t.trim().match(/[\u4e00-\u9fffA-Z0-9]{1,3}/);
  return m ? m[0] : 'VP';
}

function statusDot(status: TaskStatus | SystemJobStatus): string {
  if (status === 'done') return s.stDotDone;
  if (status === 'running') return s.stDotRunning;
  if (status === 'failed') return s.stDotFailed;
  if (status === 'queued') return s.stDotQueued;
  return s.stDotCanceled;
}

function systemStageLabel(status: SystemJobStatus): string {
  if (status === 'done') return 'COMPLETED';
  if (status === 'running') return 'RUNNING';
  if (status === 'failed') return 'FAILED';
  return 'SKIPPED';
}

interface DropdownProps {
  id: string;
  k: string;
  value: string;
  label: string;
  options: { v: string; label: string; count?: number }[];
  openId: string | null;
  setOpenId: (v: string | null) => void;
  onSelect: (v: string) => void;
}

function Dropdown({ id, k, value, label, options, openId, setOpenId, onSelect }: DropdownProps) {
  const open = openId === id;
  const isEmpty = value === 'all';
  const currentLabel = options.find((o) => o.v === value)?.label ?? label;
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
        <span className={s.dropVal}>{currentLabel}</span>
        <span className={s.dropCaret}>▾</span>
      </button>
      {open ? (
        <div className={s.dropMenu} onClick={(e) => e.stopPropagation()}>
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

export function TasksPage() {
  const [sp, setSp] = useSearchParams();
  const qc = useQueryClient();

  const scope = sp.get('scope') === 'system' ? 'system' : 'content';
  const isSystem = scope === 'system';
  const tab = sp.get('tab') || 'all';
  const model = sp.get('model') || 'all';
  const stage = sp.get('stage') || 'all';
  const time = sp.get('time') || 'all';
  const qStr = sp.get('q') || '';
  const page = Math.max(1, Number(sp.get('page') || 1));
  const [qDraft, setQDraft] = useState(qStr);
  useEffect(() => setQDraft(qStr), [qStr]);

  const setFilter = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(sp);
    for (const [k, v] of Object.entries(patch)) {
      if (!v || v === 'all' || v === '') next.delete(k);
      else next.set(k, v);
    }
    if (!('page' in patch)) next.delete('page');
    setSp(next, { replace: true });
  };

  // ─── Summary ─────────────────────────────────────
  const { data: summary } = useQuery({
    queryKey: ['tasks', 'summary'],
    queryFn: () => api.get<TaskSummary>('/api/tasks/summary'),
    refetchInterval: 60_000,
    enabled: !isSystem,
  });
  const statusCounts = summary?.status_counts ?? {};
  const totalCount = Object.values(statusCounts).reduce((a, b) => a + b, 0);

  const { data: systemSummary } = useQuery({
    queryKey: ['system-jobs', 'summary'],
    queryFn: () => api.get<SystemJobSummary>('/api/system-jobs/summary'),
    refetchInterval: 60_000,
    enabled: isSystem,
  });
  const systemStatusCounts = systemSummary?.status_counts ?? {};
  const systemTotalCount = Object.values(systemStatusCounts).reduce((a, b) => a + b, 0);

  // ─── List ────────────────────────────────────────
  const listParams = useMemo(() => {
    const p = new URLSearchParams();
    if (tab !== 'all') p.set('status', tab);
    if (stage !== 'all') p.set('stage', stage);
    if (model !== 'all') p.set('model', model);
    if (time !== 'all') p.set('since', time);
    if (qStr) p.set('q', qStr);
    p.set('limit', String(PAGE_SIZE));
    p.set('offset', String((page - 1) * PAGE_SIZE));
    return p.toString();
  }, [tab, stage, model, time, qStr, page]);

  const { data: listPage } = useQuery({
    queryKey: ['tasks', 'list', listParams],
    queryFn: () => api.get<ApiPage<Task>>(`/api/tasks?${listParams}`),
    enabled: !isSystem,
  });
  const tasks = listPage?.items ?? [];
  const listTotal = listPage?.total ?? tasks.length;
  const totalPages = Math.max(1, Math.ceil(listTotal / PAGE_SIZE));

  const systemParams = useMemo(() => {
    const p = new URLSearchParams();
    if (tab !== 'all') p.set('status', tab);
    if (time !== 'all') p.set('since', time);
    if (qStr) p.set('q', qStr);
    p.set('limit', String(PAGE_SIZE));
    p.set('offset', String((page - 1) * PAGE_SIZE));
    return p.toString();
  }, [tab, time, qStr, page]);

  const { data: systemPage } = useQuery({
    queryKey: ['system-jobs', 'list', systemParams],
    queryFn: () => api.get<ApiPage<SystemJobRun>>(`/api/system-jobs?${systemParams}`),
    enabled: isSystem,
    refetchInterval: 60_000,
  });
  const systemJobs = systemPage?.items ?? [];
  const systemListTotal = systemPage?.total ?? systemJobs.length;
  const systemTotalPages = Math.max(1, Math.ceil(systemListTotal / PAGE_SIZE));

  // ─── SSE live updates ────────────────────────────
  useEffect(() => {
    if (isSystem) return;
    return subscribeTasks((e) => {
      if (e.type === 'remove') {
        qc.invalidateQueries({ queryKey: ['tasks'] });
        return;
      }
      qc.setQueriesData<ApiPage<Task>>({ queryKey: ['tasks', 'list'] }, (data) => {
        if (!data) return data;
        const t = e.task as Task;
        const idx = data.items.findIndex((x) => x.id === t.id);
        if (idx === -1) {
          if (e.type === 'create') {
            return { ...data, items: [t, ...data.items].slice(0, PAGE_SIZE) };
          }
          return data;
        }
        const items = [...data.items];
        items[idx] = t;
        return { ...data, items };
      });
      if (e.type === 'update' && (e.task.status === 'done' || e.task.status === 'failed')) {
        qc.invalidateQueries({ queryKey: ['tasks', 'summary'] });
      }
    });
  }, [isSystem, qc]);

  // ─── Selection ───────────────────────────────────
  const [selected, setSelected] = useState<Set<string>>(new Set());
  useEffect(() => setSelected(new Set()), [listParams]);
  const toggleOne = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const toggleAll = () => {
    setSelected((prev) => {
      if (prev.size === tasks.length && tasks.length > 0) return new Set();
      return new Set(tasks.map((t) => t.id));
    });
  };
  const allCbxCls =
    selected.size === 0
      ? s.cbx
      : selected.size === tasks.length
      ? [s.cbx, s.cbxOn].join(' ')
      : [s.cbx, s.cbxIndet].join(' ');

  const [drawerId, setDrawerId] = useState<string | null>(null);

  const [openDrop, setOpenDrop] = useState<string | null>(null);
  useEffect(() => {
    if (!openDrop) return;
    const onDoc = () => setOpenDrop(null);
    document.addEventListener('click', onDoc);
    return () => document.removeEventListener('click', onDoc);
  }, [openDrop]);

  // ─── Mutations ────────────────────────────────────
  const rerunBatch = useMutation({
    mutationFn: (ids: string[]) =>
      api.post<TaskRerunResult>('/api/tasks/rerun', { task_ids: ids, mode: 'resume' }),
    onSuccess: (r) => {
      toast.success(`已加入重跑队列 · 成功 ${r.processed} / ${r.requested}`);
      setSelected(new Set());
      qc.invalidateQueries({ queryKey: ['tasks'] });
    },
    onError: (e: Error) => toast.error(e.message || '重跑失败'),
  });
  const cancelBatch = useMutation({
    mutationFn: (ids: string[]) =>
      api.post<TaskCancelResult>('/api/tasks/cancel', { task_ids: ids }),
    onSuccess: (r) => {
      toast.success(`已取消 ${r.processed} / ${r.requested} 个任务`);
      setSelected(new Set());
      qc.invalidateQueries({ queryKey: ['tasks'] });
    },
    onError: (e: Error) => toast.error(e.message || '取消失败'),
  });
  const rerunOne = useMutation({
    mutationFn: ({ id, mode }: { id: string; mode: string }) =>
      api.post<TaskRerunResult>('/api/tasks/rerun', { task_ids: [id], mode }),
    onSuccess: (_r, vars) => {
      toast.success(`已触发 ${vars.mode} 重跑`);
      setDrawerId(null);
      qc.invalidateQueries({ queryKey: ['tasks'] });
    },
    onError: (e: Error) => toast.error(e.message || '重跑失败'),
  });
  const cancelOne = useMutation({
    mutationFn: (id: string) => api.post<Task>(`/api/tasks/${id}/cancel`),
    onSuccess: () => {
      toast.success('已取消');
      qc.invalidateQueries({ queryKey: ['tasks'] });
    },
    onError: (e: Error) => toast.error(e.message || '取消失败'),
  });

  const refresh = () => {
    if (isSystem) {
      qc.invalidateQueries({ queryKey: ['system-jobs'] });
      return;
    }
    qc.invalidateQueries({ queryKey: ['tasks'] });
  };

  const contentTabCounts: Record<string, number | undefined> = {
    all: totalCount || undefined,
    running: statusCounts.running,
    queued: statusCounts.queued,
    done: statusCounts.done,
    failed: statusCounts.failed,
  };
  const systemTabCounts: Record<string, number | undefined> = {
    all: systemTotalCount || undefined,
    running: systemStatusCounts.running,
    done: systemStatusCounts.done,
    failed: systemStatusCounts.failed,
    skipped: systemStatusCounts.skipped,
  };
  const tabCounts = isSystem ? systemTabCounts : contentTabCounts;
  const visibleTabs = isSystem ? SYSTEM_STATUS_TABS : CONTENT_STATUS_TABS;

  const modelOptions = useMemo(() => {
    const opts: { v: string; label: string; count?: number }[] = [{ v: 'all', label: '全部' }];
    (summary?.model_facets ?? []).forEach((m) =>
      opts.push({ v: m.value, label: m.value, count: m.count }),
    );
    return opts;
  }, [summary]);

  const submitSearch = () => setFilter({ q: qDraft.trim() });

  const selectedIds = Array.from(selected);
  const selectedHint = useMemo(() => {
    const sel = tasks.filter((t) => selected.has(t.id));
    const failedN = sel.filter((t) => t.status === 'failed').length;
    const estCost = sel.reduce((a, t) => a + (t.cost_cny ?? 0), 0) * 0.6;
    return `预计消耗 ¥${estCost.toFixed(2)}${failedN ? ` · ${failedN} 条失败将从断点续跑` : ''}`;
  }, [tasks, selected]);

  const pagerShown = isSystem ? systemTotalPages > 1 : totalPages > 1;

  return (
    <Page>
      <PageHead
        title="任务"
        meta={
          <span>
            {isSystem ? '系统定时任务记录 · 按开始时间倒序' : '全部任务链记录 · 按开始时间倒序'}
          </span>
        }
      />

      <div className={s.scopeTabs}>
        {SCOPE_TABS.map((item) => (
          <button
            key={item.key}
            className={[s.scopeTab, scope === item.key ? s.scopeTabOn : ''].join(' ')}
            onClick={() =>
              setFilter({
                scope: item.key,
                tab: null,
                model: null,
                stage: null,
                q: null,
              })
            }
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className={s.headActions} style={{ justifyContent: 'flex-end', marginTop: -12 }}>
        <button className={[s.plainBtn, s.ghostBtn].join(' ')} onClick={refresh}>
          <Icon name="refresh" size={13} /> 刷新
        </button>
      </div>

      {/* Stats */}
      <div className={s.statsBar}>
        <div className={s.stat}>
          <span className={s.statKey}>
            {isSystem ? '今日运行' : '今日任务'} <span className="pill">24h</span>
          </span>
          <b className={s.statValue}>
            {isSystem ? systemSummary?.today_runs ?? '—' : summary?.today_tasks ?? '—'}
          </b>
          <span className={s.statDelta}>
            {isSystem
              ? systemSummary
                ? `${systemStatusCounts.done ?? 0} 成功 · ${systemStatusCounts.failed ?? 0} 失败`
                : '等待聚合'
              : summary
                ? `${statusCounts.done ?? 0} 成功 · ${statusCounts.failed ?? 0} 失败`
                : '等待聚合'}
          </span>
        </div>
        <div className={s.stat}>
          <span className={s.statKey}>成功率</span>
          <b className={s.statValue}>
            {isSystem
              ? systemSummary
                ? `${systemSummary.today_success_rate.toFixed(1)}%`
                : '—'
              : summary
                ? `${summary.today_success_rate.toFixed(1)}%`
                : '—'}
          </b>
          <span className={s.statDelta}>{isSystem ? '按周期统计' : '今日端到端'}</span>
        </div>
        <div className={s.stat}>
          <span className={s.statKey}>{isSystem ? '已刷新博主' : '今日消费'}</span>
          <b className={s.statValue}>
            {isSystem
              ? systemSummary?.today_processed_items ?? '—'
              : summary
                ? `¥${summary.today_cost_cny.toFixed(2)}`
                : '—'}
          </b>
          <span className={s.statDelta}>{isSystem ? '今日累计更新' : 'DashScope 计费'}</span>
        </div>
        <div className={s.stat}>
          <span className={s.statKey}>{isSystem ? '失败博主' : 'Token 消耗'}</span>
          <b className={s.statValue}>
            {isSystem
              ? systemSummary?.today_failed_items ?? '—'
              : summary
                ? fmtTokens(summary.today_total_tokens)
                : '—'}
          </b>
          <span className={s.statDelta}>{isSystem ? '今日累计失败' : 'LLM · 今日'}</span>
        </div>
        <div className={s.stat}>
          <span className={s.statKey}>平均耗时</span>
          <b className={s.statValue}>
            {isSystem
              ? systemSummary
                ? fmtElapsed(systemSummary.avg_duration_ms)
                : '—'
              : summary
                ? fmtElapsed(summary.avg_elapsed_ms)
                : '—'}
          </b>
          <span className={s.statDelta}>{isSystem ? '单次周期' : '单篇端到端'}</span>
        </div>
      </div>

      {/* Filter bar */}
      <div className={s.filterBar}>
        <div className={s.tabs}>
          {visibleTabs.map((t) => (
            <button
              key={t.key}
              className={[s.tabBtn, tab === t.key ? s.tabOn : ''].join(' ')}
              onClick={() => setFilter({ tab: t.key })}
            >
              {t.label}
              <span className={s.tabCount}>{tabCounts[t.key] ?? '—'}</span>
            </button>
          ))}
        </div>
        <div className={s.divider} />
        {!isSystem ? (
          <>
            <Dropdown
              id="model"
              k="模型"
              value={model}
              label="全部"
              options={modelOptions}
              openId={openDrop}
              setOpenId={setOpenDrop}
              onSelect={(v) => setFilter({ model: v })}
            />
            <Dropdown
              id="stage"
              k="阶段"
              value={stage}
              label="全部"
              options={STAGE_OPTIONS}
              openId={openDrop}
              setOpenId={setOpenDrop}
              onSelect={(v) => setFilter({ stage: v })}
            />
          </>
        ) : null}
        <Dropdown
          id="time"
          k="时间"
          value={time}
          label="全部"
          options={TIME_OPTIONS}
          openId={openDrop}
          setOpenId={setOpenDrop}
          onSelect={(v) => setFilter({ time: v })}
        />
        <div className={s.search}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
          <input
            placeholder={isSystem ? '搜索运行 ID、任务名…' : '搜索任务 ID、文章标题…'}
            value={qDraft}
            onChange={(e) => setQDraft(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submitSearch()}
            onBlur={submitSearch}
          />
        </div>
        <span className={s.spacer} />
        {tab !== 'all' ||
        (!isSystem && model !== 'all') ||
        (!isSystem && stage !== 'all') ||
        time !== 'all' ||
        qStr ? (
          <button
            className={[s.plainBtn, s.ghostBtn].join(' ')}
            onClick={() =>
              setFilter({
                tab: null,
                model: null,
                stage: null,
                time: null,
                q: null,
              })
            }
          >
            重置
          </button>
        ) : null}
      </div>

      {/* List head */}
      <div className={s.listHead}>
        <h2>
          {isSystem ? '系统任务' : '任务列表'}
          <span className={s.listHeadMeta} style={{ marginLeft: 6 }}>
            {(isSystem ? systemListTotal : listTotal).toLocaleString()} 条
          </span>
        </h2>
        <span className={s.listHeadMeta}>
          每页 {PAGE_SIZE} 条 · 第 {page} / {isSystem ? systemTotalPages : totalPages} 页
        </span>
      </div>

      {/* Bulk bar */}
      {!isSystem && selected.size > 0 ? (
        <div className={s.bulkBar}>
          <span className={s.bulkCount}>
            <b>{selected.size}</b>已选
          </span>
          <span className={s.bulkHint}>— {selectedHint}</span>
          <span className={s.bulkSpacer} />
          <button className={s.bulkBtn} onClick={() => setSelected(new Set())}>
            取消选择
          </button>
          <button
            className={s.bulkBtn}
            onClick={() => cancelBatch.mutate(selectedIds)}
            disabled={cancelBatch.isPending}
          >
            取消任务
          </button>
          <button
            className={[s.bulkBtn, s.bulkBtnPrimary].join(' ')}
            onClick={() => rerunBatch.mutate(selectedIds)}
            disabled={rerunBatch.isPending}
          >
            <Icon name="refresh" size={13} /> 重跑
          </button>
        </div>
      ) : null}

      {/* Table */}
      <div className={s.table}>
        <div className={s.tableScroll}>
          {!isSystem ? (
            <>
              <div className={s.tHead}>
                <span>
                  <button className={allCbxCls} onClick={toggleAll} aria-label="全选" />
                </span>
                <span />
                <span>任务 ID</span>
                <span>文章 / 博主</span>
                <span>任务链</span>
                <span>成本 · Token · 耗时</span>
                <span />
              </div>

              {tasks.length === 0 ? (
                <div className={s.emptyBlock}>暂无匹配的任务</div>
              ) : (
                tasks.map((t, i) => {
                  const isSel = selected.has(t.id);
                  const stageLabel =
                    t.status === 'done' ? 'completed' : STAGE_LABEL[t.stage] || t.stage;
                  return (
                    <div
                      key={t.id}
                      className={[s.tRow, isSel ? s.tRowSelected : ''].join(' ')}
                      onClick={(e) => {
                        const tgt = e.target as HTMLElement;
                        if (tgt.closest('button,[role="checkbox"]')) return;
                        setDrawerId(t.id);
                      }}
                    >
                      <span>
                        <button
                          className={[s.cbx, isSel ? s.cbxOn : ''].join(' ')}
                          role="checkbox"
                          aria-checked={isSel}
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleOne(t.id);
                          }}
                          aria-label="选择"
                        />
                      </span>
                      <span className={[s.stDot, statusDot(t.status)].join(' ')} title={t.status} />
                      <div className={s.taskId}>
                        <span className={s.taskIdShort}>{t.id.slice(0, 12)}</span>
                        <span className={s.taskIdStage}>{stageLabel}</span>
                      </div>
                      <div className={s.articleCell}>
                        <TaskCover
                          seed={(t.creator_id ?? 0) + i}
                          label={labelFromTitle(t.title_guess || t.article_title || '')}
                          src={t.cover_url}
                        />
                        <div className={s.articleMain}>
                          <span className={s.articleTitle}>
                            {t.article_title || t.title_guess || '解析中…'}
                          </span>
                          <span className={s.articleAuthor}>
                            {t.creator_name ?? '—'} · {formatRelative(t.started_at)}
                          </span>
                        </div>
                      </div>
                      <TaskChainBar stage={t.stage} status={t.status} />
                      <div className={s.costCell}>
                        <b>{fmtCost(t.cost_cny)}</b>
                        <span className={s.costSub}>
                          {t.status === 'running' || t.status === 'queued' ? (
                            t.status === 'running' ? '进行中' : '排队中'
                          ) : (
                            <>
                              {fmtTokens(t.total_tokens)} tok
                              <span className={s.costDot}>·</span>
                              {fmtElapsed(t.elapsed_ms)}
                            </>
                          )}
                        </span>
                      </div>
                      <button
                        className={s.rowAct}
                        title="查看详情"
                        onClick={(e) => {
                          e.stopPropagation();
                          setDrawerId(t.id);
                        }}
                      >
                        <Icon name="chevron" size={13} />
                      </button>
                    </div>
                  );
                })
              )}
            </>
          ) : (
            <>
              <div className={[s.tHead, s.sysHead].join(' ')}>
                <span />
                <span>运行 ID</span>
                <span>系统任务</span>
                <span>处理结果</span>
                <span>耗时</span>
                <span>最近执行</span>
              </div>

              {systemJobs.length === 0 ? (
                <div className={s.emptyBlock}>暂无系统任务记录</div>
              ) : (
                systemJobs.map((job) => (
                  <div key={job.id} className={[s.tRow, s.sysRow].join(' ')}>
                    <span className={[s.stDot, statusDot(job.status)].join(' ')} title={job.status} />
                    <div className={s.taskId}>
                      <span className={s.taskIdShort}>{job.id.slice(0, 12)}</span>
                      <span className={s.taskIdStage}>{systemStageLabel(job.status)}</span>
                    </div>
                    <div className={s.sysMain}>
                      <span className={s.articleTitle}>{job.job_name}</span>
                      <span className={s.articleAuthor}>
                        {job.scope ?? '系统后台任务'}
                        {job.detail ? ` · ${job.detail}` : ''}
                      </span>
                      {job.error ? <span className={s.sysError}>{job.error}</span> : null}
                    </div>
                    <div className={s.sysResult}>
                      <b>
                        {job.processed_items}/{job.total_items || 0}
                      </b>
                      <span className={s.costSub}>
                        失败 {job.failed_items} · 跳过 {job.skipped_items}
                      </span>
                    </div>
                    <div className={s.num}>{fmtElapsed(job.duration_ms)}</div>
                    <div className={s.sysWhen}>
                      <span>{formatRelative(job.started_at)}</span>
                      <span className={s.articleAuthor}>{job.finished_at ? '已完成' : '进行中'}</span>
                    </div>
                  </div>
                ))
              )}
            </>
          )}
        </div>
      </div>

      {pagerShown ? (
        <div className={s.pager}>
          <span>
            共 {isSystem ? systemTotalPages : totalPages} 页 · 每页 {PAGE_SIZE} 条
          </span>
          <div className={s.pagerBtns}>
            <button disabled={page <= 1} onClick={() => setFilter({ page: String(page - 1) })}>
              ‹
            </button>
            {buildPageNumbers(page, isSystem ? systemTotalPages : totalPages).map((p, i) =>
              p === '...' ? (
                <button key={`e${i}`} disabled>
                  …
                </button>
              ) : (
                <button
                  key={p}
                  className={p === page ? s.pagerBtnOn : ''}
                  onClick={() => setFilter({ page: String(p) })}
                >
                  {p}
                </button>
              ),
            )}
            <button
              disabled={page >= (isSystem ? systemTotalPages : totalPages)}
              onClick={() => setFilter({ page: String(page + 1) })}
            >
              ›
            </button>
          </div>
        </div>
      ) : null}

      {!isSystem && drawerId ? (
        <TaskDrawer
          taskId={drawerId}
          onClose={() => setDrawerId(null)}
          onRerun={(id, mode) => rerunOne.mutate({ id, mode })}
          onCancel={(id) => cancelOne.mutate(id)}
        />
      ) : null}
    </Page>
  );
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
