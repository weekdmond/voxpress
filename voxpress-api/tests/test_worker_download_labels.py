from voxpress.worker import _download_stage_labels


def test_download_stage_labels_use_youtube_provider() -> None:
    assert _download_stage_labels("youtube") == (
        "youtube",
        "yt-dlp audio",
        "yt-dlp 下载 YouTube 音频",
    )


def test_download_stage_labels_default_to_douyin_provider() -> None:
    assert _download_stage_labels("douyin") == (
        "douyin",
        "douyin-web",
        "Douyin Web API 读取视频并抽取音频",
    )
