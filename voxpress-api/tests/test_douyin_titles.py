from voxpress.pipeline.douyin_scraper import (
    ScrapedVideo,
    _iter_awemes,
    _latest_videos_by_publish_time,
    _pick_aweme_title,
)


def test_pick_aweme_title_prefers_author_desc() -> None:
    title = _pick_aweme_title(
        {
            "desc": " 作者自己写的标题 ",
            "recommend_chapter_info": {"chapter_abstract": "平台生成摘要。"},
        },
        fallback="fallback",
    )

    assert title == "作者自己写的标题"


def test_pick_aweme_title_trims_boundary_hashtags() -> None:
    title = _pick_aweme_title({"desc": "#牛市"}, fallback="fallback")

    assert title == "牛市"


def test_pick_aweme_title_uses_generated_chapter_abstract() -> None:
    title = _pick_aweme_title(
        {
            "desc": "",
            "recommend_chapter_info": {
                "chapter_abstract": "美国贫富差距不断扩大，富人通过投资和借债积累财富。第二句不进标题。",
            },
        },
        fallback="fallback",
    )

    assert title == "美国贫富差距不断扩大，富人通过投资和借债积累财富"


def test_pick_aweme_title_uses_non_generic_chapter_when_no_abstract() -> None:
    title = _pick_aweme_title(
        {
            "desc": "",
            "recommend_chapter_info": {
                "recommend_chapter_list": [
                    {"desc": "引言"},
                    {"desc": "投资的重要性"},
                ],
            },
        },
        fallback="fallback",
    )

    assert title == "投资的重要性"


def test_pick_aweme_title_uses_suggested_words_when_no_chapter_info() -> None:
    title = _pick_aweme_title(
        {
            "desc": "",
            "suggest_words": {
                "suggest_words": [
                    {
                        "words": [
                            {"word": ""},
                            {"word": "董宇辉直播被警告不卖货"},
                        ]
                    }
                ]
            },
        },
        fallback="fallback",
    )

    assert title == "董宇辉直播被警告不卖货"


def test_pick_aweme_title_skips_punctuation_suggested_words() -> None:
    title = _pick_aweme_title(
        {
            "desc": "",
            "suggest_words": {
                "suggest_words": [
                    {
                        "words": [
                            {"word": "#"},
                            {"word": "#牛市"},
                        ]
                    }
                ]
            },
        },
        fallback="fallback",
    )

    assert title == "牛市"


def test_pick_aweme_title_falls_back_to_video_id() -> None:
    assert _pick_aweme_title({"desc": ""}, fallback="视频 12345678") == "视频 12345678"


def test_iter_awemes_uses_date_fallback_when_no_title_metadata() -> None:
    class RawPage:
        def _to_raw(self) -> dict:
            return {
                "aweme_list": [
                    {
                        "aweme_id": "7627406985034584244",
                        "create_time": "2026-04-11 12:00:00",
                        "desc": "",
                        "video": {"duration": 1000},
                        "statistics": {},
                    }
                ]
            }

    [video] = _iter_awemes(RawPage())

    assert video.title == "2026-04-11 作品 4244"


def test_latest_videos_by_publish_time_ignores_pinned_feed_order() -> None:
    videos = [
        _video("pinned-2025", 1762107852),
        _video("pinned-2023", 1684564522),
        _video("pinned-2025b", 1752318222),
        _video("new-1", 1780818751),
        _video("new-2", 1780790214),
        _video("new-3", 1780693135),
    ]

    latest = _latest_videos_by_publish_time(videos, limit=3)

    assert [video.id for video in latest] == ["new-1", "new-2", "new-3"]


def _video(video_id: str, published_at_ts: int) -> ScrapedVideo:
    return ScrapedVideo(
        id=video_id,
        title=video_id,
        duration_sec=1,
        likes=0,
        plays=0,
        comments=0,
        shares=0,
        collects=0,
        published_at_ts=published_at_ts,
        cover_url=None,
        source_url=f"https://www.douyin.com/video/{video_id}",
    )
