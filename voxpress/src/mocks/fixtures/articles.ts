import type { Article, ArticleDetail } from '@/types/api';

const base: Omit<Article, 'id' | 'video_id' | 'creator_id' | 'title' | 'summary' | 'content_md' | 'content_html' | 'word_count' | 'tags' | 'likes_snapshot' | 'published_at'> = {
  created_at: '2026-04-18T12:00:00Z',
  updated_at: '2026-04-18T12:00:00Z',
};

const html = (body: string) => `<h1>占位</h1><p class="sum">${body.slice(0, 60)}…</p><p>${body}</p>`;

export const articles: Article[] = [
  {
    id: 'a_001',
    video_id: 'v_001',
    creator_id: 1,
    title: '为什么 Qwen2.5-72B 在 M5 Max 上终于跑得动了',
    summary: '苹果 M5 Max 的 128GB 统一内存让 72B 级别的 INT4 量化模型第一次可以真正作为本地 writer 使用。',
    content_md: '# 为什么 Qwen2.5-72B ...\n正文',
    content_html: html('从 M5 到 M5 Max 的跳跃,最大的变化不是 CPU,而是统一内存的带宽和调度策略。今天我们实测 Qwen2.5-72B INT4 在 llama.cpp Metal 后端的吞吐,以及它作为本地 writer 的工程可行性。'),
    word_count: 2146,
    tags: ['AI', '本地推理'],
    likes_snapshot: 45200,
    published_at: '2026-04-18T11:00:00Z',
    ...base,
  },
  {
    id: 'a_002',
    video_id: 'v_002',
    creator_id: 2,
    title: '一个产品经理的周五:把 Figma 交付链路磨薄',
    summary: '设计-开发的断裂往往发生在周四晚上。把交付清单压缩到三条,团队每周省下半天。',
    content_md: '# 交付链路\n正文',
    content_html: html('大公司里设计和开发的信息差,是每一次周四晚上 PM 最焦虑的来源。今天讲我们如何用一个 Figma 插件 + 一份结构化 spec 模板,把交付链路压到三条。'),
    word_count: 1820,
    tags: ['产品', '工作流'],
    likes_snapshot: 18300,
    published_at: '2026-04-17T15:22:00Z',
    ...base,
  },
  {
    id: 'a_003',
    video_id: 'v_003',
    creator_id: 3,
    title: '二次创业者最难承认的三件事',
    summary: '上一家公司的成功惯性会成为下一家的包袱。三件事 — 用户、节奏、团队 — 是重启的钝刀。',
    content_md: '# 二次创业\n正文',
    content_html: html('第一家公司成功之后再出发,最容易犯的不是技术错误,而是心态错误。讲讲我复盘第二家公司前六个月,学到的三件事。'),
    word_count: 2480,
    tags: ['创业'],
    likes_snapshot: 8700,
    published_at: '2026-04-16T21:02:00Z',
    ...base,
  },
  {
    id: 'a_004',
    video_id: 'v_004',
    creator_id: 4,
    title: 'React Server Components 在 2026 的落地姿势',
    summary: 'RSC 从实验走进主流,但它不是 SSR 的替代品,而是一种新的工程切分方式。',
    content_md: '# RSC\n正文',
    content_html: html('过去两年大家都在等 RSC,但真正把它用在生产里的团队不多。今天讲清楚:RSC 解决的是什么问题,它与 SSR 的关系,以及 2026 年的合理落地姿势。'),
    word_count: 2950,
    tags: ['前端', 'React'],
    likes_snapshot: 16500,
    published_at: '2026-04-16T10:41:00Z',
    ...base,
  },
  {
    id: 'a_005',
    video_id: 'v_005',
    creator_id: 5,
    title: '向上管理不是拍马屁,而是换个人替你发声',
    summary: '向上管理的本质是信息不对称的修补。不是讨好,而是让老板的数据看板更干净。',
    content_md: '# 向上管理\n正文',
    content_html: html('每次听到"向上管理"被翻译成"会说话",我就想反驳。它真正的内核是帮老板减负,帮他在别人面前讲清楚你的事。'),
    word_count: 1440,
    tags: ['职场'],
    likes_snapshot: 23400,
    published_at: '2026-04-10T09:12:00Z',
    ...base,
  },
  {
    id: 'a_006',
    video_id: 'v_006',
    creator_id: 6,
    title: '把财报读成故事:看营收质量而不是营收数字',
    summary: '季报的同比增速像照片,营收质量像视频。拉长时间轴看,故事就浮出来。',
    content_md: '# 财报\n正文',
    content_html: html('很多人读财报只看同比,那是照片。把最近十二个季度的营收质量放进一张图,你会看到一段完全不同的故事。'),
    word_count: 1780,
    tags: ['投资'],
    likes_snapshot: 6400,
    published_at: '2026-04-12T18:20:00Z',
    ...base,
  },
];

