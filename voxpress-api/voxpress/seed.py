"""Seed dev data matching the frontend fixtures so the real backend
looks identical to the mock mode the frontend has been using.

    uv run python -m voxpress.seed
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from voxpress.db import session_scope
from voxpress.models import Article, Creator, SettingEntry, Task, TranscriptSegment, Video


CREATORS = [
    dict(handle="@laoqian-ai", name="老钱说AI", bio="AI 应用工程师 · 分享每一个技术进化的瞬间。",
         region="北京", verified=True, followers=1_254_000, total_likes=12_030_000, video_count=48),
    dict(handle="@wuhou-keji", name="武侯科技", bio="前 Google 产品经理,聊硅谷 Big Tech 的产品底层思考。",
         region="杭州", verified=True, followers=786_000, total_likes=5_620_000, video_count=52),
    dict(handle="@pumpkin-ceo", name="南瓜CEO", bio="连续创业者 · 把每一次复盘讲明白。",
         region="深圳", verified=False, followers=512_000, total_likes=3_090_000, video_count=37),
    dict(handle="@cody-talks", name="Cody聊技术", bio="前端工程师 · 技术选型 / 架构 / 招聘。",
         region="上海", verified=True, followers=348_000, total_likes=1_760_000, video_count=61),
    dict(handle="@zhiliao-shi", name="知了老师", bio="职场成长 · 向上管理 · 跳槽面试。",
         region="北京", verified=False, followers=260_400, total_likes=1_223_000, video_count=41),
    dict(handle="@mopan-jun", name="磨盘君", bio="硬核财报解读 · 一周一只股票。",
         region="北京", verified=True, followers=180_000, total_likes=760_000, video_count=24),
    dict(handle="@elita-design", name="伊丽塔设计", bio="独立设计师 · 品牌与产品故事。",
         region="上海", verified=False, followers=140_000, total_likes=510_000, video_count=18),
    dict(handle="@hongtian-ai", name="洪天AI", bio="大模型训练 · 论文精读。",
         region="北京", verified=True, followers=98_000, total_likes=412_000, video_count=26),
    dict(handle="@maomao-edu", name="猫猫教英语", bio="沉浸式英语学习 · 每天一点点。",
         region="广州", verified=False, followers=67_000, total_likes=228_000, video_count=14),
    dict(handle="@danai-talk", name="丹奈说", bio="对谈节目 · 让思想落地。",
         region="北京", verified=True, followers=52_000, total_likes=172_000, video_count=19),
    dict(handle="@qingfeng-jun", name="清风君", bio="读书 · 笔记 · 感想。",
         region="成都", verified=False, followers=31_000, total_likes=98_000, video_count=14),
    dict(handle="@tech-haozi", name="郝哥聊技术", bio="SRE 一线老兵 · 稳定性 · 可观测性。",
         region="杭州", verified=False, followers=21_000, total_likes=76_000, video_count=11),
]

ARTICLES = [
    dict(video_seed="v_001", creator_idx=0,
         title="为什么 Qwen2.5-72B 在 M5 Max 上终于跑得动了",
         summary="苹果 M5 Max 的 128GB 统一内存让 72B 级别的 INT4 量化模型第一次可以真正作为本地 writer 使用。",
         tags=["AI", "本地推理"], likes=45_200, word_count=2146,
         segs=[
             (0, "大家好,欢迎回到老钱说AI。今天我们不讲产品,讲硬件。"),
             (12, "M5 Max 最大的变化不在于单核多核,而在于统一内存的调度。"),
             (38, "这意味着 72B 模型 INT4 量化之后,我们在 llama.cpp Metal 后端能稳定拿到 28 tokens/sec。"),
             (72, "但只有吞吐还不够。真正让它可用的,是首 token 延迟和上下文扩展。"),
             (118, "我们用 VoxPress 自己的整理任务当 benchmark。单篇 3000 字文章,从原始逐字稿到成品,平均 42 秒。"),
         ]),
    dict(video_seed="v_002", creator_idx=1,
         title="一个产品经理的周五:把 Figma 交付链路磨薄",
         summary="设计-开发的断裂往往发生在周四晚上。把交付清单压缩到三条,团队每周省下半天。",
         tags=["产品", "工作流"], likes=18_300, word_count=1820,
         segs=[
             (0, "今天是周五,产品经理的一天应该这样开始:先看昨天有没有没回的设计评审。"),
             (24, "我发现 80% 的交付断裂,都卡在周四晚上的那一份 spec 上。"),
             (64, "我们用一个 Figma 插件 + 结构化 spec 模板,把交付清单从十二条压到三条。"),
         ]),
    dict(video_seed="v_003", creator_idx=2,
         title="二次创业者最难承认的三件事",
         summary="上一家公司的成功惯性会成为下一家的包袱。",
         tags=["创业"], likes=8_700, word_count=2480,
         segs=[(0, "第一家公司成功之后再出发,最容易犯的不是技术错误,而是心态错误。")]),
    dict(video_seed="v_004", creator_idx=3,
         title="React Server Components 在 2026 的落地姿势",
         summary="RSC 从实验走进主流,但它不是 SSR 的替代品。",
         tags=["前端", "React"], likes=16_500, word_count=2950,
         segs=[(0, "过去两年大家都在等 RSC,但真正把它用在生产里的团队不多。")]),
    dict(video_seed="v_005", creator_idx=4,
         title="向上管理不是拍马屁,而是换个人替你发声",
         summary="向上管理的本质是信息不对称的修补。",
         tags=["职场"], likes=23_400, word_count=1440,
         segs=[(0, "每次听到“向上管理”被翻译成“会说话”,我就想反驳。")]),
    dict(video_seed="v_006", creator_idx=5,
         title="把财报读成故事:看营收质量而不是营收数字",
         summary="季报的同比增速像照片,营收质量像视频。",
         tags=["投资"], likes=6_400, word_count=1780,
         segs=[(0, "很多人读财报只看同比,那是照片。")]),
]


async def seed() -> None:
    async with session_scope() as s:
        # Clear (order respects FKs)
        await s.execute(delete(Task))
        await s.execute(delete(TranscriptSegment))
        await s.execute(delete(Article))
        await s.execute(delete(Video))
        await s.execute(delete(Creator))
        await s.execute(delete(SettingEntry))

    creator_rows: list[Creator] = []
    async with session_scope() as s:
        for i, c in enumerate(CREATORS):
            row = Creator(
                platform="douyin",
                external_id=f"sec_{i + 1}",
                handle=c["handle"],
                name=c["name"],
                bio=c["bio"],
                region=c["region"],
                verified=c["verified"],
                followers=c["followers"],
                total_likes=c["total_likes"],
                video_count=c["video_count"],
                recent_update_at=datetime.now(tz=timezone.utc) - timedelta(days=i),
            )
            s.add(row)
            creator_rows.append(row)
        await s.flush()

        base_published = datetime(2026, 4, 18, tzinfo=timezone.utc)
        video_rows: list[Video] = []
        # Add extra videos per creator for the /import flow
        for i, creator in enumerate(creator_rows):
            for k in range(6):
                vid = f"v_c{creator.id}_{k + 1}"
                video_rows.append(
                    Video(
                        id=vid,
                        creator_id=creator.id,
                        title=f"{creator.name} · 第 {k + 1} 期",
                        duration_sec=180 + (k * 37) % 900,
                        likes=3000 + (k * 1723) % 240_000,
                        plays=50_000 + (k * 13567) % 2_400_000,
                        comments=120 + (k * 83) % 1800,
                        shares=60 + (k * 41) % 900,
                        collects=200 + (k * 97) % 2400,
                        published_at=base_published - timedelta(days=k * 3 + i),
                        cover_url=None,
                        source_url=f"https://www.douyin.com/video/{vid}",
                    )
                )
        for v in video_rows:
            s.add(v)
        await s.flush()

        # Add the specific articles with their deterministic videos
        articles: list[Article] = []
        for j, meta in enumerate(ARTICLES):
            c = creator_rows[meta["creator_idx"]]
            vid = f"v_c{c.id}_article_{j + 1}"
            video = Video(
                id=vid,
                creator_id=c.id,
                title=meta["title"],
                duration_sec=512 - j * 13,
                likes=meta["likes"],
                plays=meta["likes"] * 20,
                comments=meta["likes"] // 40,
                shares=meta["likes"] // 80,
                collects=meta["likes"] // 5,
                published_at=base_published - timedelta(days=j),
                cover_url=None,
                source_url=f"https://www.douyin.com/video/{vid}",
            )
            s.add(video)
            await s.flush()
            art = Article(
                id=uuid.uuid4(),
                video_id=video.id,
                creator_id=c.id,
                title=meta["title"],
                summary=meta["summary"],
                content_md=f"# {meta['title']}\n\n> {meta['summary']}\n\n"
                + "\n\n".join(
                    [
                        "这是由 seed 脚本写入的占位正文。真实文章由 LLM 整理。",
                        "第二段:系统已经跑通 — 前端、API、DB、SSE、pipeline stub 全部联调。",
                        f"来源提示:{c.name} · {c.handle}。",
                    ]
                ),
                content_html=(
                    f"<h1>{meta['title']}</h1>"
                    f"<p class=\"sum\">{meta['summary']}</p>"
                    "<p>这是由 seed 脚本写入的占位正文。真实文章由 LLM 整理。</p>"
                    "<p>系统已经跑通 — 前端、API、DB、SSE、pipeline stub 全部联调。</p>"
                    f"<blockquote>来源:{c.name} · {c.handle}</blockquote>"
                ),
                word_count=meta["word_count"],
                tags=meta["tags"],
                likes_snapshot=meta["likes"],
                published_at=video.published_at,
            )
            s.add(art)
            articles.append(art)
            await s.flush()
            for idx, (ts, text) in enumerate(meta["segs"]):
                s.add(
                    TranscriptSegment(article_id=art.id, idx=idx, ts_sec=ts, text=text)
                )

        # Default settings row
        s.add(
            SettingEntry(
                key="prompt",
                value={
                    "version": "v1.0",
                    "template": "你是一位严谨的中文编辑。把下面这段口播转写整理成一篇结构化的文章,保留原作者的语气。",
                },
            )
        )

    async with session_scope() as s:
        total_creators = len((await s.scalars(select(Creator))).all())
        total_articles = len((await s.scalars(select(Article))).all())
        total_videos = len((await s.scalars(select(Video))).all())
    print(f"seeded: creators={total_creators} videos={total_videos} articles={total_articles}")


if __name__ == "__main__":
    asyncio.run(seed())
