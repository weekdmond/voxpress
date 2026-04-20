import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Page, PageHead } from '@/layouts/AppShell';
import { ArtHead, ArtRow, ArtTable } from '@/components/ArtRow/ArtRow';
import { Avatar, Chip, Icon, Input, Thumb } from '@/components/primitives';
import { api } from '@/lib/api';
import { formatCount, formatRelative } from '@/lib/format';
import type { Article, Creator, Page as ApiPage } from '@/types/api';

export function ArticlesPage() {
  const [q, setQ] = useState('');
  const navigate = useNavigate();

  const { data } = useQuery({
    queryKey: ['articles', { q }],
    queryFn: () => {
      const params = new URLSearchParams();
      if (q) params.set('q', q);
      const qs = params.toString();
      return api.get<ApiPage<Article>>(`/api/articles${qs ? `?${qs}` : ''}`);
    },
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

  const articles = data?.items ?? [];
  const total = data?.total ?? articles.length;

  return (
    <Page>
      <PageHead
        title="文章"
        meta={
          <>
            <span>{total} 篇已整理</span>
            <span>· 按发布时间</span>
          </>
        }
      />

      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <Chip variant="solid">{total} 篇</Chip>
        <Chip>博主 ˅</Chip>
        <Chip>标签 ˅</Chip>
        <Chip>近 30 天</Chip>
        <span style={{ flex: 1 }} />
        <div style={{ width: 280 }}>
          <Input
            leading={<Icon name="search" size={14} />}
            placeholder="搜索标题或正文"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>

      <ArtTable>
        <ArtHead>
          <ArtHead.Cell flex={2.4}>标题</ArtHead.Cell>
          <ArtHead.Cell flex={1.1}>博主</ArtHead.Cell>
          <ArtHead.Cell flex={1}>标签</ArtHead.Cell>
          <ArtHead.Cell flex={0.7} align="right">
            字数
          </ArtHead.Cell>
          <ArtHead.Cell flex={0.8} align="right">
            点赞
          </ArtHead.Cell>
          <ArtHead.Cell flex={0.9} align="right">
            日期 ↓
          </ArtHead.Cell>
        </ArtHead>
        {articles.map((a, i) => {
          const c = creatorMap.get(a.creator_id);
          return (
            <ArtRow
              key={a.id}
              onClick={() => navigate(`/articles/${a.id}`)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') navigate(`/articles/${a.id}`);
              }}
            >
              <ArtRow.T flex={2.4}>
                <Thumb seed={i} w={36} h={24} />
                <ArtRow.Ellipsis>
                  <strong style={{ fontWeight: 600 }}>{a.title}</strong>
                </ArtRow.Ellipsis>
              </ArtRow.T>
              <ArtRow.T flex={1.1}>
                {c ? <Avatar size="xs" id={c.id} initial={c.initial} /> : null}
                <ArtRow.Ellipsis>{c?.name ?? '—'}</ArtRow.Ellipsis>
              </ArtRow.T>
              <ArtRow.Tags tags={a.tags} flex={1} />
              <ArtRow.Num flex={0.7}>{a.word_count.toLocaleString()}</ArtRow.Num>
              <ArtRow.Num flex={0.8}>{formatCount(a.likes_snapshot)}</ArtRow.Num>
              <ArtRow.Mono flex={0.9} align="right">
                {formatRelative(a.published_at)}
              </ArtRow.Mono>
            </ArtRow>
          );
        })}
        {articles.length === 0 ? (
          <div style={{ padding: '40px 18px', textAlign: 'center', color: 'var(--vp-ink-3)', fontSize: 12.5 }}>
            暂无文章 · 从首页提交第一条链接 →
          </div>
        ) : null}
      </ArtTable>
    </Page>
  );
}
