import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Icon } from '@/components/primitives';
import { api } from '@/lib/api';
import { formatDuration, formatRelative } from '@/lib/format';
import type { TaskDetail, TaskStage, TaskStageRun } from '@/types/api';
import s from './TaskDrawer.module.css';

const STAGE_LABEL: Record<TaskStage, string> = {
  download: 'download',
  transcribe: 'transcribe',
  correct: 'correct',
  organize: 'organize',
  save: 'save',
};

const KIND_OF_STAGE: Record<TaskStage, 'llm' | 'asr' | 'none'> = {
  download: 'none',
  transcribe: 'asr',
  correct: 'llm',
  organize: 'llm',
  save: 'none',
};

function formatCount(n: number): string {
  if (n >= 10000) return `${(n / 10000).toFixed(1)}w`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function formatDurationMs(ms: number | null): string {
  if (!ms || ms < 0) return '—';
  const s = Math.round(ms / 1000);
  return formatDuration(s);
}

function stepStateClass(r: TaskStageRun): string {
  if (r.status === 'running') return s.dotRunning;
  if (r.status === 'failed') return s.dotFailed;
  if (r.status === 'queued') return s.dotPending;
  if (r.status === 'skipped') return s.dotPending;
  if (r.status === 'canceled') return s.dotPending;
  return '';
}

function stepMetaText(r: TaskStageRun): string {
  const bits: string[] = [];
  if (r.input_tokens) bits.push(`输入 ${formatCount(r.input_tokens)} tok`);
  if (r.output_tokens) bits.push(`输出 ${formatCount(r.output_tokens)} tok`);
  if (r.duration_ms != null) bits.push(`耗时 ${formatDurationMs(r.duration_ms)}`);
  return bits.join(' · ');
}

export interface TaskDrawerProps {
  taskId: string;
  onClose: () => void;
  onRerun: (taskId: string, mode: 'resume' | 'organize' | 'full') => void;
  onCancel?: (taskId: string) => void;
}

export function TaskDrawer({ taskId, onClose, onRerun, onCancel }: TaskDrawerProps) {
  const { data } = useQuery({
    queryKey: ['task-detail', taskId],
    queryFn: () => api.get<TaskDetail>(`/api/tasks/${taskId}/detail`),
    refetchInterval: (q) => {
      const d = q.state.data;
      if (!d) return false;
      return d.status === 'running' || d.status === 'queued' ? 1500 : false;
    },
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const t = data;
  const totalCost = t?.cost_cny ?? 0;
  const totalTokens = t?.total_tokens ?? 0;
  const elapsed = t?.elapsed_ms ?? null;
  const canCancel = t && (t.status === 'running' || t.status === 'queued');

  return (
    <>
      <div className={s.scrim} onClick={onClose} />
      <aside className={s.drawer} role="dialog" aria-label="任务详情">
        <div className={s.head}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className={s.title}>{t?.title_guess || t?.article_title || '加载中…'}</div>
            <div className={s.sub}>
              {t?.creator_name ?? '—'} · {t ? formatRelative(t.started_at) : '—'} ·{' '}
              {t?.status ?? '—'}
            </div>
          </div>
          <button className={s.close} onClick={onClose} aria-label="关闭">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M6 6l12 12M18 6 6 18" />
            </svg>
          </button>
        </div>

        <div className={s.body}>
          {t ? (
            <>
              {t.status === 'failed' ? (
                <div className={[s.rerunBox, s.rerunBoxFailed].join(' ')}>
                  <div className={[s.rerunIcon, s.rerunIconFailed].join(' ')}>
                    <Icon name="refresh" size={14} />
                  </div>
                  <div className={s.rerunInfo}>
                    <div className={s.rerunTitle}>
                      在 <b>{t.stage}</b> 阶段失败
                    </div>
                    <div className={s.rerunSub}>
                      已消耗 ¥{totalCost.toFixed(3)} · {t.error ? t.error.slice(0, 60) : ''}
                    </div>
                  </div>
                  {t.available_rerun_modes?.full ? (
                    <button
                      className={[s.rerunBtn, s.rerunBtnGhost].join(' ')}
                      onClick={() => onRerun(t.id, 'full')}
                    >
                      从头重跑
                    </button>
                  ) : null}
                  {t.available_rerun_modes?.resume ? (
                    <button className={s.rerunBtn} onClick={() => onRerun(t.id, 'resume')}>
                      从 {t.stage} 续跑
                    </button>
                  ) : null}
                </div>
              ) : null}

              {t.status === 'done' ? (
                <div className={[s.rerunBox, s.rerunBoxSucceeded].join(' ')}>
                  <div className={[s.rerunIcon, s.rerunIconSucceeded].join(' ')}>
                    <Icon name="refresh" size={14} />
                  </div>
                  <div className={s.rerunInfo}>
                    <div className={s.rerunTitle}>重新生成文章</div>
                    <div className={s.rerunSub}>
                      将覆盖现有文章 · 预计消耗 ¥{totalCost.toFixed(3)}
                    </div>
                  </div>
                  {t.available_rerun_modes?.organize ? (
                    <button
                      className={[s.rerunBtn, s.rerunBtnGhost].join(' ')}
                      onClick={() => onRerun(t.id, 'organize')}
                    >
                      只重跑 organize
                    </button>
                  ) : null}
                  {t.available_rerun_modes?.full ? (
                    <button className={s.rerunBtn} onClick={() => onRerun(t.id, 'full')}>
                      从头重跑
                    </button>
                  ) : null}
                </div>
              ) : null}

              <div className={s.sumGrid}>
                <div className={s.sumCell}>
                  <b>¥{totalCost.toFixed(3)}</b>
                  <span>总成本</span>
                </div>
                <div className={s.sumCell}>
                  <b>{elapsed ? formatDurationMs(elapsed) : '—'}</b>
                  <span>耗时</span>
                </div>
                <div className={s.sumCell}>
                  <b>{totalTokens ? formatCount(totalTokens) : '—'}</b>
                  <span>LLM tokens</span>
                </div>
                <div className={s.sumCell}>
                  <b>{t.primary_model ?? '—'}</b>
                  <span>主模型</span>
                </div>
              </div>

              <div className={s.secH}>
                <span>任务链 · {t.stage_runs.length} 步</span>
                <span className="r">
                  {t.status === 'done'
                    ? '已完成'
                    : t.status === 'running'
                    ? `进行中 · ${t.stage}`
                    : t.status === 'queued'
                    ? '等待调度'
                    : t.status === 'failed'
                    ? `失败于 ${t.stage}`
                    : '已取消'}
                </span>
              </div>

              <div className={s.chain}>
                {t.stage_runs.map((r) => {
                  const kind = KIND_OF_STAGE[r.stage];
                  const kindCls =
                    kind === 'llm' ? s.kindLlm : kind === 'asr' ? s.kindAsr : s.kindNone;
                  const costDisplay =
                    r.status === 'running'
                      ? { value: '…', label: '进行中', zero: false }
                      : r.status === 'queued' || r.status === 'skipped'
                      ? { value: '—', label: '等待中', zero: true }
                      : r.status === 'failed'
                      ? { value: '失败', label: r.error?.slice(0, 20) ?? '错误', zero: false }
                      : r.cost_cny > 0
                      ? {
                          value: `¥${r.cost_cny.toFixed(4)}`,
                          label: '本步成本',
                          zero: false,
                        }
                      : { value: '—', label: '无计费', zero: true };

                  return (
                    <div key={r.stage} className={s.chainStep}>
                      <div className={s.dotWrap}>
                        <div className={[s.dot, stepStateClass(r)].filter(Boolean).join(' ')} />
                      </div>
                      <div className={s.stepMain}>
                        <div className={s.stepName}>
                          <b>{STAGE_LABEL[r.stage]}</b>
                          <span className={[s.kind, kindCls].join(' ')}>
                            {r.model ?? r.provider ?? '—'}
                          </span>
                        </div>
                        <div className={s.stepMeta}>
                          {r.detail ? <span>{r.detail}</span> : null}
                          {stepMetaText(r) ? <span>{stepMetaText(r)}</span> : null}
                        </div>
                      </div>
                      <div
                        className={[s.stepCost, costDisplay.zero ? s.stepCostZero : '']
                          .filter(Boolean)
                          .join(' ')}
                      >
                        <b>{costDisplay.value}</b>
                        <span>{costDisplay.label}</span>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className={s.secH} style={{ marginTop: 20 }}>
                <span>任务元信息</span>
              </div>
              <div className={s.metaTable}>
                <div className={s.metaRow}>
                  <span>任务 ID</span>
                  <span>{t.id}</span>
                </div>
                <div className={s.metaRow}>
                  <span>触发</span>
                  <span>{t.trigger_kind}</span>
                </div>
                <div className={s.metaRow}>
                  <span>开始</span>
                  <span>{new Date(t.started_at).toLocaleString('zh-CN')}</span>
                </div>
                <div className={s.metaRow}>
                  <span>结束</span>
                  <span>
                    {t.finished_at ? new Date(t.finished_at).toLocaleString('zh-CN') : '—'}
                  </span>
                </div>
              </div>

              {canCancel && onCancel ? (
                <div style={{ marginTop: 16, textAlign: 'right' }}>
                  <button
                    className={[s.rerunBtn, s.rerunBtnGhost].join(' ')}
                    onClick={() => onCancel(t.id)}
                  >
                    取消任务
                  </button>
                </div>
              ) : null}
            </>
          ) : (
            <div style={{ color: 'var(--vp-ink-3)', fontFamily: 'var(--vp-font-mono)', fontSize: 12 }}>
              加载中…
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
