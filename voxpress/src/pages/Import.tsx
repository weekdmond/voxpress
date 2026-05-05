import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Page, PageHead } from '@/layouts/AppShell';
import { useCrossPageSelection } from '@/hooks/useCrossPageSelection';
import { Avatar, Icon } from '@/components/primitives';
import { api } from '@/lib/api';
import { formatCount, formatDate, formatDateTime, formatDuration } from '@/lib/format';
import { mediaCandidates } from '@/lib/media';
import type {
  Creator,
  Page as ApiPage,
  SystemJobRun,
  TaskBatchResult,
  Video,
  VideoSummary,
} from '@/types/api';
import s from './Import.module.css';

type StatusFilter = 'all' | 'organized' | 'pending';
type DurFilter = 'all' | '20s' | '60s' | '180s' | '600s';
type HotFilter = 'all' | '1k' | '1w' | '5w';
type TimeFilter = 'all' | '7d' | '30d' | '90d';

const PAGE_SIZE = 40;

const STATUS_OPTIONS: { v: StatusFilter; label: string }[] = [
  { v: 'all', label: '全部' },
  { v: 'organized', label: '已转文章' },
  { v: 'pending', label: '待处理' },
];
const DUR_OPTIONS: { v: DurFilter; label: string; minSec: number }[] = [
  { v: 'all', label: '全部', minSec: 0 },
  { v: '20s', label: '20 秒+', minSec: 20 },
  { v: '60s', label: '1 分钟+', minSec: 60 },
  { v: '180s', label: '3 分钟+', minSec: 180 },
  { v: '600s', label: '10 分钟+', minSec: 600 },
];
const HOT_OPTIONS: { v: HotFilter; label: string; minLikes: number }[] = [
  { v: 'all', label: '全部', minLikes: 0 },
  { v: '1k', label: '1k+ 点赞', minLikes: 1_000 },
  { v: '1w', label: '1w+ 点赞', minLikes: 10_000 },
  { v: '5w', label: '5w+ 点赞', minLikes: 50_000 },
];
const TIME_OPTIONS: { v: TimeFilter; label: string; days: number }[] = [
  { v: 'all', label: '全部', days: 0 },
  { v: '7d', label: '近 7 天', days: 7 },
  { v: '30d', label: '近 30 天', days: 30 },
  { v: '90d', label: '近 90 天', days: 90 },
];

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

function VideoThumb({ src, seed }: { src: string | null; seed: number }) {
  const [attempt, setAttempt] = useState(0);
  useEffect(() => setAttempt(0), [src]);
  const candidates = mediaCandidates(src);
  const resolved = candidates[attempt];
  const gradients = [
    'linear-gradient(135deg,#dde3ec,#b8c1d0)',
    'linear-gradient(135deg,#e6dfd3,#c8bfad)',
    'linear-gradient(135deg,#d6e0e6,#b0becb)',
    'linear-gradient(135deg,#e3dae0,#c5b6bf)',
    'linear-gradient(135deg,#dae3db,#b6c6b9)',
  ];
  const bg = gradients[Math.abs(seed) % gradients.length];
  return (
    <div className={s.videoThumb} style={{ background: bg }} aria-hidden>
      {resolved ? (
        <img src={resolved} alt="" referrerPolicy="no-referrer" onError={() => setAttempt((v) => v + 1)} />
      ) : null}
      <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
        <path d="M8 5.5v13l11-6.5z" />
      </svg>
    </div>
  );
}

