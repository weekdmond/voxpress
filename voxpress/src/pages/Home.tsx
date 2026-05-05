import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Page, PageHead } from '@/layouts/AppShell';
import { Avatar, Button, Chip, Icon, Input, type IconName } from '@/components/primitives';
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

interface ResolveProgressStep {
  icon: IconName;
  label: string;
  detail: string;
  state: 'done' | 'current' | 'pending';
}

function lookValidDouyin(url: string): boolean {
  if (!url.trim()) return false;
  return /(?:v\.douyin\.com|douyin\.com|iesdouyin\.com)/.test(url);
}

function looksLikeCreatorShareInput(raw: string): boolean {
  const value = raw.trim().toLowerCase();
  return (
    /查看ta的更多作品|更多作品/.test(raw) ||
    /douyin\.com\/user\//.test(value) ||
    /iesdouyin\.com\/share\/user\//.test(value)
  );
}

function formatResolveElapsed(ms: number): string {
  const totalSec = Math.max(1, Math.floor(ms / 1000));
  if (totalSec < 60) return `${totalSec}s`;
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${min}m ${sec.toString().padStart(2, '0')}s`;
}

function buildResolveProgress(raw: string, elapsedMs: number): {
  headline: string;
  footnote: string;
  isSlow: boolean;
  elapsedLabel: string;
  steps: ResolveProgressStep[];
} {
  const creatorLikely = looksLikeCreatorShareInput(raw);
  const currentStep =
    elapsedMs < 1200 ? 0 : elapsedMs < 3200 ? 1 : elapsedMs < 6500 ? 2 : 3;

  const steps: Omit<ResolveProgressStep, 'state'>[] = [
    {
      icon: 'download',
      label: '提取链接',
      detail: '从分享文案里提取真实链接',
    },
    {
      icon: 'swap',
      label: '展开短链',
      detail: '跟随 v.douyin.com 跳转到真实地址',
    },
    {
      icon: 'search',
      label: '识别类型',
      detail: '判断这是单条内容还是来源主页',
    },
    creatorLikely
      ? {
          icon: 'users',
          label: '同步来源',
          detail: '读取来源主页与最近公开内容',
        }
      : {
          icon: 'check',
          label: '创建任务',
          detail: '单视频会直接入队，主页会继续同步内容',
        },
  ];

  let headline = '正在提取分享文案里的链接…';
  if (currentStep === 1) headline = '正在展开分享短链…';
  if (currentStep === 2) headline = '正在识别这是单条内容还是来源主页…';
  if (currentStep >= 3) {
    headline = creatorLikely
      ? '正在同步来源主页与公开内容…'
      : '正在准备创建处理任务…';
  }

  let footnote = creatorLikely
    ? '这类“查看TA的更多作品”分享通常会先同步来源主页，再跳转到来源页。'
    : '单条公开内容通常会很快入队；如果被识别为来源主页，会额外同步公开内容列表。';
  if (elapsedMs >= 12000) {
    footnote = creatorLikely
      ? '平台侧响应偏慢，仍在同步主页和公开内容列表；这个过程通常比单条内容慢。'
      : '仍在等待平台返回结果；如果它最终被识别成来源主页，会继续同步公开内容。';
  }
  if (elapsedMs >= 20000) {
    footnote =
      `如果持续超过 ${CREATOR_RESOLVE_TIMEOUT_SEC} 秒，系统会自动提示同步超时；通常是平台响应较慢，或当前 Cookie 已失效。`;
  }

  return {
    headline,
    footnote,
    isSlow: elapsedMs >= 12000,
    elapsedLabel: formatResolveElapsed(elapsedMs),
    steps: steps.map((step, idx) => ({
      ...step,
      state: idx < currentStep ? 'done' : idx === currentStep ? 'current' : 'pending',
    })),
  };
}

const RESOLVE_REQUEST_TIMEOUT_MS = 30_000;
const CREATOR_RESOLVE_TIMEOUT_SEC = 25;

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
  const [resolveElapsedMs, setResolveElapsedMs] = useState(0);
  const [resolveTarget, setResolveTarget] = useState('');
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
    mutationFn: async (u: string) => {
      const controller = new AbortController();
      const timeoutId = window.setTimeout(() => controller.abort(), RESOLVE_REQUEST_TIMEOUT_MS);
      try {
        return await api.post<ResolveResult>('/api/resolve', { url: u }, { signal: controller.signal });
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          throw new Error(
            '解析等待超时，请稍后重试。通常是抖音响应较慢，或当前 Cookie 已失效。',
          );
        }
        throw err;
      } finally {
        window.clearTimeout(timeoutId);
      }
    },
    onMutate: (submittedUrl) => {
      setResolveTarget(submittedUrl);
    },
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
    onSettled: () => setResolveTarget(''),
    onError: (err: Error) => toast.error(err.message || '解析链接失败'),
  });

  useEffect(() => {
    if (!resolveLink.isPending) {
      setResolveElapsedMs(0);
      return undefined;
    }
    const startedAt = Date.now();
    setResolveElapsedMs(0);
    const timer = window.setInterval(() => {
      setResolveElapsedMs(Date.now() - startedAt);
    }, 250);
    return () => window.clearInterval(timer);
  }, [resolveLink.isPending]);

  const disabled = !looksValid || resolveLink.isPending;
  const resolveProgress = useMemo(
    () => buildResolveProgress(resolveTarget || url, resolveElapsedMs),
    [resolveElapsedMs, resolveTarget, url],
  );

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
        <div className={s.submitBar}>
          <Input
            size="lg"
            mono
            wrapClassName={s.submitInput}
            placeholder="导入你的视频、音频、字幕或公共链接 · 回车提交"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSubmit();
            }}
            leading={<Icon name="download" size={18} />}
          />
          <Button
            className={s.submitButton}
            variant="primary"
            disabled={disabled}
            onClick={handleSubmit}
          >
            {resolveLink.isPending ? '解析中' : '提交'}
            <Icon name="arrow-right" size={13} />
          </Button>
        </div>
        <div
          className={[s.hint, url.trim() && !looksValid ? s.errorHint : ''].join(' ')}
        >
          {url.trim() && !looksValid
            ? '当前连接器支持公共视频链接、来源主页链接或完整分享文案'
            : resolveLink.isPending
            ? '解析进行中；下面会显示当前阶段和慢请求提示。'
            : '支持导入你拥有或已获授权的内容；公共链接 → 直接入队，来源主页 → 同步公开内容后进入来源页'}
        </div>
        {resolveLink.isPending ? (
          <div className={s.resolvePanel} role="status" aria-live="polite">
            <div className={s.resolvePanelHead}>
              <span>{resolveProgress.headline}</span>
              <span>{resolveProgress.elapsedLabel}</span>
            </div>
            <div className={s.resolveSteps}>
              {resolveProgress.steps.map((step) => (
                <div
                  key={step.label}
                  className={[
                    s.resolveStep,
                    step.state === 'done' ? s.resolveStepDone : '',
                    step.state === 'current' ? s.resolveStepCurrent : '',
                  ].join(' ')}
                >
                  <span className={s.resolveStepBadge}>
                    <Icon name={step.state === 'done' ? 'check' : step.icon} size={12} />
                  </span>
                  <span className={s.resolveStepCopy}>
                    <strong>{step.label}</strong>
                    <small>{step.detail}</small>
                  </span>
                </div>
              ))}
            </div>
            <div className={[s.resolveFootnote, resolveProgress.isSlow ? s.resolveFootnoteSlow : ''].join(' ')}>
              {resolveProgress.footnote}
            </div>
          </div>
        ) : null}
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
