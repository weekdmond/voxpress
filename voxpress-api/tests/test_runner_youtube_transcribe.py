from datetime import datetime, timezone
from uuid import uuid4

import pytest

from voxpress.models import Creator, Task, Video
from voxpress.pipeline.protocols import TranscriptResult
from voxpress.pipeline.runner import TaskRunner, VideoContext
from voxpress.pipeline.youtube_ytdlp import YouTubeTranscriptError


def _youtube_context(source_url: str) -> VideoContext:
    creator = Creator(
        id=1,
        platform="youtube",
        external_id="UC9cfcOuTT9rYkyUimMjLxuw",
        handle="@Money_or_Life",
        name="Money or Life 美股频道",
        followers=76800,
    )
    video = Video(
        id="youtube:KJ-efTR7WxM",
        creator_id=1,
        title="Test video",
        duration_sec=123,
        published_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        source_url=source_url,
    )
    task = Task(id=uuid4(), source_url=source_url, creator_id=1, video_id=video.id)
    return VideoContext(task=task, video=video, creator=creator)


async def test_youtube_transcribe_prefers_subtitles_without_preparing_audio(monkeypatch) -> None:
    runner = TaskRunner()
    source_url = "https://www.youtube.com/watch?v=KJ-efTR7WxM"
    transcript = TranscriptResult(segments=[(0, "字幕优先")])

    async def fake_load_video_context(_task_id):
        return _youtube_context(source_url)

    async def fake_fetch_transcript(url: str):
        assert url == source_url
        return transcript

    async def fail_prepare_audio(_task_id):
        raise AssertionError("prepare_audio should not run when YouTube subtitles are available")

    monkeypatch.setattr(runner, "_load_video_context", fake_load_video_context)
    monkeypatch.setattr("voxpress.pipeline.youtube_ytdlp.fetch_transcript", fake_fetch_transcript)
    monkeypatch.setattr(runner, "prepare_audio", fail_prepare_audio)

    assert await runner.transcribe_inline(uuid4()) is transcript


async def test_youtube_transcribe_does_not_download_audio_when_subtitles_missing(monkeypatch) -> None:
    runner = TaskRunner()
    source_url = "https://www.youtube.com/watch?v=KJ-efTR7WxM"

    async def fake_load_video_context(_task_id):
        return _youtube_context(source_url)

    async def fake_fetch_transcript(_url: str):
        return None

    async def fail_prepare_audio(_task_id):
        raise AssertionError("prepare_audio should not run when YouTube subtitles are missing by default")

    monkeypatch.setattr(runner, "_load_video_context", fake_load_video_context)
    monkeypatch.setattr("voxpress.pipeline.youtube_ytdlp.fetch_transcript", fake_fetch_transcript)
    monkeypatch.setattr(runner, "prepare_audio", fail_prepare_audio)

    with pytest.raises(RuntimeError, match="没有可用字幕"):
        await runner.transcribe_inline(uuid4())


async def test_youtube_transcribe_surfaces_subtitle_fetch_error(monkeypatch) -> None:
    runner = TaskRunner()
    source_url = "https://www.youtube.com/watch?v=KJ-efTR7WxM"

    async def fake_load_video_context(_task_id):
        return _youtube_context(source_url)

    async def fake_fetch_transcript(_url: str):
        raise YouTubeTranscriptError("YouTube 字幕读取失败: Requested format is not available")

    async def fail_prepare_audio(_task_id):
        raise AssertionError("prepare_audio should not run when subtitle fetch fails by default")

    monkeypatch.setattr(runner, "_load_video_context", fake_load_video_context)
    monkeypatch.setattr("voxpress.pipeline.youtube_ytdlp.fetch_transcript", fake_fetch_transcript)
    monkeypatch.setattr(runner, "prepare_audio", fail_prepare_audio)

    with pytest.raises(YouTubeTranscriptError, match="字幕读取失败"):
        await runner.transcribe_inline(uuid4())
