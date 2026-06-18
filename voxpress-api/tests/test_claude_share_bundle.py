import uuid
from datetime import datetime, timezone

from voxpress.models import Article, Creator, Transcript, Video
from voxpress.routers.articles import _build_claude_bundle


def test_claude_bundle_guides_loyal_article_optimization() -> None:
    article_id = uuid.uuid4()
    now = datetime(2026, 6, 18, 10, 0, tzinfo=timezone.utc)
    creator = Creator(
        id=1,
        platform="douyin",
        external_id="creator-1",
        handle="@creator",
        name="创作者",
        followers=100,
    )
    video = Video(
        id="video-1",
        creator_id=1,
        title="视频标题",
        duration_sec=754,
        likes=10,
        plays=100,
        comments=1,
        shares=2,
        collects=3,
        published_at=now,
        source_url="https://example.com/video/1",
    )
    article = Article(
        id=article_id,
        video_id="video-1",
        creator_id=1,
        title="系统整理稿",
        summary="摘要",
        content_md="# 系统整理稿\n\n这是当前整理稿。",
        content_html="<h1>系统整理稿</h1>",
        word_count=1800,
        tags=["投资"],
        topics=["金融投资/股票市场"],
        entities={"people": ["张三"]},
        likes_snapshot=10,
        published_at=now,
    )
    transcript = Transcript(video_id="video-1", raw_text="这是逐字稿。", segments=[])

    bundle = _build_claude_bundle(
        [(article, creator, video, transcript)],
        created_at=now,
    )

    assert "不是写微信公众号营销文" in bundle
    assert "不是摘要任务" in bundle
    assert "不串改观点" in bundle
    assert "完整文章，而不是压缩成精简摘要" in bundle
    assert "- 视频时长: 12:34" in bundle
    assert "- 当前整理稿字数: 1800" in bundle
    assert "### SpeechFolio 当前整理稿（参考）" in bundle
