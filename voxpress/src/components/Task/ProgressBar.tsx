import s from './ProgressBar.module.css';

export interface ProgressBarProps {
  value: number;
  active?: boolean;
  accent?: boolean;
}

export function ProgressBar({ value, active, accent }: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className={[s.wrap, active ? s.active : ''].filter(Boolean).join(' ')}>
      <div
        className={[s.fill, accent ? s.accent : ''].filter(Boolean).join(' ')}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
