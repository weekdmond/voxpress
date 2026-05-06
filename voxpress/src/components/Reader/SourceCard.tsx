import { Fragment } from 'react';
import type { ArticleSource } from '@/types/api';
import { formatCountZh, formatDuration } from '@/lib/format';
import { Icon, type IconName } from '@/components/primitives';
import s from './Reader.module.css';

export function SourceCard({ source }: { source: ArticleSource }) {
  const platformLabel = source.platform === 'youtube' ? 'YouTube' : source.platform === 'douyin' ? '抖音' : source.platform;
  const creatorHandle = source.creator_snapshot.handle.startsWith('@')
    ? source.creator_snapshot.handle
    : `@${source.creator_snapshot.handle}`;
  const items: Array<{ key: string; text: string; icon: IconName; tone?: 'accent' }> = [
    { key: 'platform', text: platformLabel, icon: 'wave' },
    { key: 'creator', text: creatorHandle, icon: 'user' },
    { key: 'duration', text: source.duration_sec ? `${formatDuration(source.duration_sec)} 时长` : '时长未知', icon: 'clock' },
    { key: 'likes', text: source.metrics.likes > 0 ? `${formatCountZh(source.metrics.likes)}赞` : '赞数未知', icon: 'heart', tone: 'accent' },
    { key: 'comments', text: source.metrics.comments > 0 ? `${formatCountZh(source.metrics.comments)}评论` : '评论未知', icon: 'comment' },
    { key: 'collects', text: source.metrics.collects > 0 ? `${formatCountZh(source.metrics.collects)}收藏` : '收藏未知', icon: 'bookmark' },
    {
      key: 'followers',
      text: source.creator_snapshot.followers > 0 ? `${formatCountZh(source.creator_snapshot.followers)}粉` : '粉丝未知',
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
      {source.platform === 'youtube' ? <YouTubeEmbed sourceUrl={source.source_url} /> : null}
    </div>
  );
}

function YouTubeEmbed({ sourceUrl }: { sourceUrl: string }) {
  const videoId = getYouTubeVideoId(sourceUrl);
  if (!videoId) return null;
  return (
    <div className={s.youtubeEmbed}>
      <iframe
        src={`https://www.youtube.com/embed/${videoId}`}
        title="YouTube video player"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
        allowFullScreen
      />
    </div>
  );
}

function getYouTubeVideoId(url: string): string | null {
  try {
    const parsed = new URL(url);
    if (parsed.hostname === 'youtu.be') return parsed.pathname.slice(1) || null;
    if (parsed.pathname === '/watch') return parsed.searchParams.get('v');
    if (parsed.pathname.startsWith('/shorts/')) return parsed.pathname.split('/')[2] ?? null;
    if (parsed.pathname.startsWith('/embed/')) return parsed.pathname.split('/')[2] ?? null;
  } catch {
    return null;
  }
  return null;
}
