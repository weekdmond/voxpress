const BASE = import.meta.env.VITE_API_BASE || '';

function isDouyinMedia(url: URL): boolean {
  const host = url.hostname.toLowerCase();
  return host === 'douyinpic.com' || host.endsWith('.douyinpic.com');
}

export function mediaCandidates(src?: string | null): string[] {
  if (!src) return [];
  try {
    const url = new URL(src);
    if (!isDouyinMedia(url)) return [src];
    const proxy = `${BASE}/api/media?url=${encodeURIComponent(src)}`;
    return Array.from(new Set([proxy, src]));
  } catch {
    return [src];
  }
}
