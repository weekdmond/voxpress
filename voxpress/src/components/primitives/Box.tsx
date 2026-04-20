import type { HTMLAttributes, ReactNode } from 'react';
import s from './Box.module.css';

export interface BoxProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'soft' | 'lifted';
  flush?: boolean;
  children?: ReactNode;
}

export function Box({ variant = 'default', flush, className, children, ...rest }: BoxProps) {
  const cls = [
    s.box,
    variant === 'soft' ? s.soft : '',
    variant === 'lifted' ? s.lifted : '',
    flush ? s.flush : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <div {...rest} className={cls}>
      {children}
    </div>
  );
}

export interface RowProps extends HTMLAttributes<HTMLDivElement> {
  between?: boolean;
  wrap?: boolean;
  gap?: number;
}
export function Row({ between, wrap, gap, className, style, children, ...rest }: RowProps) {
  const cls = [s.row, between ? s.rowBetween : '', wrap ? s.rowWrap : '', className ?? '']
    .filter(Boolean)
    .join(' ');
  const finalStyle = gap != null ? { ...style, gap } : style;
  return (
    <div {...rest} className={cls} style={finalStyle}>
      {children}
    </div>
  );
}

export interface ColProps extends HTMLAttributes<HTMLDivElement> {
  gap?: number;
}
export function Col({ gap, className, style, children, ...rest }: ColProps) {
  const finalStyle = gap != null ? { ...style, gap } : style;
  return (
    <div {...rest} className={[s.col, className ?? ''].filter(Boolean).join(' ')} style={finalStyle}>
      {children}
    </div>
  );
}

export function Divider({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return <div className={[s.divider, className ?? ''].filter(Boolean).join(' ')} style={style} role="separator" />;
}
