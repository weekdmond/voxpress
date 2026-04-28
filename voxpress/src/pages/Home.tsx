import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Page, PageHead } from '@/layouts/AppShell';
import { Avatar, Button, Chip, Icon, Input } from '@/components/primitives';
import { ArtCard } from '@/components/ArtCard/ArtCard';
import { api } from '@/lib/api';
import { formatDateTime, formatEta, formatRelative } from '@/lib/format';
import type { Article, Creator, Health, Page as ApiPage, Task } from '@/types/api';
import { useRunningTasks } from '@/features/tasks/useRunningTasks';
import s from './Home.module.css';

type ResolveResult =
  | { kind: 'video'; task_id: string }
  | {
      kind: 'creator';
      creator_id: number;
      name?: string;
      video_count?: number;
      fetched_video_count?: number;
      backfill_started?: boolean;
      backfill_run_id?: string | null;
    };

function lookValidDouyin(url: string): boolean {
  if (!url.trim()) return false;
  return /(?:v\.douyin\.com|douyin\.com|iesdouyin\.com)/.test(url);
}

const STAGE_LABELS = {
  download: '下载',
  transcribe: '转写',
  correct: '纠错',
  organize: '整理',
  save: '保存',
} as const;

const STAGE_ICONS = {
  download: 'download',
  transcribe: 'wave',
  correct: 'refresh',
  organize: 'sparkle',
  save: 'check',
} as const;

const STATUS_LABELS = {
  queued: '排队中',
  running: '运行中',
  failed: '失败',
  canceled: '已取消',
  done: '已完成',
} as const;

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
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: () => api.get<Health>('/api/health'),
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
        const fetched = res.fetched_video_count ?? res.video_count ?? 0;
        const total = res.video_count ?? fetched;
        const summary =
          total !== fetched ? `已入库 ${fetched} 条；主页显示 ${total} 条` : `已入库 ${fetched} 条`;
        const backfill = res.backfill_started ? '；后台补齐已启动' : '';
        toast.success(
          `已同步创作者「${res.name ?? '未命名'}」的公开视频列表：${summary}${backfill}`,
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

  const activeTasks = useMemo(() => {
    return [...(running.data ?? [])]
      .filter((task) => task.status === 'queued' || task.status === 'running')
      .sort((a, b) => {
        if (a.status !== b.status) return a.status === 'running' ? -1 : 1;
        if (a.progress !== b.progress) return b.progress - a.progress;
        return Date.parse(b.updated_at) - Date.parse(a.updated_at);
      });
  }, [running.data]);
  const runningCount = activeTasks.filter((task) => task.status === 'running').length;
  const queuedCount = activeTasks.filter((task) => task.status === 'queued').length;
  const visible = activeTasks.slice(0, 8);
  const overflow = Math.max(0, activeTasks.length - visible.length);

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
            {health?.deploy_commit ? <span>· 版本 {health.deploy_commit.slice(0, 7)}</span> : null}
            {health?.deployed_at ? <span>· 更新 {formatDateTime(health.deployed_at)}</span> : null}
          </>
        }
      />

      <section className={s.submit}>
        <Input
          size="lg"
          mono
          placeholder="导入你的公开视频链接、创作者主页链接或整段分享文案 · 回车提交"
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
            ? '当前支持抖音公开视频或创作者主页链接(v.douyin.com / douyin.com/video/... / douyin.com/user/...)'
            : resolveLink.isPending
            ? '解析中…'
            : '支持直接粘贴整段抖音分享文案；公开视频链接 → 直接入队；创作者主页短链 → 同步公开内容后进入来源页'}
        </div>
      </section>

      <section className={s.section}>
        <div className={s.sectionHead}>
          <div className={s.sectionTitle}>
            运行中任务
            {activeTasks.length > 0 ? (
              <Chip variant="ok" live>
                {runningCount} 运行中
              </Chip>
            ) : null}
            {queuedCount > 0 ? <Chip>{queuedCount} 排队</Chip> : null}
          </div>
          <span className={s.sectionMeta}>
            SSE · 实时推送
          </span>
        </div>
        <div className={s.taskList}>
          <div className={s.taskHead}>
            <span>任务</span>
            <span>阶段</span>
            <span>进度</span>
            <span>状态</span>
            <span>操作</span>
          </div>
          {activeTasks.length === 0 ? (
            <div className={s.emptyLine}>暂无运行中任务</div>
          ) : (
            visible.map((t) => (
              <div key={t.id} className={s.taskRow}>
                <div className={s.taskMain}>
                  <Avatar
                    size="sm"
                    id={t.creator_id ?? 0}
                    initial={t.creator_initial ?? t.creator_name?.[0] ?? '·'}
                    src={t.creator_id != null ? creatorMap.get(t.creator_id)?.avatar_url : null}
                  />
                  <div className={s.taskBody}>
                    <div className={s.taskTitle} title={t.title_guess}>
                      {t.title_guess || '解析中…'}
                    </div>
                    <div className={s.taskMetaLine}>
                      <span>{t.creator_name ?? '未识别创作者'}</span>
                      <span className={s.taskDot}>·</span>
                      <span>{t.detail ?? (t.status === 'queued' ? '等待调度' : '处理中')}</span>
                      <span className={s.taskDot}>·</span>
                      <span>{formatRelative(t.updated_at)}</span>
                    </div>
                  </div>
                </div>

                <div className={s.taskStage}>
                  <span className={s.stagePill}>
                    <Icon name={STAGE_ICONS[t.stage]} size={12} />
                    {STAGE_LABELS[t.stage]}
                  </span>
                </div>

                <div className={s.taskProgress}>
                  <div className={s.progressTrack}>
                    <span
                      className={s.progressFill}
                      style={{ width: `${Math.max(t.progress, t.status === 'running' ? 6 : 4)}%` }}
                    />
                  </div>
                  <span className={s.progressValue}>{t.progress}%</span>
                </div>

                <div className={s.taskStatus}>
                  <span
                    className={[
                      s.statusPill,
                      t.status === 'running' ? s.statusRunning : s.statusQueued,
                    ].join(' ')}
                  >
                    {STATUS_LABELS[t.status]}
                  </span>
                  <span className={s.statusSub}>{formatEta(t.eta_sec) || '实时队列'}</span>
                </div>

                <div className={s.taskAction}>
                  <Button size="sm" variant="ghost" onClick={() => cancelTask.mutate(t)}>
                    取消
                  </Button>
                </div>
              </div>
            ))
          )}
          {overflow > 0 ? (
            <div className={s.more}>
              还有 {overflow} 个任务 ·{' '}
              <Link to="/tasks" className={s.moreButton}>
                查看全部任务 →
              </Link>
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
                  creatorName={c?.name ?? '未知创作者'}
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
