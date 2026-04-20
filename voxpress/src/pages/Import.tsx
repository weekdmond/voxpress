import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Page, PageHead } from '@/layouts/AppShell';
import { ArtHead, ArtRow, ArtTable } from '@/components/ArtRow/ArtRow';
import { Avatar, Box, Button, Chip, Icon, Thumb } from '@/components/primitives';
import { Stepper } from '@/components/Stepper/Stepper';
import { api } from '@/lib/api';
import { formatCount, formatDate, formatDuration } from '@/lib/format';
import type { Creator, Page as ApiPage, Task, Video } from '@/types/api';

export function ImportPage() {
  const { creatorId = '' } = useParams<{ creatorId: string }>();
  const idNum = Number(creatorId);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [minDur, setMinDur] = useState(180);
  const [minLikes, setMinLikes] = useState(10_000);
  const [since30d, setSince30d] = useState(true);

  const { data: creator } = useQuery({
    queryKey: ['creator', idNum],
    queryFn: () => api.get<Creator>(`/api/creators/${idNum}`),
  });

  const { data: videosPage } = useQuery({
    queryKey: ['videos', idNum, { minDur, minLikes, since30d }],
    queryFn: () => {
      const params = new URLSearchParams({
        min_dur: String(minDur),
        min_likes: String(minLikes),
      });
      if (since30d) params.set('since', '30d');
      return api.get<ApiPage<Video>>(`/api/creators/${idNum}/videos?${params}`);
    },
    enabled: !isNaN(idNum),
  });
  const videos = useMemo(() => videosPage?.items ?? [], [videosPage]);

  const total = videos.length;
  const allSelected = total > 0 && videos.every((v) => selected.has(v.id));
  const toggleAll = () => {
    if (allSelected) setSelected(new Set());
    else setSelected(new Set(videos.map((v) => v.id)));
  };
  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  const submit = useMutation({
    mutationFn: () => api.post<{ tasks: Task[] }>('/api/tasks/batch', { video_ids: Array.from(selected) }),
    onSuccess: (res) => {
      toast.success(`已创建 ${res.tasks.length} 个任务`);
      qc.invalidateQueries({ queryKey: ['tasks'] });
      navigate('/');
    },
    onError: (err: Error) => toast.error(err.message || '提交失败'),
  });

  const currentStep = selected.size > 0 ? 2 : 1;

  return (
    <Page>
      <PageHead
        title="博主批量导入"
        meta={
          creator ? (
            <>
              <span>{creator.name}</span>
              <span>· {total} 条视频</span>
            </>
          ) : null
        }
      />

      <Stepper
        steps={[{ label: '粘贴博主主页' }, { label: '选择视频' }, { label: '开始处理' }]}
        current={currentStep}
      />

      {creator ? (
        <Box>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <Avatar size="lg" id={creator.id} initial={creator.initial} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <strong style={{ fontSize: 16, fontWeight: 600 }}>{creator.name}</strong>
                {creator.verified ? <Chip variant="ok">蓝V</Chip> : null}
              </div>
              <div
                className="mono"
                style={{ fontSize: 11.5, color: 'var(--vp-ink-3)', marginTop: 4 }}
              >
                {creator.handle} · {creator.region ?? '—'}
              </div>
              {creator.bio ? (
                <div style={{ fontSize: 13, color: 'var(--vp-ink-2)', marginTop: 8 }}>
                  {creator.bio}
                </div>
              ) : null}
            </div>
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'flex-end',
                gap: 4,
                fontFamily: 'var(--vp-font-mono)',
                fontSize: 11,
                color: 'var(--vp-ink-3)',
              }}
            >
              <span>
                <strong style={{ color: 'var(--vp-ink)' }}>{formatCount(creator.followers)}</strong> 粉
              </span>
              <span>
                <strong style={{ color: 'var(--vp-ink)' }}>{creator.video_count}</strong> 作品
              </span>
              <span>
                <strong style={{ color: 'var(--vp-ink)' }}>{formatCount(creator.total_likes)}</strong> 获赞
              </span>
            </div>
          </div>
        </Box>
      ) : null}

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <Chip variant="solid">
          选中 {selected.size} / {total}
        </Chip>
        <Chip
          variant={minDur >= 180 ? 'accent' : 'default'}
          onClick={() => setMinDur((v) => (v >= 180 ? 0 : 180))}
          style={{ cursor: 'pointer' }}
        >
          时长 &gt; 3 min
        </Chip>
        <Chip
          variant={since30d ? 'accent' : 'default'}
          onClick={() => setSince30d((v) => !v)}
          style={{ cursor: 'pointer' }}
        >
          近 30 天
        </Chip>
        <Chip
          variant={minLikes >= 10_000 ? 'accent' : 'default'}
          onClick={() => setMinLikes((v) => (v >= 10_000 ? 0 : 10_000))}
          style={{ cursor: 'pointer' }}
        >
          点赞 &gt; 1w
        </Chip>
        <span style={{ flex: 1 }} />
        <Button
          variant="primary"
          disabled={selected.size === 0 || submit.isPending}
          onClick={() => submit.mutate()}
          trailing={<Icon name="arrow-right" size={12} />}
        >
          开始处理 {selected.size} 条
        </Button>
      </div>

      <ArtTable>
        <ArtHead>
          <ArtHead.Cell style={{ width: 24, flex: '0 0 24px' }}>
            <input type="checkbox" checked={allSelected} onChange={toggleAll} />
          </ArtHead.Cell>
          <ArtHead.Cell flex={2.4}>视频</ArtHead.Cell>
          <ArtHead.Cell flex={0.6} align="right">
            时长
          </ArtHead.Cell>
          <ArtHead.Cell flex={0.7} align="right">
            点赞
          </ArtHead.Cell>
          <ArtHead.Cell flex={0.8} align="right">
            播放
          </ArtHead.Cell>
          <ArtHead.Cell flex={0.9} align="right">
            发布
          </ArtHead.Cell>
        </ArtHead>
        {videos.map((v, i) => (
          <ArtRow
            key={v.id}
            onClick={(e) => {
              if ((e.target as HTMLElement).tagName === 'INPUT') return;
              toggle(v.id);
            }}
          >
            <ArtRow.C style={{ width: 24, flex: '0 0 24px' }}>
              <input
                type="checkbox"
                checked={selected.has(v.id)}
                onChange={() => toggle(v.id)}
                onClick={(e) => e.stopPropagation()}
              />
            </ArtRow.C>
            <ArtRow.T flex={2.4}>
              <Thumb seed={i} w={52} h={34} play />
              <ArtRow.Ellipsis>
                <strong style={{ fontWeight: 600 }}>{v.title}</strong>
              </ArtRow.Ellipsis>
            </ArtRow.T>
            <ArtRow.Num flex={0.6}>{formatDuration(v.duration_sec)}</ArtRow.Num>
            <ArtRow.Num flex={0.7}>{formatCount(v.likes)}</ArtRow.Num>
            <ArtRow.Num flex={0.8}>{formatCount(v.plays)}</ArtRow.Num>
            <ArtRow.Mono flex={0.9} align="right">
              {formatDate(v.published_at)}
            </ArtRow.Mono>
          </ArtRow>
        ))}
        {videos.length === 0 ? (
          <div style={{ padding: '36px 18px', textAlign: 'center', color: 'var(--vp-ink-3)', fontSize: 12.5 }}>
            暂无视频 · 换一个筛选条件
          </div>
        ) : null}
      </ArtTable>
    </Page>
  );
}
