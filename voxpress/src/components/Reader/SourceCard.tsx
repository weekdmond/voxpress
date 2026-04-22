import { Fragment } from 'react';
import type { ArticleSource } from '@/types/api';
import { formatCountZh, formatDuration } from '@/lib/format';
import { Icon, type IconName } from '@/components/primitives';
import s from './Reader.module.css';

export function SourceCard({ source }: { source: ArticleSource }) {
  const platformLabel = source.platform === 'douyin' ? '抖音' : source.platform;
  const creatorHandle = source.creator_snapshot.handle.startsWith('@')
    ? source.creator_snapshot.handle
    : `@${source.creator_snapshot.handle}`;
  const items: Array<{ key: string; text: string; icon: IconName; tone?: 'accent' }> = [
    { key: 'platform', text: platformLabel, icon: 'wave' },
    { key: 'creator', text: creatorHandle, icon: 'user' },
    { key: 'duration', text: `${formatDuration(source.duration_sec)} 时长`, icon: 'clock' },
    { key: 'likes', text: `${formatCountZh(source.metrics.likes)}赞`, icon: 'heart', tone: 'accent' },
    { key: 'comments', text: `${formatCountZh(source.metrics.comments)}评论`, icon: 'comment' },
    { key: 'collects', text: `${formatCountZh(source.metrics.collects)}收藏`, icon: 'bookmark' },
    {
      key: 'followers',
      text: `${formatCountZh(source.creator_snapshot.followers)}粉`,
      icon: 'users',
    },
  ];

  if (source.metrics.plays > 0) {
    items.splice(5, 0, {
      key: 'plays',
      text: `${formatCountZh(source.metrics.plays)}播放`,
      icon: 'play',
    });
  }

  return (
    <div className={s.sourceCard}>
      {items.map((item, index) => (
        <Fragment key={item.key}>
          <span
            className={[s.sourceInlineItem, item.tone === 'accent' ? s.sourceInlineAccent : ''].join(' ')}
            title={item.text}
          >
            <span className={s.sourceInlineIcon}>
              <Icon name={item.icon} size={12.5} />
            </span>
            <span className={s.sourceInlineValue}>{item.text}</span>
          </span>
          {index < items.length - 1 ? <span className={s.sourceDivider}>·</span> : null}
        </Fragment>
      ))}
      <span className={s.sourceDivider}>·</span>
      <a
        className={s.sourceInlineLink}
        href={source.source_url}
        target="_blank"
        rel="noreferrer"
      >
        <Icon name="external" size={12.5} />
        <span>原视频</span>
      </a>
    </div>
  );
}
