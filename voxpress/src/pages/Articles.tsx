import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Page, PageHead } from '@/layouts/AppShell';
import { ArtHead, ArtRow, ArtTable } from '@/components/ArtRow/ArtRow';
import { Avatar, Button, Chip, Icon, Input, Thumb } from '@/components/primitives';
import { api } from '@/lib/api';
import { formatCount, formatRelative } from '@/lib/format';
import type { Article, ArticleBatchResult, Creator, Page as ApiPage } from '@/types/api';
import s from './Articles.module.css';

type SinceFilter = 'all' | '7d' | '30d' | '90d';

const SINCE_OPTIONS: Array<{ value: SinceFilter; label: string }> = [
  { value: 'all', label: '全部时间' },
  { value: '7d', label: '近 7 天' },
  { value: '30d', label: '近 30 天' },
  { value: '90d', label: '近 90 天' },
];

export function ArticlesPage() {
  const [q, setQ] = useState('');
  const [creatorFilter, setCreatorFilter] = useState<'all' | string>('all');
  const [tagFilter, setTagFilter] = useState<'all' | string>('all');
  const [sinceFilter, setSinceFilter] = useState<SinceFilter>('all');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const navigate = useNavigate();
  const qc = useQueryClient();

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

  const { data } = useQuery({
    queryKey: ['articles', { q, creatorFilter, tagFilter, sinceFilter }],
    queryFn: () => {
      const params = new URLSearchParams();
      if (q.trim()) params.set('q', q.trim());
      if (creatorFilter !== 'all') params.set('creator_id', creatorFilter);
      if (tagFilter !== 'all') params.set('tag', tagFilter);
      if (sinceFilter !== 'all') params.set('since', sinceFilter);
      params.set('limit', '200');
      const qs = params.toString();
      return api.get<ApiPage<Article>>(`/api/articles${qs ? `?${qs}` : ''}`);
    },
  });

  const articles = data?.items ?? [];
  const total = data?.total ?? articles.length;
  const creatorOptions = creatorsPage?.items ?? [];

  useEffect(() => {
    setSelected((prev) => {
      if (prev.size === 0) return prev;
      const allowed = new Set(articles.map((article) => article.id));
      const next = new Set(Array.from(prev).filter((id) => allowed.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [articles]);

  const tagOptions = useMemo(() => {
    const counts = new Map<string, number>();
    articles.forEach((article) => {
      article.tags.forEach((tag) => counts.set(tag, (counts.get(tag) ?? 0) + 1));
    });
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8);
  }, [articles]);

  const hasFilters =
    creatorFilter !== 'all' || tagFilter !== 'all' || sinceFilter !== 'all' || q.trim().length > 0;
  const allSelected = articles.length > 0 && articles.every((article) => selected.has(article.id));

  const toggleSelected = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (allSelected) {
      setSelected(new Set());
      return;
    }
    setSelected(new Set(articles.map((article) => article.id)));
  };

  const batchDelete = useMutation({
    mutationFn: () =>
      api.post<ArticleBatchResult>('/api/articles/batch/delete', {
        article_ids: Array.from(selected),
      }),
    onSuccess: (res) => {
      toast.success(`已删除 ${res.processed} 篇文章`);
      setSelected(new Set());
      qc.invalidateQueries({ queryKey: ['articles'] });
      qc.invalidateQueries({ queryKey: ['creators'] });
    },
    onError: (err: Error) => toast.error(err.message || '批量删除失败'),
  });

  const batchRebuild = useMutation({
    mutationFn: () =>
      api.post<ArticleBatchResult>('/api/articles/batch/rebuild', {
        article_ids: Array.from(selected),
      }),
    onSuccess: (res) => {
      toast.success(`已加入 ${res.processed} 篇文章的重新整理队列`);
      setSelected(new Set());
      qc.invalidateQueries({ queryKey: ['tasks'] });
    },
    onError: (err: Error) => toast.error(err.message || '批量重新整理失败'),
  });

  return (
    <Page>
      <PageHead
        title="文章列表"
        meta={
          <>
            <span>{total} 篇已整理</span>
            <span>· 支持按创作者、标签、时间筛选</span>
          </>
        }
      />

      <section className={s.toolbar}>
        <div className={s.toolbarTop}>
          <div className={s.toolbarSummary}>
            <Chip variant="solid">{total} 篇</Chip>
            <Chip variant="accent">封面使用原视频首图</Chip>
            {creatorFilter !== 'all' ? <Chip>创作者 {creatorMap.get(Number(creatorFilter))?.name}</Chip> : null}
            {tagFilter !== 'all' ? <Chip>标签 #{tagFilter}</Chip> : null}
            {sinceFilter !== 'all' ? <Chip>{SINCE_OPTIONS.find((item) => item.value === sinceFilter)?.label}</Chip> : null}
          </div>

          <div className={s.searchWrap}>
            <Input
              leading={<Icon name="search" size={14} />}
              placeholder="搜索标题、摘要或正文关键词"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
        </div>

        <div className={s.filterGrid}>
          <div className={s.filterGroup}>
            <div className={s.filterLabel}>创作者</div>
            <div className={s.filterRow}>
              <button
                type="button"
                className={[s.filterChip, creatorFilter === 'all' ? s.filterChipActive : ''].filter(Boolean).join(' ')}
                onClick={() => setCreatorFilter('all')}
              >
                全部
              </button>
              {creatorOptions.map((creator) => (
                <button
                  key={creator.id}
                  type="button"
                  className={[s.filterChip, creatorFilter === String(creator.id) ? s.filterChipActive : '']
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => setCreatorFilter(String(creator.id))}
                >
                  {creator.name}
                </button>
              ))}
            </div>
          </div>

          <div className={s.filterGroup}>
            <div className={s.filterLabel}>发布时间</div>
            <div className={s.filterRow}>
              {SINCE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={[s.filterChip, sinceFilter === option.value ? s.filterChipActive : '']
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => setSinceFilter(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <div className={s.filterGroup}>
            <div className={s.filterLabel}>高频标签</div>
            <div className={s.filterRow}>
              <button
                type="button"
                className={[s.filterChip, tagFilter === 'all' ? s.filterChipActive : ''].filter(Boolean).join(' ')}
                onClick={() => setTagFilter('all')}
              >
                全部标签
              </button>
              {tagOptions.map(([tag, count]) => (
                <button
                  key={tag}
                  type="button"
                  className={[s.filterChip, tagFilter === tag ? s.filterChipActive : ''].filter(Boolean).join(' ')}
                  onClick={() => setTagFilter(tag)}
                >
                  #{tag}
                  <span className={s.filterCount}>{count}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className={s.toolbarFoot}>
          <span className={s.toolbarMeta}>
            当前结果 {articles.length} 篇{hasFilters ? ' · 已启用筛选' : ' · 未启用额外筛选'}
          </span>
          <div className={s.toolbarActions}>
            <Chip variant={selected.size > 0 ? 'solid' : 'default'}>{selected.size} 篇已选</Chip>
            <Button
              size="sm"
              disabled={selected.size === 0 || batchRebuild.isPending}
              onClick={() => {
                if (confirm(`确认将选中的 ${selected.size} 篇文章重新加入整理队列？`)) {
                  batchRebuild.mutate();
                }
              }}
            >
              重新整理
            </Button>
            <Button
              size="sm"
              disabled={selected.size === 0 || batchDelete.isPending}
              onClick={() => {
                if (confirm(`确认删除选中的 ${selected.size} 篇文章？此操作不可恢复。`)) {
                  batchDelete.mutate();
                }
              }}
            >
              删除
            </Button>
            <Button
              size="sm"
              disabled={!hasFilters}
              onClick={() => {
                setQ('');
                setCreatorFilter('all');
                setTagFilter('all');
                setSinceFilter('all');
              }}
            >
              重置筛选
            </Button>
          </div>
        </div>
      </section>

      <ArtTable className={s.table}>
        <ArtHead>
          <ArtHead.Cell style={{ width: 24, flex: '0 0 24px' }}>
            <input type="checkbox" checked={allSelected} onChange={toggleAll} />
          </ArtHead.Cell>
          <ArtHead.Cell flex={3.2}>文章</ArtHead.Cell>
          <ArtHead.Cell flex={1.1}>博主</ArtHead.Cell>
          <ArtHead.Cell flex={1.3}>标签</ArtHead.Cell>
          <ArtHead.Cell flex={0.7} align="right">
            字数
          </ArtHead.Cell>
          <ArtHead.Cell flex={0.8} align="right">
            点赞
          </ArtHead.Cell>
          <ArtHead.Cell flex={0.9} align="right">
            日期
          </ArtHead.Cell>
        </ArtHead>

        {articles.map((article, index) => {
          const creator = creatorMap.get(article.creator_id);
          return (
            <ArtRow
              key={article.id}
              onClick={(e) => {
                const target = e.target as HTMLElement;
                if (target.closest('input') || target.closest('button') || target.closest('a')) return;
                navigate(`/articles/${article.id}`);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') navigate(`/articles/${article.id}`);
              }}
            >
              <ArtRow.C style={{ width: 24, flex: '0 0 24px' }}>
                <input
                  type="checkbox"
                  checked={selected.has(article.id)}
                  onChange={() => toggleSelected(article.id)}
                  onClick={(e) => e.stopPropagation()}
                />
              </ArtRow.C>
              <ArtRow.T flex={3.2}>
                <Thumb seed={index} w={88} h={56} play src={article.cover_url} className={s.coverThumb} />
                <div className={s.articleMeta}>
                  <ArtRow.Ellipsis>
                    <strong className={s.articleTitle}>{article.title}</strong>
                  </ArtRow.Ellipsis>
                  <p className={s.articleSummary}>{article.summary}</p>
                </div>
              </ArtRow.T>

              <ArtRow.T flex={1.1}>
                {creator ? <Avatar size="xs" id={creator.id} initial={creator.initial} src={creator.avatar_url} /> : null}
                <div className={s.creatorMeta}>
                  <ArtRow.Ellipsis>{creator?.name ?? '—'}</ArtRow.Ellipsis>
                  <span className={s.creatorHandle}>{creator?.handle ?? ''}</span>
                </div>
              </ArtRow.T>

              <ArtRow.Tags tags={article.tags.slice(0, 3)} flex={1.3} />

              <ArtRow.Num flex={0.7}>{article.word_count.toLocaleString()}</ArtRow.Num>
              <ArtRow.Num flex={0.8}>{formatCount(article.likes_snapshot)}</ArtRow.Num>
              <ArtRow.Mono flex={0.9} align="right">
                {formatRelative(article.published_at)}
              </ArtRow.Mono>
            </ArtRow>
          );
        })}

        {articles.length === 0 ? (
          <div className={s.emptyState}>暂无匹配文章 · 换一个筛选条件试试</div>
        ) : null}
      </ArtTable>
    </Page>
  );
}
