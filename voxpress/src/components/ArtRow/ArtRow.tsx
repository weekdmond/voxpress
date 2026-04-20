import type { CSSProperties, HTMLAttributes, ReactNode } from 'react';
import s from './ArtRow.module.css';

type CellProps = HTMLAttributes<HTMLDivElement> & { flex?: number; align?: 'left' | 'right' };

function makeCell(defaultCls = '') {
  return function Cell({ flex, align, className, style, children, ...rest }: CellProps) {
    const finalStyle: CSSProperties = {
      flex: flex != null ? `${flex} 1 0` : undefined,
      textAlign: align,
      ...style,
    };
    return (
      <div
        {...rest}
        className={[s.cell, defaultCls, className ?? ''].filter(Boolean).join(' ')}
        style={finalStyle}
      >
        {children}
      </div>
    );
  };
}

const TCell = makeCell(s.textCell);
const Num = makeCell(s.num);
const Mono = makeCell(s.mono);
const Plain = makeCell('');

function Tags({ tags, flex }: { tags: string[]; flex?: number }) {
  return (
    <div
      className={[s.cell, s.tags].join(' ')}
      style={{ flex: flex != null ? `${flex} 1 0` : undefined }}
    >
      {tags.map((t) => (
        <span key={t} className={s.tag}>
          #{t}
        </span>
      ))}
    </div>
  );
}

export interface ArtTableProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}
export function ArtTable({ children, className, ...rest }: ArtTableProps) {
  return (
    <div {...rest} className={[s.wrap, className ?? ''].filter(Boolean).join(' ')}>
      {children}
    </div>
  );
}

export interface ArtHeadProps extends HTMLAttributes<HTMLDivElement> {}
export function ArtHead({ className, children, ...rest }: ArtHeadProps) {
  return (
    <div {...rest} className={[s.head, className ?? ''].filter(Boolean).join(' ')}>
      {children}
    </div>
  );
}
ArtHead.Cell = Plain;

export interface ArtRowProps extends HTMLAttributes<HTMLDivElement> {}
export function ArtRow({ className, children, ...rest }: ArtRowProps) {
  return (
    <div
      role="button"
      tabIndex={0}
      {...rest}
      className={[s.row, className ?? ''].filter(Boolean).join(' ')}
    >
      {children}
    </div>
  );
}
ArtRow.T = TCell;
ArtRow.C = Plain;
ArtRow.Num = Num;
ArtRow.Mono = Mono;
ArtRow.Tags = Tags;
ArtRow.Ellipsis = function Ellipsis({ className, children, ...rest }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span {...rest} className={[s.ellipsis, className ?? ''].filter(Boolean).join(' ')}>
      {children}
    </span>
  );
};
