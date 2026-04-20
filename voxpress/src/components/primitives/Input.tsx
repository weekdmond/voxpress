import type { InputHTMLAttributes, ReactNode } from 'react';
import s from './Input.module.css';

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> {
  size?: 'md' | 'lg';
  leading?: ReactNode;
  trailing?: ReactNode;
  mono?: boolean;
  wrapClassName?: string;
}

export function Input({
  size = 'md',
  leading,
  trailing,
  mono,
  wrapClassName,
  className,
  ...rest
}: InputProps) {
  const wrapCls = [s.wrap, size === 'lg' ? s.lg : s.md, wrapClassName ?? ''].filter(Boolean).join(' ');
  const inputCls = [s.input, mono ? s.mono : '', className ?? ''].filter(Boolean).join(' ');
  return (
    <div className={wrapCls}>
      {leading ? <span className={s.leading}>{leading}</span> : null}
      <input {...rest} className={inputCls} />
      {trailing ? <span className={s.trailing}>{trailing}</span> : null}
    </div>
  );
}
