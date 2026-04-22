import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Page, PageHead } from '@/layouts/AppShell';
import { ArtHead, ArtRow, ArtTable } from '@/components/ArtRow/ArtRow';
import { Avatar, Button, Chip, Icon, Thumb } from '@/components/primitives';
import { api, apiUrl } from '@/lib/api';
import { formatCount, formatDate, formatDateTime, formatDuration } from '@/lib/format';
import type { Creator, Page as ApiPage, Task, Video } from '@/types/api';
import s from './Import.module.css';

type StatusFilter = 'all' | 'organized' | 'pending';
type DurationFilter = 'all' | '20s' | '60s' | '180s' | '600s';
type LikesFilter = 'all' | '1000' | '10000' | '50000';
type RecencyFilter = 'all' | '7d' | '30d' | '90d';
type FilterState = {
  status: StatusFilter;
  duration: DurationFilter;
  likes: LikesFilter;
  recency: RecencyFilter;
};
type FilterMenuKey = 'status' | 'duration' | 'likes' | 'recency' | null;
type FilterDropdownOption = {
  value: string;
  label: string;
  count: number;
};

const PAGE_SIZE = 40;

const DURATION_OPTIONS: Array<{
  value: DurationFilter;
  label: string;
  hint: string;
  minSec: number;
}> = [
  { value: 'all', label: '全部', hint: '不限制视频长短', minSec: 0 },
  { value: '20s', label: '20 秒+', hint: '推荐先过滤碎片内容', minSec: 20 },
  { value: '60s', label: '1 分钟+', hint: '保留更完整的表达', minSec: 60 },
  { value: '180s', label: '3 分钟+', hint: '更适合直接转文', minSec: 180 },
  { value: '600s', label: '10 分钟+', hint: '优先看长篇内容', minSec: 600 },
];

const LIKES_OPTIONS: Array<{
  value: LikesFilter;
  label: string;
  hint: string;
  minLikes: number;
}> = [
  { value: 'all', label: '全部', hint: '不过滤互动强度', minLikes: 0 },
  { value: '1000', label: '1k+ 点赞', hint: '保留有基础反馈的视频', minLikes: 1_000 },
  { value: '10000', label: '1w+ 点赞', hint: '筛高反馈内容', minLikes: 10_000 },
  { value: '50000', label: '5w+ 点赞', hint: '只看爆款候选', minLikes: 50_000 },
];

const RECENCY_OPTIONS: Array<{
  value: RecencyFilter;
  label: string;
  hint: string;
  days: number | null;
}> = [
  { value: 'all', label: '全部', hint: '不过滤发布时间', days: null },
  { value: '7d', label: '近 7 天', hint: '追最新内容波动', days: 7 },
  { value: '30d', label: '近 30 天', hint: '兼顾新内容样本量', days: 30 },
  { value: '90d', label: '近 90 天', hint: '回看近期沉淀内容', days: 90 },
];

function findDurationOption(value: DurationFilter) {
  return DURATION_OPTIONS.find((option) => option.value === value) ?? DURATION_OPTIONS[0];
}

function findLikesOption(value: LikesFilter) {
  return LIKES_OPTIONS.find((option) => option.value === value) ?? LIKES_OPTIONS[0];
}

function findRecencyOption(value: RecencyFilter) {
  return RECENCY_OPTIONS.find((option) => option.value === value) ?? RECENCY_OPTIONS[0];
}

function matchesQuery(video: Video, query: string) {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return video.title.toLowerCase().includes(needle) || video.id.toLowerCase().includes(needle);
}

