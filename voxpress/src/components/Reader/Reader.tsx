import type { ReactNode } from 'react';
import s from './Reader.module.css';

export function Reader({ children }: { children: ReactNode }) {
  return <div className={s.reader}>{children}</div>;
}

export function ReaderToolbar({ left, right }: { left: ReactNode; right: ReactNode }) {
  return (
    <div className={s.toolbar}>
      <div className={s.toolbarLeft}>{left}</div>
      <div className={s.toolbarRight}>{right}</div>
    </div>
  );
}

export function ReaderBody({ split, children }: { split?: boolean; children: ReactNode }) {
  return <div className={[s.body, split ? s.split : ''].join(' ')}>{children}</div>;
}

export function ReaderArticle({
  html,
  source,
  children,
}: {
  html?: string;
  source?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <article className={`${s.article} reader-article`}>
      {children ? (
        children
      ) : (
        <>
          {source}
          {html ? <div dangerouslySetInnerHTML={{ __html: html }} /> : null}
        </>
      )}
    </article>
  );
}

export { SourceCard } from './SourceCard';
export { Drawer } from './Drawer';
