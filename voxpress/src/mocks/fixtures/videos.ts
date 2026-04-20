import type { Video } from '@/types/api';

function mkVideos(creatorId: number, count: number): Video[] {
  const out: Video[] = [];
  const base = Date.parse('2026-04-18T00:00:00Z');
  for (let i = 0; i < count; i++) {
    const id = `v_c${creatorId}_${i + 1}`;
    out.push({
      id,
      creator_id: creatorId,
      title: `${['M5 Max 实测', '周末复盘', '对谈', 'Claude 4.7 体验', '职场避坑', '产品节奏', '创业难点', '技术面试'][i % 8]} · 第 ${i + 1} 期`,
      duration_sec: 180 + ((i * 37) % 900),
      likes: 3000 + ((i * 1723) % 240000),
      plays: 50000 + ((i * 13567) % 2_400_000),
      comments: 120 + ((i * 83) % 1800),
      shares: 60 + ((i * 41) % 900),
      collects: 200 + ((i * 97) % 2400),
      published_at: new Date(base - i * 86_400_000 * (0.8 + (i % 3) * 0.4)).toISOString(),
      cover_url: null,
      source_url: `https://www.douyin.com/video/${id}`,
      article_id: i < 2 ? `pseudo_${id}` : null,
    });
  }
  return out;
}

export const videosByCreator: Record<number, Video[]> = {
  1: mkVideos(1, 24),
  2: mkVideos(2, 18),
  3: mkVideos(3, 14),
  4: mkVideos(4, 22),
  5: mkVideos(5, 11),
  6: mkVideos(6, 9),
  7: mkVideos(7, 7),
  8: mkVideos(8, 12),
  9: mkVideos(9, 5),
  10: mkVideos(10, 8),
  11: mkVideos(11, 6),
  12: mkVideos(12, 5),
};
