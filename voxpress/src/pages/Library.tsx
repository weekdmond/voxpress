import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Page, PageHead } from '@/layouts/AppShell';
import { ArtHead, ArtRow, ArtTable } from '@/components/ArtRow/ArtRow';
import { Avatar, Button, Chip, Icon, Input } from '@/components/primitives';
import { api } from '@/lib/api';
import { formatCount, formatRelative } from '@/lib/format';
import type { Creator, Page as ApiPage } from '@/types/api';

export function LibraryPage() {
  const [q, setQ] = useState('');
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const navigate = useNavigate();

  const { data } = useQuery({
    queryKey: ['creators', { q, verifiedOnly }],
    queryFn: () => {
      const params = new URLSearchParams({ sort: 'followers:desc' });
      if (q) params.set('q', q);
      if (verifiedOnly) params.set('verified', '1');
      return api.get<ApiPage<Creator>>(`/api/creators?${params}`);
    },
  });
  const creators = data?.items ?? [];
  const total = data?.total ?? creators.length;
  const verifiedCount = useMemo(() => creators.filter((c) => c.verified).length, [creators]);

  return (
    <Page>
      <PageHead
        title="博主列表"
        meta={
          <>
            <span>{total} 位博主</span>
            <span>· 创作者内容资产库</span>
            <span>· 按受众规模排序</span>
          </>
        }
      />

      <div
        style={{
          display: 'flex',
          gap: 12,
          alignItems: 'center',
          flexWrap: 'wrap',
          padding: '2px 0',
        }}
      >
        <Chip variant="solid">全部 · {total}</Chip>
        <Chip
          onClick={() => setVerifiedOnly((v) => !v)}
          variant={verifiedOnly ? 'accent' : 'default'}
          style={{ cursor: 'pointer' }}
        >
          已认证 · {verifiedCount}
        </Chip>
        <Chip>公开视频</Chip>
        <span style={{ flex: 1 }} />
        <div style={{ width: 280 }}>
          <Input
            leading={<Icon name="search" size={14} />}
            placeholder="搜索博主名或简介"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <Button variant="primary" icon={<Icon name="download" size={12} />}>
          导入博主
        </Button>
      </div>

      <ArtTable>
        <ArtHead>
          <ArtHead.Cell flex={2}>博主</ArtHead.Cell>
          <ArtHead.Cell flex={1} align="right">
            受众 ↓
          </ArtHead.Cell>
          <ArtHead.Cell flex={0.7} align="right">
            文章
          </ArtHead.Cell>
          <ArtHead.Cell flex={0.7} align="right">
            内容
          </ArtHead.Cell>
          <ArtHead.Cell flex={1} align="right">
            获赞
          </ArtHead.Cell>
          <ArtHead.Cell flex={1}>最近更新</ArtHead.Cell>
          <ArtHead.Cell flex={0.6} align="right">
            认证
          </ArtHead.Cell>
        </ArtHead>

        {creators.map((c) => (
          <ArtRow
            key={c.id}
            onClick={() => navigate(`/library/${c.id}`)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') navigate(`/library/${c.id}`);
            }}
          >
            <ArtRow.T flex={2}>
              <Avatar size="sm" id={c.id} initial={c.initial} src={c.avatar_url} />
              <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                <strong style={{ fontSize: 13, fontWeight: 600 }}>{c.name}</strong>
                <span
                  className="mono"
                  style={{ fontSize: 11, color: 'var(--vp-ink-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                >
                  {c.handle} · {c.region ?? '—'} · {c.bio ?? ''}
                </span>
              </div>
            </ArtRow.T>
            <ArtRow.Num flex={1}>{formatCount(c.followers)}</ArtRow.Num>
            <ArtRow.Num flex={0.7}>{c.article_count}</ArtRow.Num>
            <ArtRow.Num flex={0.7}>{formatCount(c.video_count)}</ArtRow.Num>
            <ArtRow.Num flex={1}>{formatCount(c.total_likes)}</ArtRow.Num>
            <ArtRow.Mono flex={1}>
              {c.recent_update_at ? formatRelative(c.recent_update_at) : '—'}
            </ArtRow.Mono>
            <ArtRow.Mono flex={0.6} align="right">
              {c.verified ? <Chip variant="ok">已认证</Chip> : '—'}
            </ArtRow.Mono>
          </ArtRow>
        ))}
        {creators.length === 0 ? (
          <div style={{ padding: '40px 18px', textAlign: 'center', color: 'var(--vp-ink-3)', fontSize: 12.5 }}>
            暂无博主 · 换个关键词试试
          </div>
        ) : null}
      </ArtTable>
    </Page>
  );
}
