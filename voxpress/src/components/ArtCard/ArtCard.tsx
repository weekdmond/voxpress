import { Link } from 'react-router-dom';
import { Avatar, Icon } from '@/components/primitives';
import { formatCount, formatRelative } from '@/lib/format';
import type { Article } from '@/types/api';
import s from './ArtCard.module.css';

export interface ArtCardProps {
  article: Article;
  creatorName: string;
  creatorInitial: string;
}

export function ArtCard({ article, creatorName, creatorInitial }: ArtCardProps) {
  return (
    <Link to={`/articles/${article.id}`} className={s.card}>
      <div className={s.head}>
        <Avatar size="xs" id={article.creator_id} initial={creatorInitial} />
        <span className={s.headName}>{creatorName}</span>
        <span>·</span>
        <span>{formatRelative(article.published_at)}</span>
      </div>
      <h3 className={s.title}>{article.title}</h3>
      <div className={s.foot}>
        <span className={s.num}>{article.word_count.toLocaleString()} 字</span>
        <span>·</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          <Icon name="heart" size={11} />
          <span className={s.num}>{formatCount(article.likes_snapshot)}</span>
        </span>
        <span className={s.tags}>
          {article.tags.slice(0, 2).map((t) => (
            <span key={t} className={s.tag}>
              #{t}
            </span>
          ))}
        </span>
      </div>
    </Link>
  );
}
