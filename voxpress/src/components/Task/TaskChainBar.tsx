import { Icon } from '@/components/primitives';
import type { IconName } from '@/components/primitives';
import type { TaskStage, TaskStatus } from '@/types/api';
import s from './TaskChainBar.module.css';

const STAGE_ORDER: TaskStage[] = ['download', 'transcribe', 'correct', 'organize', 'save'];

const STAGE_ICON: Record<TaskStage, IconName> = {
  download: 'download',
  transcribe: 'mic',
  correct: 'zap',
  organize: 'doc',
  save: 'save',
};

const STAGE_LABEL: Record<TaskStage, string> = {
  download: '下载',
  transcribe: '转写',
  correct: '纠错',
  organize: '整理',
  save: '保存',
};

type StepStatus = 'done' | 'running' | 'queued' | 'failed';

function statusFor(
  stage: TaskStage,
  currentStage: TaskStage,
  taskStatus: TaskStatus,
): StepStatus {
  const idx = STAGE_ORDER.indexOf(stage);
  const cur = STAGE_ORDER.indexOf(currentStage);
  if (taskStatus === 'done') return 'done';
  if (taskStatus === 'queued') return 'queued';
  if (taskStatus === 'canceled') return idx <= cur ? 'failed' : 'queued';
  if (taskStatus === 'failed') {
    if (idx < cur) return 'done';
    if (idx === cur) return 'failed';
    return 'queued';
  }
  // running
  if (idx < cur) return 'done';
  if (idx === cur) return 'running';
  return 'queued';
}

export interface TaskChainBarProps {
  stage: TaskStage;
  status: TaskStatus;
  compact?: boolean;
}

export function TaskChainBar({ stage, status, compact }: TaskChainBarProps) {
  return (
    <div className={[s.bar, compact ? s.compact : ''].filter(Boolean).join(' ')}>
      {STAGE_ORDER.map((st, i) => {
        const stepStatus = statusFor(st, stage, status);
        return (
          <div key={st} style={{ display: 'inline-flex', alignItems: 'center' }}>
            <span
              className={[s.step, s[stepStatus]].join(' ')}
              title={`${STAGE_LABEL[st]} · ${stepStatus}`}
            >
              <Icon name={STAGE_ICON[st]} size={compact ? 11 : 13} />
            </span>
            {i < STAGE_ORDER.length - 1 ? <span className={s.sep} /> : null}
          </div>
        );
      })}
    </div>
  );
}

export { STAGE_ORDER, STAGE_ICON, STAGE_LABEL };