function DouyinBadge() {
  return (
    <span className={s.platformBadge} title="抖音">
      <svg viewBox="0 0 48 48" width="16" height="16" aria-label="抖音">
        <path
          d="M37.5 13.2a9.3 9.3 0 0 1-5.7-2 9.3 9.3 0 0 1-3.6-5.8h-5.8v23.9a4.3 4.3 0 1 1-3-4.1v-5.9a10.2 10.2 0 1 0 8.8 10.1V17.6a15 15 0 0 0 9.3 3.2z"
          fill="currentColor"
        />
      </svg>
    </span>
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
}

function Dropdown<T extends string>({
  id,
  k,
  value,
  options,
  openId,
  setOpenId,
  onSelect,
}: DropdownProps<T>) {
  const open = openId === id;
  const isEmpty = value === 'all';
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

export function ImportPage() {
  const { creatorId = '' } = useParams<{ creatorId: string }>();
  const idNum = Number(creatorId);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [status, setStatus] = useState<StatusFilter>('all');
  const [dur, setDur] = useState<DurFilter>('all');
  const [hot, setHot] = useState<HotFilter>('all');
  const [time, setTime] = useState<TimeFilter>('all');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const [openDrop, setOpenDrop] = useState<string | null>(null);

  useEffect(() => {
    if (!openDrop) return;
    const onDoc = () => setOpenDrop(null);
    document.addEventListener('click', onDoc);
    return () => document.removeEventListener('click', onDoc);
  }, [openDrop]);

  useEffect(() => {
    setPage(1);
  }, [status, dur, hot, time, q]);

  const { data: creator } = useQuery({
    queryKey: ['creator', idNum],
    queryFn: () => api.get<Creator>(`/api/creators/${idNum}`),
    enabled: !isNaN(idNum),
  });

  const minDur = DUR_OPTIONS.find((o) => o.v === dur)!.minSec;
  const minLikes = HOT_OPTIONS.find((o) => o.v === hot)!.minLikes;
  const sinceDays = TIME_OPTIONS.find((o) => o.v === time)!.days;

  const videoParams = useMemo(() => {
    const p = new URLSearchParams();
    if (minDur) p.set('min_dur', String(minDur));
    if (minLikes) p.set('min_likes', String(minLikes));
    if (sinceDays) p.set('since', `${sinceDays}d`);
    if (q) p.set('q', q);
    if (status !== 'all') p.set('status', status);
    p.set('limit', String(PAGE_SIZE));
    p.set('offset', String((page - 1) * PAGE_SIZE));
    return p.toString();
  }, [minDur, minLikes, sinceDays, q, status, page]);

  const summaryParams = useMemo(() => {
    const p = new URLSearchParams();
    if (minDur) p.set('min_dur', String(minDur));
    if (minLikes) p.set('min_likes', String(minLikes));
    if (sinceDays) p.set('since', `${sinceDays}d`);
    if (q) p.set('q', q);
    return p.toString();
  }, [minDur, minLikes, sinceDays, q]);

  const { data: filteredSummary } = useQuery({
    queryKey: ['videos', 'summary', idNum, summaryParams],
    queryFn: () =>
      api.get<VideoSummary>(
        `/api/creators/${idNum}/videos/summary${summaryParams ? `?${summaryParams}` : ''}`,
      ),
    enabled: !isNaN(idNum),
  });

  const { data: overallSummary } = useQuery({
    queryKey: ['videos', 'summary', idNum, 'overall'],
    queryFn: () => api.get<VideoSummary>(`/api/creators/${idNum}/videos/summary`),
    enabled: !isNaN(idNum),
  });

  const { data: videosPage } = useQuery({
    queryKey: ['videos', idNum, videoParams],
    queryFn: () =>
      api.get<ApiPage<Video>>(`/api/creators/${idNum}/videos${videoParams ? `?${videoParams}` : ''}`),
    enabled: !isNaN(idNum),
  });

  const pagedVideos = videosPage?.items ?? [];
  const listTotal = videosPage?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(listTotal / PAGE_SIZE));
  const selectionScope = useMemo(
    () => JSON.stringify({ creatorId, status, dur, hot, time, q }),
    [creatorId, status, dur, hot, time, q],
  );
  const selection = useCrossPageSelection(selectionScope, pagedVideos);
  const pageClamped = Math.min(page, totalPages);
  useEffect(() => {
    if (page !== pageClamped) setPage(pageClamped);
  }, [page, pageClamped]);
  const totalVideos = overallSummary?.total ?? creator?.video_count ?? listTotal;
  const storedVideoCount = overallSummary?.total ?? listTotal;
  const organizedCount = overallSummary?.organized ?? creator?.article_count ?? 0;
  const pendingCount = overallSummary?.pending ?? Math.max(0, totalVideos - organizedCount);
  const backfillMissingCount = Math.max(0, (creator?.video_count ?? 0) - storedVideoCount);
  const filteredTotalVideos = filteredSummary?.total ?? listTotal;
  const filteredOrganizedCount = filteredSummary?.organized ?? 0;
  const filteredPendingCount =
    filteredSummary?.pending ?? Math.max(0, filteredTotalVideos - filteredOrganizedCount);

  const allCbxCls =
    !selection.someOnPageSelected
      ? s.cbx
      : selection.allOnPageSelected
      ? [s.cbx, s.cbxOn].join(' ')
      : [s.cbx, s.cbxIndet].join(' ');

  const submit = useMutation({
    mutationFn: () =>
      api.post<TaskBatchResult>('/api/tasks/batch', {
        video_ids: selection.selectedIds,
        creator_id: idNum,
      }),
    onSuccess: (r) => {
      toast.success(`已创建 ${r.tasks.length} 个任务`);
      qc.invalidateQueries({ queryKey: ['tasks'] });
      navigate('/tasks');
    },
    onError: (err: Error) => toast.error(err.message || '提交失败'),
  });

  const backfillMut = useMutation({
    mutationFn: () =>
      api.post<SystemJobRun>(`/api/system-jobs/creator_backfill/run?creator_id=${idNum}`),
    onSuccess: () => {
      toast.success('已启动后台补齐作品');
      qc.invalidateQueries({ queryKey: ['system-jobs'] });
    },
    onError: (err: Error) => toast.error(err.message || '启动补齐失败'),
  });

  const clearAll = () => {
    setStatus('all');
    setDur('all');
    setHot('all');
    setTime('all');
    setQ('');
  };

  const activeFilters: { k: string; label: string; reset: () => void }[] = [
    ...(status !== 'all'
      ? [
          {
            k: '状态',
            label: STATUS_OPTIONS.find((o) => o.v === status)!.label,
            reset: () => setStatus('all'),
          },
        ]
      : []),
    ...(dur !== 'all'
      ? [
          {
            k: '时长',
            label: DUR_OPTIONS.find((o) => o.v === dur)!.label,
            reset: () => setDur('all'),
          },
        ]
      : []),
    ...(hot !== 'all'
      ? [
          {
            k: '热度',
            label: HOT_OPTIONS.find((o) => o.v === hot)!.label,
            reset: () => setHot('all'),
          },
        ]
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
  ];

  const selCount = selection.selectedCount;

  return (
    <Page>
      <div className={s.crumb}>
        <Link to="/library">← 来源库</Link>
        <span className={s.crumbSep}>/</span>
        <span>{creator?.name ?? '—'}</span>
      </div>

      <PageHead
        title="来源视频库"
        meta={
          <>
            <span>{totalVideos.toLocaleString()} 条视频</span>
            <span>· {organizedCount} 已转文章</span>
            <span>· {pendingCount} 待处理</span>
          </>
        }
      />

      {/* Compact creator card */}
      {creator ? (
        <div className={s.creatorCard}>
          <div className={s.creatorIdentity}>
            <Avatar
              size="lg"
              id={creator.id}
              initial={creator.initial}
              src={creator.avatar_url}
            />
            <div className={s.creatorMain}>
              <div className={s.titleRow}>
                <span className={s.creatorName}>{creator.name}</span>
                <DouyinBadge />
                {creator.verified ? <span className={s.chip}>蓝V</span> : null}
                <span className={[s.chip, s.chipOk].join(' ')}>已转 {organizedCount}</span>
                {pendingCount > 0 ? (
                  <span className={[s.chip, s.chipWarn].join(' ')}>
                    待处理 {pendingCount.toLocaleString()}
                  </span>
                ) : null}
                {creator.external_id ? (
                  <a
                    className={s.chipLink}
                    href={`https://www.douyin.com/user/${creator.external_id}`}
                    target="_blank"
                    rel="noreferrer noopener"
                    title="在抖音打开创作者主页"
                  >
                    <Icon name="external" size={11} />
                    在抖音查看
                  </a>
                ) : null}
                <button
                  className={s.chipButton}
                  disabled={backfillMut.isPending}
                  onClick={() => backfillMut.mutate()}
                  title="后台补齐这个来源尚未入库的作品"
                >
                  <Icon name="refresh" size={11} />
                  {backfillMut.isPending
                    ? '启动中'
                    : backfillMissingCount > 0
                      ? `补齐作品 ${formatCount(backfillMissingCount)}`
                      : '重新补齐'}
                </button>
              </div>
              <div className={s.creatorMeta}>
                <span>{creator.handle}</span>
                {creator.region ? (
                  <>
                    <span className={s.creatorMetaSep}>·</span>
                    <span>IP 属地 · {creator.region}</span>
                  </>
                ) : null}
                {creator.recent_update_at ? (
                  <>
                    <span className={s.creatorMetaSep}>·</span>
                    <span>最近更新 {formatDate(creator.recent_update_at)}</span>
                  </>
                ) : null}
              </div>
              {creator.bio ? <div className={s.creatorBio}>{creator.bio}</div> : null}
            </div>
          </div>
          <div className={s.creatorStats}>
            <div className={s.creatorStat}>
              <b>{formatCount(creator.followers)}</b>
              <span>粉丝</span>
            </div>
            <div className={s.creatorStat}>
              <b>{formatCount(creator.video_count)}</b>
              <span>作品</span>
            </div>
            <div className={s.creatorStat}>
              <b>{formatCount(totalVideos)}</b>
              <span>已抓</span>
            </div>
            <div className={s.creatorStat}>
              <b>{formatCount(creator.total_likes)}</b>
              <span>获赞</span>
            </div>
          </div>
        </div>
      ) : null}

      {/* Filter bar */}
      <div className={s.filterBar}>
        <span className={s.fbLabel}>筛选</span>
        <Dropdown
          id="status"
          k="状态"
          value={status}
          options={[
            { v: 'all', label: '全部', count: filteredTotalVideos },
            { v: 'organized', label: '已转文章', count: filteredOrganizedCount },
            { v: 'pending', label: '待处理', count: filteredPendingCount },
          ]}
          openId={openDrop}
          setOpenId={setOpenDrop}
          onSelect={(v) => setStatus(v)}
        />
        <Dropdown
          id="dur"
          k="时长"
          value={dur}
          options={DUR_OPTIONS.map((o) => ({ v: o.v, label: o.label }))}
          openId={openDrop}
          setOpenId={setOpenDrop}
          onSelect={(v) => setDur(v)}
        />
        <Dropdown
          id="hot"
          k="热度"
          value={hot}
          options={HOT_OPTIONS.map((o) => ({ v: o.v, label: o.label }))}
          openId={openDrop}
          setOpenId={setOpenDrop}
          onSelect={(v) => setHot(v)}
        />
        <Dropdown
          id="time"
          k="时间"
          value={time}
          options={TIME_OPTIONS.map((o) => ({ v: o.v, label: o.label }))}
          openId={openDrop}
          setOpenId={setOpenDrop}
          onSelect={(v) => setTime(v)}
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
            placeholder="搜索视频标题…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <span className={s.fbSpacer} />
        <button className={[s.btn, s.btnGhost].join(' ')} onClick={clearAll}>
          重置
        </button>
        <button
          className={[s.btn, s.btnPrimary].join(' ')}
          disabled={selCount === 0 || submit.isPending}
          onClick={() => submit.mutate()}
        >
          开始处理 {selCount} 条
        </button>
      </div>

      {/* Active filter strip */}
      {activeFilters.length > 0 ? (
        <div className={s.activeStrip}>
          <span className={s.activeLbl}>已选</span>
          {activeFilters.map((f) => (
            <span key={f.k} className={s.activePill}>
              {f.k}:{f.label}
              <button onClick={f.reset} aria-label={`移除${f.k}筛选`}>×</button>
            </span>
          ))}
          <button className={s.activeClear} onClick={clearAll}>
            清除全部
          </button>
        </div>
      ) : null}

      {/* List head */}
      <div className={s.listHead}>
        <h2>
          视频列表
          <span className={s.listHeadMeta} style={{ marginLeft: 6 }}>
            {listTotal.toLocaleString()} 条
          </span>
        </h2>
        <span className={s.listHeadMeta}>
          显示 {listTotal === 0 ? 0 : (pageClamped - 1) * PAGE_SIZE + 1} – {Math.min(pageClamped * PAGE_SIZE, listTotal)} /{' '}
          {listTotal.toLocaleString()} · 按发布时间倒序
        </span>
      </div>

      {/* Table */}
      <div className={s.table}>
        <div className={s.tableScroll}>
          <div className={s.tHead}>
            <span>
              <button className={allCbxCls} onClick={selection.toggleAllOnPage} aria-label="全选" />
            </span>
            <span>视频</span>
            <span>时长</span>
            <span>点赞</span>
            <span>播放</span>
            <span>状态</span>
            <span>发布</span>
            <span>更新</span>
            <span />
          </div>
          {pagedVideos.length === 0 ? (
            <div className={s.emptyBlock}>暂无匹配的视频 · 换个筛选条件</div>
          ) : (
            pagedVideos.map((v, i) => {
              const isSel = selection.isSelected(v.id);
              const isOrganized = Boolean(v.article_id);
              return (
                <div
                  key={v.id}
                  className={[s.tRow, isSel ? s.tRowSelected : ''].join(' ')}
                  onClick={(e) => {
                    const tgt = e.target as HTMLElement;
                    if (tgt.closest('button')) return;
                    if (isOrganized && v.article_id) {
                      navigate(`/articles/${v.article_id}`);
                    } else {
                      selection.toggleOne(v);
                    }
                  }}
                >
                  <span>
                    <button
                      className={[s.cbx, isSel ? s.cbxOn : ''].join(' ')}
                      onClick={(e) => {
                        e.stopPropagation();
                        selection.toggleOne(v);
                      }}
                      aria-label="选择"
                    />
                  </span>
                  <div className={s.videoCell}>
                    <VideoThumb src={v.cover_url} seed={i + idNum} />
                    <div className={s.videoText}>
                      <span className={s.videoTitle}>{v.title}</span>
                      <span className={s.videoId}>ID {v.id}</span>
                    </div>
                  </div>
                  <span className={s.num}>{formatDuration(v.duration_sec)}</span>
                  <span className={s.num}>{formatCount(v.likes)}</span>
                  <span className={s.num}>{formatCount(v.plays)}</span>
                  <span className={isOrganized ? s.stDone : s.stPending}>
                    {isOrganized ? '已转文章' : '待处理'}
                  </span>
                  <span className={s.dateCell}>{formatDate(v.published_at)}</span>
                  <span className={s.dateCell}>
                    {v.updated_at ? formatDateTime(v.updated_at) : '—'}
                  </span>
                  <a
                    className={s.vidExtBtn}
                    href={v.source_url}
                    target="_blank"
                    rel="noreferrer noopener"
                    title="在抖音打开"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <Icon name="external" size={12} />
                  </a>
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
            <button disabled={pageClamped <= 1} onClick={() => setPage(pageClamped - 1)}>
              ‹
            </button>
            {buildPageNumbers(pageClamped, totalPages).map((p, i) =>
              p === '...' ? (
                <button key={`e${i}`} disabled>
                  …
                </button>
              ) : (
                <button
                  key={p}
                  className={p === pageClamped ? s.pagerBtnOn : ''}
                  onClick={() => setPage(p)}
                >
                  {p}
                </button>
              ),
            )}
            <button
              disabled={pageClamped >= totalPages}
              onClick={() => setPage(pageClamped + 1)}
            >
              ›
            </button>
          </div>
        </div>
      ) : null}

      {/* Sticky dark selection bar */}
      {selCount > 0 ? (
        <div className={s.stickyBar}>
          <span className={s.stickyCount}>
            <b>{selCount}</b>条已选中 · 当前页 {selection.pageSelectedCount}
          </span>
          <span className={s.stickySpacer} />
          <button className={s.stickyGhost} onClick={selection.clearSelection}>
            取消选择
          </button>
          <button
            className={s.stickyPrimary}
            disabled={submit.isPending}
            onClick={() => submit.mutate()}
          >
            开始处理 <Icon name="arrow-right" size={12} />
          </button>
        </div>
      ) : null}
    </Page>
  );
}
