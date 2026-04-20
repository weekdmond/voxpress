import { thumbGradient } from '@/lib/gradients';
import { Icon } from './Icon';
import s from './Thumb.module.css';

export interface ThumbProps {
  seed: number;
  w: number;
  h: number;
  play?: boolean;
  className?: string;
}

export function Thumb({ seed, w, h, play, className }: ThumbProps) {
  return (
    <div
      className={[s.thumb, className ?? ''].filter(Boolean).join(' ')}
      style={{ width: w, height: h, background: thumbGradient(seed) }}
      aria-hidden
    >
      <span className={s.highlight} />
      {play ? (
        <span className={s.play}>
          <Icon name="play" size={Math.min(14, Math.floor(Math.min(w, h) * 0.35))} />
        </span>
      ) : null}
    </div>
  );
}
