import { useEffect, useState } from 'react';
import { avatarGradient } from '@/lib/gradients';
import { mediaCandidates } from '@/lib/media';
import s from './Avatar.module.css';

export interface AvatarProps {
  size?: 'xs' | 'sm' | 'md' | 'lg';
  id: number;
  initial: string;
  src?: string | null;
  className?: string;
}

export function Avatar({ size = 'md', id, initial, src, className }: AvatarProps) {
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setAttempt(0);
  }, [src]);

  const cls = [s.avatar, s[size], className ?? ''].filter(Boolean).join(' ');
  const candidates = mediaCandidates(src);
  const resolvedSrc = candidates[attempt];
  const showImage = Boolean(resolvedSrc);

  return (
    <span className={cls} style={{ background: avatarGradient(id) }} aria-hidden>
      {showImage ? (
        <img
          className={s.image}
          src={resolvedSrc}
          alt=""
          referrerPolicy="no-referrer"
          onError={() => setAttempt((current) => current + 1)}
        />
      ) : (
        initial
      )}
    </span>
  );
}
