import type { TaskStage, TaskStatus } from '@/types/api';
import s from './StageStrip.module.css';

const LABELS: Record<TaskStage, string> = {
  download: '下载',
  transcribe: '转写',
  organize: '整理',
  save: '保存',
};

const STAGES: TaskStage[] = ['download', 'transcribe', 'organize', 'save'];

export interface StageStripProps {
  current: TaskStage;
  status?: TaskStatus;
}

export function StageStrip({ current, status }: StageStripProps) {
  const idx = STAGES.indexOf(current);
  return (
    <div className={s.strip}>
      {STAGES.map((stage, i) => {
        const isDone = i < idx || status === 'done';
        const isCurrent = i === idx && status !== 'done' && status !== 'failed';
        const isFailed = i === idx && status === 'failed';
        const cls = [
          s.seg,
          isDone ? s.done : '',
          isCurrent ? s.current : '',
          isFailed ? s.failed : '',
        ]
          .filter(Boolean)
          .join(' ');
        return (
          <span key={stage} className={cls}>
            {LABELS[stage]}
          </span>
        );
      })}
    </div>
  );
}
