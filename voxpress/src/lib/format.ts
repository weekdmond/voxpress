export function formatCount(n: number): string {
  if (n < 1000) return `${n}`;
  if (n < 10000) return `${(n / 1000).toFixed(1).replace(/\.0$/, '')}k`;
  // Chinese 万 for >= 10000
  const w = n / 10000;
  if (w < 100) return `${w.toFixed(1).replace(/\.0$/, '')}w`;
  return `${Math.round(w)}w`;
}

export function formatCountZh(n: number): string {
  if (n < 10000) return `${n}`;
  if (n < 100000000) {
    const w = n / 10000;
    if (w < 100) return `${w.toFixed(1).replace(/\.0$/, '')}万`;
    return `${Math.round(w)}万`;
  }
  const yi = n / 100000000;
  return `${yi.toFixed(1).replace(/\.0$/, '')}亿`;
}

export function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  if (m >= 60) {
    const h = Math.floor(m / 60);
    return `${h}:${(m % 60).toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function formatEta(sec: number | null | undefined): string {
  if (!sec || sec <= 0) return '';
  return `~${formatDuration(sec)} 剩余`;
}

export function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  const diff = Date.now() - then;
  const min = 60 * 1000;
  const hr = 60 * min;
  const day = 24 * hr;
  if (diff < min) return '刚刚';
  if (diff < hr) return `${Math.floor(diff / min)} 分钟前`;
  if (diff < day) return `${Math.floor(diff / hr)} 小时前`;
  if (diff < 2 * day) return '昨天';
  if (diff < 7 * day) return `${Math.floor(diff / day)} 天前`;
  const d = new Date(iso);
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

export function formatMoney(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return '¥0.00';
  return `¥${n.toFixed(n < 1 ? 4 : 2).replace(/0+$/, '').replace(/\.$/, '.00')}`;
}

export function formatDurationMs(ms: number | null | undefined): string {
  if (!ms || ms <= 0) return '—';
  if (ms < 1000) return `${ms}ms`;
  const sec = Math.round(ms / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  return rem === 0 ? `${min}m` : `${min}m ${rem}s`;
}

export function firstGrapheme(s: string): string {
  if (!s) return '?';
  const stripped = s.replace(/^@/, '');
  return Array.from(stripped)[0] ?? '?';
}
