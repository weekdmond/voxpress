"""mlx-whisper Transcriber (Apple Silicon only)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from voxpress.pipeline.protocols import Transcriber, TranscriptResult

logger = logging.getLogger(__name__)

# mlx-whisper uses HuggingFace repo IDs. Map our friendly names.
_MODEL_MAP = {
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "small": "mlx-community/whisper-small-mlx",
}


class MlxWhisperTranscriber(Transcriber):
    def __init__(self, model: str = "large-v3") -> None:
        self.model_repo = _MODEL_MAP.get(model, _MODEL_MAP["large-v3"])

    async def transcribe(self, audio_path: Path, language: str = "zh") -> TranscriptResult:
        return await asyncio.to_thread(self._transcribe_sync, audio_path, language)

    def _transcribe_sync(self, audio_path: Path, language: str) -> TranscriptResult:
        import mlx_whisper

        lang_arg = None if language == "auto" else language
        result = mlx_whisper.transcribe(
            str(audio_path),
            path_or_hf_repo=self.model_repo,
            language=lang_arg,
            word_timestamps=False,
        )
        segments = [
            (int(round(seg["start"])), str(seg["text"]).strip())
            for seg in result.get("segments", [])
            if str(seg.get("text", "")).strip()
        ]
        if not segments:
            # Fall back to whole text if the model didn't emit segments
            whole = str(result.get("text", "")).strip()
            if whole:
                segments = [(0, whole)]
        return TranscriptResult(segments=segments)
