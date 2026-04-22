import { useEffect, useState } from 'react';
import { thumbGradient } from '@/lib/gradients';
import { mediaCandidates } from '@/lib/media';
import { Icon } from './Icon';
import s from './Thumb.module.css';

export interface ThumbProps {
  seed: number;
  w: number;
  h: number;
  play?: boolean;
  src?: string | null;
  className?: string;
}

export function Thumb({ seed, w, h, play, src, className }: ThumbProps) {
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setAttempt(0);
  }, [src]);

  const candidates = mediaCandidates(src);
  const resolvedSrc = candidates[attempt];
  const showImage = Boolean(resolvedSrc);

  return (
    <div
      className={[s.thumb, className ?? ''].filter(Boolean).join(' ')}
      style={{ width: w, height: h, background: thumbGradient(seed) }}
      aria-hidden
    >
      {showImage ? (
        <img
          className={s.image}
          src={resolvedSrc}
          alt=""
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setAttempt((current) => current + 1)}
        />
      ) : null}
      <span className={s.highlight} />
      {play ? (
        <span className={s.play}>
          <Icon name="play" size={Math.min(14, Math.floor(Math.min(w, h) * 0.35))} />
        </span>
      ) : null}
    </div>
  );
}
