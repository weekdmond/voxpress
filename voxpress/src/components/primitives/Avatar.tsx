import { avatarGradient } from '@/lib/gradients';
import s from './Avatar.module.css';

export interface AvatarProps {
  size?: 'xs' | 'sm' | 'md' | 'lg';
  id: number;
  initial: string;
  className?: string;
}

export function Avatar({ size = 'md', id, initial, className }: AvatarProps) {
  const cls = [s.avatar, s[size], className ?? ''].filter(Boolean).join(' ');
  return (
    <span className={cls} style={{ background: avatarGradient(id) }} aria-hidden>
      {initial}
    </span>
  );
}