function matchesVideo(video: Video, filters: FilterState, now: number, query: string) {
  const durationMinSec = findDurationOption(filters.duration).minSec;
  const likesMin = findLikesOption(filters.likes).minLikes;
  const recencyDays = findRecencyOption(filters.recency).days;

  if (!matchesQuery(video, query)) return false;
  if (durationMinSec && video.duration_sec < durationMinSec) return false;
  if (likesMin && video.likes < likesMin) return false;
  if (recencyDays) {
    const cutoff = now - recencyDays * 86_400_000;
    if (Date.parse(video.published_at) < cutoff) return false;
  }
  if (filters.status === 'organized' && !video.article_id) return false;
  if (filters.status === 'pending' && video.article_id) return false;
  return true;
}

function buildPageItems(current: number, total: number): Array<number | 'ellipsis'> {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  if (current <= 4) return [1, 2, 3, 4, 5, 'ellipsis', total];
  if (current >= total - 3) return [1, 'ellipsis', total - 4, total - 3, total - 2, total - 1, total];
  return [1, 'ellipsis', current - 1, current, current + 1, 'ellipsis', total];
}

function FilterDropdown({
  label,
  selectedLabel,
  selectedCount,
  open,
  options,
  onToggle,
  onSelect,
}: {
  label: string;
  selectedLabel: string;
  selectedCount: number;
  open: boolean;
  options: FilterDropdownOption[];
  onToggle: () => void;
  onSelect: (value: string) => void;
}) {
  return (
    <div
      className={[s.fdrop, open ? s.fdropOpen : ''].filter(Boolean).join(' ')}
      onClick={(e) => e.stopPropagation()}
    >
      <button type="button" className={s.fdropButton} onClick={onToggle}>
        <span className={s.fdropKey}>{label}</span>
        <span>{selectedLabel}</span>
        <span className={s.fdropValue}>{selectedCount.toLocaleString()}</span>
        <Icon name="chevron" size={11} className={s.fdropCaret} />
      </button>

      <div className={s.fdropMenu}>
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            className={[
              s.fdropItem,
              option.label === selectedLabel ? s.fdropItemActive : '',
            ]
              .filter(Boolean)
              .join(' ')}
            onClick={() => onSelect(option.value)}
          >
            <span>{option.label}</span>
            <span className={s.fdropItemCount}>{option.count.toLocaleString()}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function ImportPage() {
  const { creatorId = '' } = useParams<{ creatorId: string }>();
  const idNum = Number(creatorId);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [durationFilter, setDurationFilter] = useState<DurationFilter>('all');
  const [likesFilter, setLikesFilter] = useState<LikesFilter>('all');
  const [recencyFilter, setRecencyFilter] = useState<RecencyFilter>('all');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [openMenu, setOpenMenu] = useState<FilterMenuKey>(null);
  const [bioExpanded, setBioExpanded] = useState(false);

  const { data: creator, isFetching: creatorFetching } = useQuery({
    queryKey: ['creator', idNum],
    queryFn: () => api.get<Creator>(`/api/creators/${idNum}`),
    enabled: !isNaN(idNum),
  });

  const { data: videosPage, isFetching: videosFetching } = useQuery({
    queryKey: ['videos', idNum],
    queryFn: () => api.get<ApiPage<Video>>(`/api/creators/${idNum}/videos`),
    enabled: !isNaN(idNum),
  });

  const videos = useMemo(() => videosPage?.items ?? [], [videosPage]);
  const organizedCount = useMemo(
    () => videos.filter((v) => Boolean(v.article_id)).length,
    [videos],
  );
  const pendingCount = Math.max(0, videos.length - organizedCount);

  useEffect(() => {
    if (!openMenu) return undefined;
    const close = () => setOpenMenu(null);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
    };
    document.addEventListener('click', close);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('click', close);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [openMenu]);

  const filterStats = useMemo(() => {
    const now = Date.now();
    const countMatches = (filters: FilterState) =>
      videos.reduce((count, video) => count + (matchesVideo(video, filters, now, query) ? 1 : 0), 0);

    return {
      statusCounts: {
        all: countMatches({
          status: 'all',
          duration: durationFilter,
          likes: likesFilter,
          recency: recencyFilter,
        }),
        organized: countMatches({
          status: 'organized',
          duration: durationFilter,
          likes: likesFilter,
          recency: recencyFilter,
        }),
        pending: countMatches({
          status: 'pending',
          duration: durationFilter,
          likes: likesFilter,
          recency: recencyFilter,
        }),
      } satisfies Record<StatusFilter, number>,
      durationCounts: {
        all: countMatches({
          status: statusFilter,
          duration: 'all',
          likes: likesFilter,
          recency: recencyFilter,
        }),
        '20s': countMatches({
          status: statusFilter,
          duration: '20s',
          likes: likesFilter,
          recency: recencyFilter,
        }),
        '60s': countMatches({
          status: statusFilter,
          duration: '60s',
          likes: likesFilter,
          recency: recencyFilter,
        }),
        '180s': countMatches({
          status: statusFilter,
          duration: '180s',
          likes: likesFilter,
          recency: recencyFilter,
        }),
        '600s': countMatches({
          status: statusFilter,
          duration: '600s',
          likes: likesFilter,
          recency: recencyFilter,
        }),
      } satisfies Record<DurationFilter, number>,
      likesCounts: {
        all: countMatches({
          status: statusFilter,
          duration: durationFilter,
          likes: 'all',
          recency: recencyFilter,
        }),
        '1000': countMatches({
          status: statusFilter,
          duration: durationFilter,
          likes: '1000',
          recency: recencyFilter,
        }),
        '10000': countMatches({
          status: statusFilter,
          duration: durationFilter,
          likes: '10000',
          recency: recencyFilter,
        }),
        '50000': countMatches({
          status: statusFilter,
          duration: durationFilter,
          likes: '50000',
          recency: recencyFilter,
        }),
      } satisfies Record<LikesFilter, number>,
      recencyCounts: {
        all: countMatches({
          status: statusFilter,
          duration: durationFilter,
          likes: likesFilter,
          recency: 'all',
        }),
        '7d': countMatches({
          status: statusFilter,
          duration: durationFilter,
          likes: likesFilter,
          recency: '7d',
        }),
        '30d': countMatches({
          status: statusFilter,
          duration: durationFilter,
          likes: likesFilter,
          recency: '30d',
        }),
        '90d': countMatches({
          status: statusFilter,
          duration: durationFilter,
          likes: likesFilter,
          recency: '90d',
        }),
      } satisfies Record<RecencyFilter, number>,
    };
  }, [durationFilter, likesFilter, query, recencyFilter, statusFilter, videos]);

  const visibleVideos = useMemo(() => {
    const now = Date.now();
    return videos
      .filter((video) =>
        matchesVideo(
          video,
          {
            status: statusFilter,
            duration: durationFilter,
            likes: likesFilter,
            recency: recencyFilter,
          },
          now,
          query,
        ),
      )
      .sort((a, b) => Date.parse(b.published_at) - Date.parse(a.published_at));
  }, [durationFilter, likesFilter, query, recencyFilter, statusFilter, videos]);

  useEffect(() => {
    setPage(1);
  }, [creatorId, durationFilter, likesFilter, query, recencyFilter, statusFilter]);

  useEffect(() => {
    setSelected(new Set());
  }, [creatorId]);

  useEffect(() => {
    setBioExpanded(false);
  }, [creatorId]);

  useEffect(() => {
    setSelected((prev) => {
      if (prev.size === 0) return prev;
      const allowed = new Set(videos.map((video) => video.id));
      const next = new Set(Array.from(prev).filter((id) => allowed.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [videos]);

  const filteredTotal = visibleVideos.length;
  const fetchedTotal = videosPage?.total ?? videos.length;
  const profileTotal = creator?.video_count ?? fetchedTotal;
  const totalPages = Math.max(1, Math.ceil(filteredTotal / PAGE_SIZE));

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const pageStart = filteredTotal === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const pageEnd = filteredTotal === 0 ? 0 : Math.min(page * PAGE_SIZE, filteredTotal);
  const pageVideos = useMemo(
    () => visibleVideos.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [page, visibleVideos],
  );
  const pageItems = useMemo(() => buildPageItems(page, totalPages), [page, totalPages]);

  const allSelected = pageVideos.length > 0 && pageVideos.every((v) => selected.has(v.id));
  const toggleAll = () => {
    if (allSelected) {
      const next = new Set(selected);
      pageVideos.forEach((v) => next.delete(v.id));
      setSelected(next);
      return;
    }
    setSelected((prev) => {
      const next = new Set(prev);
      pageVideos.forEach((v) => next.add(v.id));
      return next;
    });
  };

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  const submit = useMutation({
    mutationFn: () =>
      api.post<{ tasks: Task[] }>('/api/tasks/batch', {
        creator_id: idNum,
        video_ids: Array.from(selected),
      }),
    onSuccess: (res) => {
      toast.success(`已创建 ${res.tasks.length} 个任务`);
      qc.invalidateQueries({ queryKey: ['tasks'] });
      navigate('/');
    },
    onError: (err: Error) => toast.error(err.message || '提交失败'),
  });

  const activeFilters = [
    query.trim() ? `搜索: ${query.trim()}` : null,
    statusFilter !== 'all'
      ? statusFilter === 'organized'
        ? '状态: 已转文章'
        : '状态: 未转文章'
      : null,
    durationFilter !== 'all' ? `时长: ${findDurationOption(durationFilter).label}` : null,
    likesFilter !== 'all' ? `热度: ${findLikesOption(likesFilter).label}` : null,
    recencyFilter !== 'all' ? `时间: ${findRecencyOption(recencyFilter).label}` : null,
  ].filter(Boolean) as string[];
  const hasActiveFilters = activeFilters.length > 0;

  const resetFilters = () => {
    setStatusFilter('all');
    setDurationFilter('all');
    setLikesFilter('all');
    setRecencyFilter('all');
    setQuery('');
  };

  const discrepancy = Math.max(0, profileTotal - fetchedTotal);
  const refreshData = async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ['creator', idNum] }),
      qc.invalidateQueries({ queryKey: ['videos', idNum] }),
      qc.invalidateQueries({ queryKey: ['creators'] }),
    ]);
    toast.success('已刷新创作者信息和视频列表');
  };

  const copyShareLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast.success('已复制当前页面链接');
    } catch {
      toast.error('复制链接失败');
    }
  };

  const statusOptions: FilterDropdownOption[] = [
    { value: 'all', label: '全部', count: filterStats.statusCounts.all },
    { value: 'organized', label: '已转文章', count: filterStats.statusCounts.organized },
    { value: 'pending', label: '待处理', count: filterStats.statusCounts.pending },
  ];
  const durationOptions: FilterDropdownOption[] = DURATION_OPTIONS.map((option) => ({
    value: option.value,
    label: option.label,
    count: filterStats.durationCounts[option.value],
  }));
  const likesOptions: FilterDropdownOption[] = LIKES_OPTIONS.map((option) => ({
    value: option.value,
    label: option.label,
    count: filterStats.likesCounts[option.value],
  }));
  const recencyOptions: FilterDropdownOption[] = RECENCY_OPTIONS.map((option) => ({
    value: option.value,
    label: option.label,
    count: filterStats.recencyCounts[option.value],
  }));

  return (
    <Page>
      <PageHead
        title="创作者视频库"
        meta={
          <>
            <Link to="/library" className={s.headLink}>
              返回博主库
            </Link>
            {creator ? <span>{creator.name}</span> : null}
            <span>
              {fetchedTotal.toLocaleString()} 条视频 · {organizedCount.toLocaleString()} 已转文章 ·{' '}
              {pendingCount.toLocaleString()} 待处理
            </span>
          </>
        }
      />

      {creator ? (
        <section className={s.creatorCard}>
          <div className={s.avatarFrame}>
            <Avatar
              size="lg"
              id={creator.id}
              initial={creator.initial}
              src={creator.avatar_url}
              className={s.heroAvatar}
            />
          </div>

          <div className={s.creatorMain}>
            <div className={s.creatorTitleRow}>
              <h2 className={s.creatorName}>{creator.name}</h2>
              {creator.verified ? <Chip variant="ok">蓝V</Chip> : <Chip>抖音</Chip>}
              {organizedCount > 0 ? <Chip variant="ok">已转 {organizedCount.toLocaleString()}</Chip> : null}
              {pendingCount > 0 ? <Chip>待处理 {pendingCount.toLocaleString()}</Chip> : null}
            </div>

            <div className={s.creatorMeta}>
              <span>{creator.handle}</span>
              <span className={s.sep}>·</span>
              <span>IP 属地 {creator.region ?? '未知'}</span>
              {creator.recent_update_at ? (
                <>
                  <span className={s.sep}>·</span>
                  <span>最近更新 {formatDate(creator.recent_update_at)}</span>
                </>
              ) : null}
            </div>

            {creator.bio ? (
              <div className={s.creatorBioWrap}>
                <p className={[s.creatorBio, bioExpanded ? s.creatorBioExpanded : ''].filter(Boolean).join(' ')}>
                  {creator.bio}
                </p>
                {creator.bio.length > 24 ? (
                  <button
                    type="button"
                    className={s.creatorBioToggle}
                    onClick={() => setBioExpanded((value) => !value)}
                  >
                    {bioExpanded ? '收起' : '展开全文'}
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className={s.creatorStats}>
            <div className={s.stat}>
              <b className={s.statValue}>{formatCount(creator.followers)}</b>
              <span className={s.statLabel}>粉丝</span>
            </div>
            <div className={s.stat}>
              <b className={s.statValue}>{formatCount(profileTotal)}</b>
              <span className={s.statLabel}>主页作品</span>
            </div>
            <div className={s.stat}>
              <b className={s.statValue}>{formatCount(fetchedTotal)}</b>
              <span className={s.statLabel}>已抓视频</span>
            </div>
            <div className={s.stat}>
              <b className={s.statValue}>{formatCount(creator.total_likes)}</b>
              <span className={s.statLabel}>获赞</span>
            </div>
          </div>

          <div className={s.creatorActions}>
            <Button size="sm" icon={<Icon name="refresh" size={12} />} onClick={refreshData} disabled={creatorFetching || videosFetching}>
              刷新
            </Button>
            <Button size="sm" icon={<Icon name="external" size={12} />} onClick={copyShareLink}>
              复制链接
            </Button>
          </div>

          {discrepancy > 0 ? (
            <div className={s.creatorNote}>主页显示比可处理列表多 {discrepancy.toLocaleString()} 条，通常是图文或不可处理条目。</div>
          ) : null}
        </section>
      ) : null}

      <section className={s.filterBar}>
        <FilterDropdown
          label="状态"
          selectedLabel={
            statusFilter === 'organized'
              ? '已转文章'
              : statusFilter === 'pending'
                ? '待处理'
                : '全部'
          }
          selectedCount={filterStats.statusCounts[statusFilter]}
          open={openMenu === 'status'}
          options={statusOptions}
          onToggle={() => setOpenMenu((prev) => (prev === 'status' ? null : 'status'))}
          onSelect={(value) => {
            setStatusFilter(value as StatusFilter);
            setOpenMenu(null);
          }}
        />
        <FilterDropdown
          label="时长"
          selectedLabel={findDurationOption(durationFilter).label}
          selectedCount={filterStats.durationCounts[durationFilter]}
          open={openMenu === 'duration'}
          options={durationOptions}
          onToggle={() => setOpenMenu((prev) => (prev === 'duration' ? null : 'duration'))}
          onSelect={(value) => {
            setDurationFilter(value as DurationFilter);
            setOpenMenu(null);
          }}
        />
        <FilterDropdown
          label="热度"
          selectedLabel={findLikesOption(likesFilter).label}
          selectedCount={filterStats.likesCounts[likesFilter]}
          open={openMenu === 'likes'}
          options={likesOptions}
          onToggle={() => setOpenMenu((prev) => (prev === 'likes' ? null : 'likes'))}
          onSelect={(value) => {
            setLikesFilter(value as LikesFilter);
            setOpenMenu(null);
          }}
        />
        <FilterDropdown
          label="时间"
          selectedLabel={findRecencyOption(recencyFilter).label}
          selectedCount={filterStats.recencyCounts[recencyFilter]}
          open={openMenu === 'recency'}
          options={recencyOptions}
          onToggle={() => setOpenMenu((prev) => (prev === 'recency' ? null : 'recency'))}
          onSelect={(value) => {
            setRecencyFilter(value as RecencyFilter);
            setOpenMenu(null);
          }}
        />

        <div className={s.spacer} />

        <label className={s.search}>
          <Icon name="search" size={13} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索标题或视频 ID"
          />
        </label>

        <Button size="sm" disabled={!hasActiveFilters} onClick={resetFilters}>
          重置
        </Button>
        <Button
          variant="primary"
          size="sm"
          disabled={selected.size === 0 || submit.isPending}
          onClick={() => submit.mutate()}
          trailing={<Icon name="arrow-right" size={12} />}
        >
          开始处理 {selected.size} 条
        </Button>
      </section>

      <div className={s.activeStrip}>
        <span className={s.activeLabel}>当前筛选</span>
        {hasActiveFilters ? (
          activeFilters.map((item) => (
            <span key={item} className={s.activePill}>
              {item}
            </span>
          ))
        ) : (
          <span className={s.activeEmpty}>未启用额外筛选</span>
        )}
        <span className={s.activeSelection}>{selected.size} 条已选中</span>
      </div>

      <section className={s.listSection}>
        <div className={s.listHead}>
          <div className={s.listTitle}>视频列表</div>
          <div className={s.listMeta}>
            {filteredTotal === 0
              ? '没有匹配结果'
              : `显示 ${pageStart}-${pageEnd} / ${filteredTotal.toLocaleString()} · 按发布时间倒序`}
          </div>
        </div>

        <ArtTable className={s.tableCard}>
          <ArtHead>
            <ArtHead.Cell style={{ width: 24, flex: '0 0 24px' }}>
              <input type="checkbox" checked={allSelected} onChange={toggleAll} />
            </ArtHead.Cell>
            <ArtHead.Cell flex={2.8}>视频</ArtHead.Cell>
            <ArtHead.Cell flex={0.7} align="right">
              时长 ⇅
            </ArtHead.Cell>
            <ArtHead.Cell flex={0.8} align="right">
              点赞 ▼
            </ArtHead.Cell>
            <ArtHead.Cell flex={0.8} align="right">
              播放 ⇅
            </ArtHead.Cell>
            <ArtHead.Cell flex={1} align="right">
              状态
            </ArtHead.Cell>
            <ArtHead.Cell flex={0.9} align="right">
              发布 ▼
            </ArtHead.Cell>
            <ArtHead.Cell flex={1.2} align="right">
              更新
            </ArtHead.Cell>
          </ArtHead>

          {pageVideos.map((video, index) => (
            <ArtRow
              key={video.id}
              onClick={(event) => {
                if ((event.target as HTMLElement).tagName === 'INPUT') return;
                toggle(video.id);
              }}
            >
              <ArtRow.C style={{ width: 24, flex: '0 0 24px' }}>
                <input
                  type="checkbox"
                  checked={selected.has(video.id)}
                  onChange={() => toggle(video.id)}
                  onClick={(event) => event.stopPropagation()}
                />
              </ArtRow.C>

              <ArtRow.T flex={2.8}>
                <Thumb seed={index} w={68} h={44} play src={video.cover_url} />
                <div className={s.videoMeta}>
                  <ArtRow.Ellipsis>
                    <strong className={s.videoTitle}>{video.title}</strong>
                  </ArtRow.Ellipsis>
                  <div className={s.videoSubline}>
                    <span>ID {video.id}</span>
                    <span>评 {formatCount(video.comments)}</span>
                    <span>转 {formatCount(video.shares)}</span>
                    <span>藏 {formatCount(video.collects)}</span>
                    <a
                      href={video.source_url}
                      target="_blank"
                      rel="noreferrer"
                      onClick={(event) => event.stopPropagation()}
                      className={s.videoLink}
                    >
                      原视频
                      <Icon name="external" size={11} />
                    </a>
                    {video.media_url ? (
                      <a
                        href={apiUrl(video.media_url)}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(event) => event.stopPropagation()}
                        className={s.videoLink}
                      >
                        OSS 存档
                        <Icon name="external" size={11} />
                      </a>
                    ) : null}
                  </div>
                </div>
              </ArtRow.T>

              <ArtRow.Num flex={0.7}>{formatDuration(video.duration_sec)}</ArtRow.Num>
              <ArtRow.Num flex={0.8}>{formatCount(video.likes)}</ArtRow.Num>
              <ArtRow.Num flex={0.8}>{formatCount(video.plays)}</ArtRow.Num>
              <ArtRow.Mono flex={1} align="right">
                {video.article_id ? (
                  <Link
                    to={`/articles/${video.article_id}`}
                    onClick={(event) => event.stopPropagation()}
                    className={s.statusLink}
                  >
                    <Chip variant="ok">已转文章</Chip>
                  </Link>
                ) : (
                  <Chip>未转文章</Chip>
                )}
              </ArtRow.Mono>
              <ArtRow.Mono flex={0.9} align="right">
                {formatDate(video.published_at)}
              </ArtRow.Mono>
              <ArtRow.Mono flex={1.2} align="right">
                {formatDateTime(video.updated_at)}
              </ArtRow.Mono>
            </ArtRow>
          ))}

          {pageVideos.length === 0 ? (
            <div className={s.emptyState}>暂无视频 · 换一个筛选条件试试</div>
          ) : null}
        </ArtTable>

        <div className={s.pagination}>
          <div className={s.paginationSummary}>共 {totalPages} 页 · 每页 {PAGE_SIZE} 条</div>

          <div className={s.paginationControls}>
            <button
              type="button"
              className={s.pageButton}
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              ‹
            </button>

            {pageItems.map((item, index) =>
              item === 'ellipsis' ? (
                <span key={`ellipsis-${index}`} className={s.pageEllipsis}>
                  …
                </span>
              ) : (
                <button
                  key={item}
                  type="button"
                  className={[s.pageButton, item === page ? s.pageCurrent : ''].filter(Boolean).join(' ')}
                  onClick={() => setPage(item)}
                >
                  {item}
                </button>
              ),
            )}

            <button
              type="button"
              className={s.pageButton}
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              ›
            </button>
          </div>
        </div>
      </section>

      {selected.size > 0 ? (
        <div className={s.selectionDock}>
          <div className={s.selectionMeta}>
            <span className={s.selectionCount}>{selected.size} 条已选中</span>
            <span className={s.selectionHint}>
              当前结果 {filteredTotal.toLocaleString()} 条 · 当前页 {pageVideos.length} 条
            </span>
          </div>
          <div className={s.selectionActions}>
            <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
              取消选择
            </Button>
            <Button
              variant="primary"
              size="sm"
              disabled={submit.isPending}
              onClick={() => submit.mutate()}
              trailing={<Icon name="arrow-right" size={12} />}
            >
              开始处理
            </Button>
          </div>
        </div>
      ) : null}
    </Page>
  );
}
