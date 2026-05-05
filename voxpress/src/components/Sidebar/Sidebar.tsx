import { NavLink, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Icon } from '@/components/primitives';
import { Avatar } from '@/components/primitives';
import { api } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import type { Creator, Health, Page } from '@/types/api';
import type { IconName } from '@/components/primitives';
import { SpeechFolioMark } from '@/components/Brand/SpeechFolioMark';
import s from './Sidebar.module.css';
import { useSseStatus } from '@/features/tasks/useSseStatus';

interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  end?: boolean;
  count?: number;
}

export function Sidebar() {
  const loc = useLocation();

  const { data: creators } = useQuery({
    queryKey: ['creators', 'sidebar'],
    queryFn: () => api.get<Page<Creator>>('/api/creators?sort=followers:desc'),
    staleTime: 60_000,
  });
  const { data: health } = useQuery({
    queryKey: ['health', 'sidebar'],
    queryFn: () => api.get<Health>('/api/health'),
    staleTime: 60_000,
    refetchInterval: 60_000,
  });
  const recent = (creators?.items ?? []).slice(0, 6);

  const items: NavItem[] = [
    { to: '/', label: '首页', icon: 'home', end: true },
    { to: '/library', label: '来源库', icon: 'users', count: creators?.total },
    { to: '/tasks', label: '任务', icon: 'swap' },
    { to: '/articles', label: '文章', icon: 'doc' },
    { to: '/settings', label: '设置', icon: 'cog' },
  ];

  const status = useSseStatus();
  const statusLabel =
    status === 'open' ? 'SpeechFolio 服务 · 运行中' : status === 'connecting' ? '连接中' : '已断开';
  const statusCls = status === 'open' ? s.ok : status === 'connecting' ? s.warn : s.bad;
  const deployLabel = health?.deploy_commit
    ? `${health.version} · ${health.deploy_commit.slice(0, 7)}`
    : health?.version ?? 'v0.4.0';
  const deployedAtLabel = health?.deployed_at ? formatDateTime(health.deployed_at) : '未部署';

  return (
    <aside className={s.sidebar}>
      <div className={s.brand}>
        <div className={s.brandMark}>
          <SpeechFolioMark className={s.brandMarkIcon} aria-hidden="true" />
        </div>
        <div>
          <div className={s.brandName}>
            <span>Speech</span>
            <span className={s.brandAccent}>Folio</span>
          </div>
        </div>
        <div className={s.brandVersion}>v0.4</div>
      </div>

      <nav className={s.section} aria-label="主导航">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              [s.item, isActive ? s.active : ''].filter(Boolean).join(' ')
            }
          >
            <Icon name={item.icon} size={15} />
            <span className={s.itemLabel}>{item.label}</span>
            {item.count != null ? <span className={s.count}>{item.count}</span> : null}
          </NavLink>
        ))}
      </nav>

      <div className={s.section}>
        <div className={s.sectionTitle}>最近来源</div>
        <div className={s.recent}>
          {recent.map((c) => (
            <NavLink
              key={c.id}
              to={`/library/${c.id}`}
              className={s.creator}
            >
              <Avatar size="sm" id={c.id} initial={c.initial} src={c.avatar_url} />
              <span className={s.creatorName}>{c.name}</span>
              <span className={s.creatorCount}>{c.article_count}</span>
            </NavLink>
          ))}
          {recent.length === 0 ? (
            <div style={{ padding: '8px 10px', color: 'var(--vp-ink-3)', fontSize: 12 }}>暂无</div>
          ) : null}
        </div>
      </div>

      <div className={s.status}>
        <div className={s.statusRow} title={`SSE ${status} · ${loc.pathname}`}>
          <span className={[s.statusDot, statusCls].join(' ')} />
          <span>{statusLabel}</span>
        </div>
        <div className={s.metaRow}>
          <span>版本</span>
          <b>{deployLabel}</b>
        </div>
        <div className={s.metaRow}>
          <span>更新</span>
          <b>{deployedAtLabel}</b>
        </div>
      </div>
    </aside>
  );
}
