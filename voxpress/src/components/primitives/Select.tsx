import type { ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';
import s from './Select.module.css';

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {}
export function Select({ className, children, ...rest }: SelectProps) {
  return (
    <select {...rest} className={[s.sel, className ?? ''].filter(Boolean).join(' ')}>
      {children}
    </select>
  );
}

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {}
export function Textarea({ className, ...rest }: TextareaProps) {
  return <textarea {...rest} className={[s.ta, className ?? ''].filter(Boolean).join(' ')} />;
}

export interface FieldProps {
  label: string;
  help?: ReactNode;
  children: ReactNode;
}
export function Field({ label, help, children }: FieldProps) {
  return (
    <div className={s.field}>
      <label className={s.fieldLabel}>{label}</label>
      <div className={s.fieldCtl}>
        {children}
        {help ? <div className={s.fieldHelp}>{help}</div> : null}
      </div>
    </div>
  );
}
