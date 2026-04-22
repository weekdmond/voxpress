from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from voxpress.pipeline.mlx import MlxWhisperTranscriber


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio-path", required=True)
    parser.add_argument("--model", default="large-v3")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--initial-prompt", default="")
    args = parser.parse_args()

    transcriber = MlxWhisperTranscriber(model=args.model)
    result = await transcriber.transcribe(
        Path(args.audio_path),
        language=args.language,
        initial_prompt=args.initial_prompt or None,
    )
    print(
        json.dumps(
            {
                "segments": [[ts, text] for ts, text in result.segments],
                "raw_text": result.raw_text,
            },
            ensure_ascii=False,
        )
    )
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