export const articleDetails: Record<string, ArticleDetail> = {
  a_001: {
    ...articles[0],
    source: {
      platform: 'douyin',
      source_url: 'https://www.douyin.com/video/7291234567890123456',
      duration_sec: 512,
      metrics: { likes: 45200, comments: 1283, shares: 4612, collects: 8820, plays: 986400 },
      topics: ['AI', '本地推理', 'Apple Silicon'],
      creator_snapshot: {
        name: '老钱说AI',
        handle: '@laoqian-ai',
        followers: 1254000,
        verified: true,
        region: '北京',
      },
    },
    segments: [
      { ts_sec: 0, text: '大家好,欢迎回到老钱说AI。今天我们不讲产品,讲硬件。' },
      { ts_sec: 12, text: 'M5 Max 最大的变化不在于单核多核,而在于统一内存的调度。' },
      { ts_sec: 38, text: '这意味着 72B 模型 INT4 量化之后,我们在 llama.cpp Metal 后端能稳定拿到 28 tokens/sec。' },
      { ts_sec: 72, text: '但只有吞吐还不够。真正让它可用的,是首 token 延迟和上下文扩展。' },
      { ts_sec: 118, text: '我们用 VoxPress 自己的整理任务当 benchmark。单篇 3000 字文章,从原始逐字稿到成品,平均 42 秒。' },
      { ts_sec: 168, text: '对比 A100 云端部署,本地贵在隐私和随手用,代价是冷启动。' },
      { ts_sec: 240, text: '最后讲一下,如果你手上是 M4 Max 64GB,现实的选择还是 32B 级别的模型。' },
    ],
  },
  a_002: {
    ...articles[1],
    source: {
      platform: 'douyin',
      source_url: 'https://www.douyin.com/video/7291234567890000002',
      duration_sec: 402,
      metrics: { likes: 18300, comments: 822, shares: 1944, collects: 3660, plays: 412300 },
      topics: ['产品', 'Figma', '交付'],
      creator_snapshot: {
        name: '武侯科技',
        handle: '@wuhou-keji',
        followers: 786000,
        verified: true,
        region: '杭州',
      },
    },
    segments: [
      { ts_sec: 0, text: '今天是周五,产品经理的一天应该这样开始:先看昨天有没有没回的设计评审。' },
      { ts_sec: 24, text: '我发现 80% 的交付断裂,都卡在周四晚上的那一份 spec 上。' },
      { ts_sec: 64, text: '我们用一个 Figma 插件 + 结构化 spec 模板,把交付清单从十二条压到三条。' },
      { ts_sec: 138, text: '每周省下的时间,大概是半天。' },
    ],
  },
};

for (const a of articles) {
  if (!articleDetails[a.id]) {
    articleDetails[a.id] = {
      ...a,
      source: {
        platform: 'douyin',
        source_url: `https://www.douyin.com/video/${a.video_id}`,
        duration_sec: 360,
        metrics: { likes: a.likes_snapshot, comments: 620, shares: 1200, collects: 2300, plays: 284000 },
        topics: a.tags,
        creator_snapshot: {
          name: '创作者',
          handle: '@placeholder',
          followers: 100000,
          verified: false,
          region: null,
        },
      },
      segments: [
        { ts_sec: 0, text: '这是一段示例逐字稿。' },
        { ts_sec: 28, text: '真实内容会由 whisper 生成。' },
      ],
    };
  }
}
