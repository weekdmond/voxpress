from datetime import datetime, timezone
import importlib
from uuid import uuid4

import pytest

from voxpress.models import Creator, Task, Video
from voxpress.pipeline.protocols import TranscriptResult
from voxpress.pipeline.runner import TaskRunner, VideoContext
from voxpress.pipeline.youtube_ytdlp import YouTubeTranscriptError

runner_module = importlib.import_module("voxpress.pipeline.runner")


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


async def test_youtube_transcribe_falls_back_to_audio_when_subtitles_missing(monkeypatch, tmp_path) -> None:
    runner = TaskRunner()
    source_url = "https://www.youtube.com/watch?v=KJ-efTR7WxM"
    calls: list[str] = []

    async def fake_load_video_context(_task_id):
        ctx = _youtube_context(source_url)
        ctx.video.audio_object_key = "existing-audio"
        return ctx

    async def fake_fetch_transcript(_url: str):
        return None

    async def fake_prepare_audio(_task_id):
        calls.append("prepare_audio")
        return tmp_path / "youtube.m4a"

    async def fake_set_task_detail(_task_id, detail: str):
        calls.append(detail)

    class FakeTranscriber:
        async def transcribe(self, _audio_path, *, language: str = "zh", initial_prompt: str | None = None):
            calls.append(f"transcribe:{language}:{initial_prompt}")
            return TranscriptResult(segments=[(0, "音频兜底")])

    async def fake_transcriber_backend():
        return FakeTranscriber()

    async def fake_current_whisper_language():
        return "zh"

    async def fake_build_initial_prompt(_task_id):
        return None

    async def fake_media_store_disabled():
        return False

    monkeypatch.setattr(runner, "_load_video_context", fake_load_video_context)
    monkeypatch.setattr("voxpress.pipeline.youtube_ytdlp.fetch_transcript", fake_fetch_transcript)
    monkeypatch.setattr(runner, "prepare_audio", fake_prepare_audio)
    monkeypatch.setattr(runner, "_set_task_detail", fake_set_task_detail)
    monkeypatch.setattr(runner, "_transcriber_backend", fake_transcriber_backend)
    monkeypatch.setattr(runner, "current_whisper_language", fake_current_whisper_language)
    monkeypatch.setattr(runner, "build_initial_prompt", fake_build_initial_prompt)
    monkeypatch.setattr(runner_module.media_store, "is_enabled", fake_media_store_disabled)

    transcript = await runner.transcribe_inline(uuid4())

    assert transcript.raw_text == "音频兜底"
    assert transcript.source == "youtube_audio_fallback"
    assert calls == [
        "YouTube 未检测到可用字幕，切换音频下载与 ASR 转写",
        "prepare_audio",
        "transcribe:zh:None",
    ]


async def test_youtube_transcribe_surfaces_subtitle_fetch_error_when_audio_disabled(monkeypatch) -> None:
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
    monkeypatch.setattr(runner_module.app_settings, "youtube_audio_enabled", False)

    with pytest.raises(YouTubeTranscriptError, match="字幕读取失败"):
        await runner.transcribe_inline(uuid4())
