import type { HTMLAttributes, ReactNode } from 'react';
import s from './Chip.module.css';

export type ChipVariant = 'default' | 'solid' | 'accent' | 'ok' | 'warn' | 'danger';

export interface ChipProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: ChipVariant;
  live?: boolean;
  mono?: boolean;
  icon?: ReactNode;
}

export function Chip({
  variant = 'default',
  live,
  mono,
  icon,
  children,
  className,
  ...rest
}: ChipProps) {
  const cls = [
    s.chip,
    variant === 'solid' ? s.solid : '',
    variant === 'accent' ? s.accent : '',
    variant === 'ok' ? s.ok : '',
    variant === 'warn' ? s.warn : '',
    variant === 'danger' ? s.danger : '',
    mono ? s.mono : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <span {...rest} className={cls}>
      {live ? <span className={s.dot} aria-hidden /> : null}
      {icon ? <span>{icon}</span> : null}
      {children}
    </span>
  );
}
