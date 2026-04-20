import type { ArticleSource } from '@/types/api';
import { formatCount, formatDuration } from '@/lib/format';
import s from './Reader.module.css';

export function SourceCard({ source }: { source: ArticleSource }) {
  const rows: Array<[string, string]> = [
    ['平台', source.platform],
    ['时长', formatDuration(source.duration_sec)],
    ['点赞', formatCount(source.metrics.likes)],
    ['播放', formatCount(source.metrics.plays)],
    ['评论', formatCount(source.metrics.comments)],
    ['收藏', formatCount(source.metrics.collects)],
    ['博主', source.creator_snapshot.handle],
    ['粉丝', formatCount(source.creator_snapshot.followers)],
  ];
  return (
    <div className={s.sourceCard}>
      {rows.map(([k, v]) => (
        <div key={k} className={s.sourceItem}>
          <span className={s.sourceKey}>{k}</span>
          <span className={s.sourceVal}>{v}</span>
        </div>
      ))}
      <div className={s.sourceItem} style={{ gridColumn: 'span 2' }}>
        <span className={s.sourceKey}>原链接</span>
        <a
          className={s.sourceVal}
          href={source.source_url}
          target="_blank"
          rel="noreferrer"
          style={{ color: 'var(--vp-accent-2)' }}
        >
          {source.source_url}
        </a>
      </div>
    </div>
  );
}
