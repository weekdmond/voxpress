import type { CSSProperties } from 'react';

export type IconName =
  | 'home'
  | 'users'
  | 'doc'
  | 'cog'
  | 'search'
  | 'arrow-right'
  | 'arrow-left'
  | 'download'
  | 'wave'
  | 'sparkle'
  | 'check'
  | 'play'
  | 'heart'
  | 'swap'
  | 'refresh'
  | 'tag'
  | 'external'
  | 'chevron';

export interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
  style?: CSSProperties;
}

export function Icon({ name, size = 14, className, style }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      aria-hidden="true"
      className={className}
      style={{ flexShrink: 0, ...style }}
    >
      <use href={`/icons.svg#i-${name}`} />
    </svg>
  );
}
