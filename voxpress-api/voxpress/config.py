from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VOXPRESS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    db_url: str = "postgresql+asyncpg://auston@localhost/voxpress"
    host: str = "127.0.0.1"
    port: int = 8787
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    llm_base_url: str = "http://localhost:11434"
    audio_dir: Path = Path("/tmp/voxpress/audio")
    max_pipeline_concurrency: int = Field(default=2, ge=1, le=20)
    # "stub" = hardcoded placeholder pipeline (default, safe)
    # "real" = yt-dlp + mlx-whisper + Ollama (requires models pulled + cookie)
    pipeline: Literal["stub", "real"] = "stub"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
