import { Avatar, Button, Chip } from '@/components/primitives';
import { formatEta } from '@/lib/format';
import type { Task } from '@/types/api';
import { ProgressBar } from './ProgressBar';
import { StageStrip } from './StageStrip';
import s from './TaskCard.module.css';

export interface TaskCardProps {
  task: Task;
  onCancel?: (task: Task) => void;
  onRetry?: (task: Task) => void;
}

export function TaskCard({ task, onCancel, onRetry }: TaskCardProps) {
  const isFailed = task.status === 'failed';
  return (
    <div className={s.card}>
      <div className={s.head}>
        {task.creator_id != null ? (
          <Avatar
            size="sm"
            id={task.creator_id}
            initial={task.creator_initial ?? task.creator_name?.[0] ?? '?'}
          />
        ) : (
          <Avatar size="sm" id={0} initial="·" />
        )}
        <div className={s.headText}>
          <p className={s.title} title={task.title_guess}>
            {task.title_guess || '解析中…'}
          </p>
          <div className={s.meta}>
            <span>{task.creator_name ?? '未识别创作者'}</span>
            <span className={s.dot}>·</span>
            <span>{task.detail ?? '等待调度'}</span>
          </div>
        </div>
        {isFailed ? (
          <Chip variant="warn">失败</Chip>
        ) : (
          <Chip variant="accent" mono>
            {task.progress}%
          </Chip>
        )}
      </div>

      <StageStrip current={task.stage} status={task.status} />

      <ProgressBar value={task.progress} active={task.status === 'running'} accent />

      <div className={s.tail}>
        <div className={s.detail}>{task.status === 'running' ? '运行中' : task.status}</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {isFailed && task.error ? <span className={s.error}>{task.error}</span> : null}
          <span className={s.eta}>{formatEta(task.eta_sec)}</span>
          {isFailed && onRetry ? (
            <Button size="sm" variant="default" onClick={() => onRetry(task)}>
              重试
            </Button>
          ) : null}
          {!isFailed && onCancel ? (
            <Button size="sm" variant="ghost" onClick={() => onCancel(task)}>
              取消
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
