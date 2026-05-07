from datetime import datetime, timezone
import importlib

import pytest

from voxpress.media_store import MediaStoreError, audio_object_key, video_object_key
from voxpress.pipeline.protocols import ExtractorResult
from voxpress.pipeline.runner import TaskRunner

runner_module = importlib.import_module("voxpress.pipeline.runner")


class FakeMediaStore:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.uploads: list[tuple[str, str]] = []

    async def is_enabled(self) -> bool:
        return self.enabled

    async def upload_file(self, path, *, object_key: str) -> str:
        self.uploads.append((str(path), object_key))
        return object_key


def _extractor_result(tmp_path) -> ExtractorResult:
    video_path = tmp_path / "video.mp4"
    audio_path = tmp_path / "audio.m4a"
    video_path.write_bytes(b"video")
    audio_path.write_bytes(b"audio")
    return ExtractorResult(
        video_id="youtube:abc123",
        creator_external_id="channel",
        creator_handle="@channel",
        creator_name="Channel",
        creator_region=None,
        creator_verified=False,
        creator_followers=0,
        creator_total_likes=0,
        title="Title",
        duration_sec=1,
        likes=0,
        plays=0,
        comments=0,
        shares=0,
        collects=0,
        published_at_iso=datetime.now(tz=timezone.utc).isoformat(),
        cover_url=None,
        source_url="https://www.youtube.com/watch?v=abc123",
        audio_path=audio_path,
        video_path=video_path,
        platform="youtube",
    )


def test_media_object_keys_are_platform_scoped(tmp_path) -> None:
    assert video_object_key("youtube:abc123", tmp_path / "v.mp4", platform="youtube") == (
        "youtube/videos/youtube:abc123.mp4"
    )
    assert audio_object_key("youtube:abc123", tmp_path / "a.m4a", platform="youtube") == (
        "youtube/audio/youtube:abc123.m4a"
    )


async def test_archive_media_uploads_to_oss_and_removes_local_files(monkeypatch, tmp_path) -> None:
    fake_store = FakeMediaStore(enabled=True)
    monkeypatch.setattr(runner_module, "media_store", fake_store)
    meta = _extractor_result(tmp_path)

    await TaskRunner()._archive_media(meta)

    assert meta.media_object_key == "youtube/videos/youtube:abc123.mp4"
    assert meta.audio_object_key == "youtube/audio/youtube:abc123.m4a"
    assert not meta.video_path.exists()
    assert not meta.audio_path.exists()
    assert [object_key for _path, object_key in fake_store.uploads] == [
        "youtube/videos/youtube:abc123.mp4",
        "youtube/audio/youtube:abc123.m4a",
    ]


async def test_archive_media_requires_oss_for_downloaded_files(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(runner_module, "media_store", FakeMediaStore(enabled=False))
    meta = _extractor_result(tmp_path)

    with pytest.raises(MediaStoreError, match="OSS 未配置"):
        await TaskRunner()._archive_media(meta)

    assert meta.video_path.exists()
    assert meta.audio_path.exists()
