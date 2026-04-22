import { useEffect, useState } from 'react';
import { thumbGradient } from '@/lib/gradients';
import { mediaCandidates } from '@/lib/media';
import s from './TaskCover.module.css';

export interface TaskCoverProps {
  seed: number;
  label: string;
  src?: string | null;
  size?: number;
}

export function TaskCover({ seed, label, src, size = 32 }: TaskCoverProps) {
  const [attempt, setAttempt] = useState(0);
  useEffect(() => setAttempt(0), [src]);

  const candidates = mediaCandidates(src);
  const resolvedSrc = candidates[attempt];

  const bg = thumbGradient(seed);
  const trimmed = label.trim().slice(0, 3) || '·';

  return (
    <div
      className={s.cover}
      style={{ width: size, height: size, background: bg, fontSize: size * 0.28 }}
      aria-hidden
    >
      {resolvedSrc ? (
        <img
          src={resolvedSrc}
          alt=""
          referrerPolicy="no-referrer"
          onError={() => setAttempt((v) => v + 1)}
        />
      ) : null}
      <span>{trimmed}</span>
    </div>
  );
}
