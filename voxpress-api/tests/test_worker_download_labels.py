from voxpress.pipeline.protocols import TranscriptResult
from voxpress.worker import _download_stage_labels, _transcribe_done_detail


def test_download_stage_labels_use_youtube_provider() -> None:
    assert _download_stage_labels("youtube") == (
        "youtube",
        "yt-dlp metadata",
        "yt-dlp 读取 YouTube 元信息",
    )


def test_download_stage_labels_default_to_douyin_provider() -> None:
    assert _download_stage_labels("douyin") == (
        "douyin",
        "douyin-web",
        "Douyin Web API 读取视频并抽取音频",
    )


def test_transcribe_done_detail_names_youtube_sources() -> None:
    assert _transcribe_done_detail(TranscriptResult(segments=[(0, "a")], source="youtube_subtitle")) == (
        "YouTube 字幕转写完成 · 1 段"
    )
    assert _transcribe_done_detail(TranscriptResult(segments=[(0, "a")], source="youtube_audio_fallback")) == (
        "YouTube 无字幕，音频转写完成 · 1 段"
    )
