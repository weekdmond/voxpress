import type { ReactNode } from 'react';
import { useEffect } from 'react';
import { Button } from './Button';
import s from './ConfirmDialog.module.css';

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  children?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  pending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  children,
  confirmLabel = '确认',
  cancelLabel = '取消',
  pending = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !pending) onCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, pending, onCancel]);

  if (!open) return null;

  return (
    <>
      <div className={s.scrim} onClick={pending ? undefined : onCancel} />
      <div className={s.dialog} role="dialog" aria-modal="true" aria-label={title}>
        <div className={s.body}>
          <div className={s.title}>{title}</div>
          {description ? <div className={s.desc}>{description}</div> : null}
          {children ? <div className={s.content}>{children}</div> : null}
        </div>
        <div className={s.actions}>
          <Button size="sm" onClick={onCancel} disabled={pending}>
            {cancelLabel}
          </Button>
          <Button size="sm" variant="primary" onClick={onConfirm} disabled={pending}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </>
  );
}
