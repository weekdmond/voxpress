import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Page, PageHead } from '@/layouts/AppShell';
import { Button, Chip, Icon, Input } from '@/components/primitives';
import { TaskCard } from '@/components/Task/TaskCard';
import { ArtCard } from '@/components/ArtCard/ArtCard';
import { api } from '@/lib/api';
import type { Article, Creator, Page as ApiPage, Task } from '@/types/api';
import { useRunningTasks } from '@/features/tasks/useRunningTasks';
import s from './Home.module.css';

type ResolveResult =
  | { kind: 'video'; task_id: string }
  | { kind: 'creator'; creator_id: number; name?: string };

function lookValidDouyin(url: string): boolean {
  if (!url.trim()) return false;
  return /(?:v\.douyin\.com|douyin\.com|iesdouyin\.com)/.test(url);
}

export function HomePage() {
  const [url, setUrl] = useState('');
  const navigate = useNavigate();
  const qc = useQueryClient();

  const looksValid = useMemo(() => lookValidDouyin(url), [url]);

  const running = useRunningTasks();
  const { data: recentPage } = useQuery({
    queryKey: ['articles', 'recent', 6],
    queryFn: () => api.get<ApiPage<Article>>('/api/articles?limit=6'),
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

  const resolveLink = useMutation({
    mutationFn: (u: string) => api.post<ResolveResult>('/api/resolve', { url: u }),
    onSuccess: (res) => {
      setUrl('');
      if (res.kind === 'video') {
        toast.success('任务已创建');
      } else {
        toast.success(
          `已建档博主「${res.name ?? '未命名'}」— Douyin 用户页是 SPA,视频列表要手动粘链接`,
          { duration: 6000 },
        );
        qc.invalidateQueries({ queryKey: ['creators'] });
        navigate(`/import/${res.creator_id}`);
      }
    },
    onError: (err: Error) => toast.error(err.message || '解析链接失败'),
  });

  const disabled = !looksValid || resolveLink.isPending;

  const handleSubmit = () => {
    if (disabled) return;
    resolveLink.mutate(url.trim());
  };

  const cancelTask = useMutation({
    mutationFn: (task: Task) => api.post<Task>(`/api/tasks/${task.id}/cancel`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }),
  });

  const runningTasks = running.data ?? [];
  const visible = runningTasks.slice(0, 5);
  const overflow = Math.max(0, runningTasks.length - visible.length);

  const recentArticles = recentPage?.items ?? [];

  return (
    <Page>
      <PageHead
        title="首页"
        meta={
          <>
            <span>提交新任务</span>
            <span>· 运行中</span>
            <span>· 最近完成</span>
          </>
        }
      />

      <section className={s.submit}>
        <Input
          size="lg"
          mono
          placeholder="粘贴抖音视频或博主主页链接 · 回车提交"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleSubmit();
          }}
          leading={<Icon name="download" size={18} />}
          trailing={
            <Button variant="primary" disabled={disabled} onClick={handleSubmit}>
              提交 <Icon name="arrow-right" size={12} />
            </Button>
          }
        />
        <div
          className={[s.hint, url.trim() && !looksValid ? s.errorHint : ''].join(' ')}
        >
          {url.trim() && !looksValid
            ? '请贴一条抖音链接(v.douyin.com / douyin.com/video/... / douyin.com/user/...)'
            : resolveLink.isPending
            ? '解析中…'
            : '视频链接 → 直接入队;博主主页/短链 → 自动抓视频列表后跳导入页'}
        </div>
      </section>

      <section className={s.section}>
        <div className={s.sectionHead}>
          <div className={s.sectionTitle}>
            运行中任务
            {runningTasks.length > 0 ? (
              <Chip variant="ok" live>
                {runningTasks.length} running
              </Chip>
            ) : null}
          </div>
          <span style={{ fontFamily: 'var(--vp-font-mono)', fontSize: 11, color: 'var(--vp-ink-3)' }}>
            SSE · 实时推送
          </span>
        </div>
        <div className={s.tasks}>
          {runningTasks.length === 0 ? (
            <div className={s.emptyLine}>暂无运行中任务</div>
          ) : (
            visible.map((t) => (
              <TaskCard key={t.id} task={t} onCancel={(task) => cancelTask.mutate(task)} />
            ))
          )}
          {overflow > 0 ? (
            <div className={s.more}>
              还有 {overflow} 个任务 · <Link to="/articles">全部 →</Link>
            </div>
          ) : null}
        </div>
      </section>

      <section className={s.section}>
        <div className={s.sectionHead}>
          <div className={s.sectionTitle}>最近完成</div>
          <Link
            to="/articles"
            style={{ fontFamily: 'var(--vp-font-mono)', fontSize: 11, color: 'var(--vp-ink-3)' }}
          >
            全部 {recentPage?.total ?? '…'} 篇 →
          </Link>
        </div>
        {recentArticles.length === 0 ? (
          <div className={s.emptyLine}>粘贴一条链接开始处理 →</div>
        ) : (
          <div className={s.grid}>
            {recentArticles.map((a) => {
              const c = creatorMap.get(a.creator_id);
              return (
                <ArtCard
                  key={a.id}
                  article={a}
                  creatorName={c?.name ?? '未知博主'}
                  creatorInitial={c?.initial ?? '?'}
                />
              );
            })}
          </div>
        )}
      </section>
    </Page>
  );
}
