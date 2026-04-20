import type { ButtonHTMLAttributes, ReactNode } from 'react';
import s from './Button.module.css';

type Variant = 'default' | 'primary' | 'ghost';
type Size = 'sm' | 'md';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
  trailing?: ReactNode;
}

export function Button({
  variant = 'default',
  size = 'md',
  icon,
  trailing,
  children,
  className,
  type = 'button',
  ...rest
}: ButtonProps) {
  const cls = [
    s.btn,
    size === 'sm' ? s.sm : s.md,
    variant === 'primary' ? s.primary : '',
    variant === 'ghost' ? s.ghost : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <button {...rest} type={type} className={cls}>
      {icon ? <span className={s.iconBox}>{icon}</span> : null}
      {children}
      {trailing ? <span className={s.iconBox}>{trailing}</span> : null}
    </button>
  );
}
