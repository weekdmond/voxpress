from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VOXPRESS_",
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    db_url: str = "postgresql+asyncpg://auston@localhost/voxpress"
    host: str = "127.0.0.1"
    port: int = 8787
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    dashscope_api_key: str | None = None
    dashscope_compatible_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_default_llm_model: str = "qwen3.6-plus"
    dashscope_default_corrector_model: str = "qwen-turbo"
    dashscope_default_asr_model: str = "qwen3-asr-flash-filetrans"
    dashscope_chat_pricing: str = (
        '{"qwen3.6-plus":[0.0020,0.0120],"qwen3.6-plus-2026-04-02":[0.0020,0.0120],'
        '"qwen-plus":[0.0008,0.0020],"qwen-plus-latest":[0.0008,0.0020],'
        '"qwen-turbo":[0.0003,0.0006],"qwen-max":[0.0024,0.0096],"qwen-max-latest":[0.0024,0.0096]}'
    )
    dashscope_asr_pricing: str = '{"qwen3-asr-flash-filetrans":0.00022}'
    dashscope_asr_poll_interval_sec: int = Field(default=2, ge=1, le=30)
    dashscope_asr_timeout_sec: int = Field(default=1800, ge=30, le=86_400)
    audio_dir: Path = Path("/tmp/voxpress/audio")
    video_dir: Path = Path("/tmp/voxpress/video")
    max_pipeline_concurrency: int = Field(default=2, ge=1, le=20)
    download_concurrency: int = Field(default=4, ge=1, le=20)
    transcribe_concurrency: int = Field(default=4, ge=1, le=20)
    correct_concurrency: int = Field(default=8, ge=1, le=20)
    organize_concurrency: int = Field(default=8, ge=1, le=20)
    save_concurrency: int = Field(default=4, ge=1, le=20)
    task_lease_seconds: int = Field(default=120, ge=30, le=3600)
    task_heartbeat_seconds: int = Field(default=15, ge=5, le=300)
    worker_poll_interval_ms: int = Field(default=1200, ge=100, le=10_000)
    creator_refresh_enabled: bool = True
    creator_refresh_interval_hours: int = Field(default=4, ge=1, le=168)
    creator_refresh_recent_count: int = Field(default=5, ge=1, le=20)
    oss_region: str | None = None
    oss_endpoint: str | None = None
    oss_bucket: str | None = None
    oss_access_key_id: str | None = None
    oss_access_key_secret: str | None = None
    oss_sign_expires_sec: int = Field(default=3600, ge=60, le=86_400)
    # "stub" = hardcoded placeholder pipeline (default, safe)
    # "real" = f2 Douyin API + direct media download + DashScope ASR + DashScope Qwen
    pipeline: Literal["stub", "real"] = "stub"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def dashscope_enabled(self) -> bool:
        return bool((self.dashscope_api_key or "").strip() and self.dashscope_compatible_base_url.strip())

    @property
    def dashscope_chat_base_url(self) -> str:
        return self.dashscope_compatible_base_url.rstrip("/")

    @property
    def dashscope_api_base_url(self) -> str:
        base = self.dashscope_chat_base_url
        if base.endswith("/compatible-mode/v1"):
            return f"{base[:-len('/compatible-mode/v1')]}/api/v1"
        if "/compatible-mode/" in base:
            return base.replace("/compatible-mode/", "/api/", 1)
        return f"{base}/api/v1"

    @staticmethod
    def _parse_json_mapping(raw: str) -> dict:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @property
    def dashscope_chat_pricing_map(self) -> dict[str, tuple[float, float]]:
        parsed = self._parse_json_mapping(self.dashscope_chat_pricing)
        out: dict[str, tuple[float, float]] = {}
        for model, value in parsed.items():
            if (
                isinstance(model, str)
                and isinstance(value, (list, tuple))
                and len(value) == 2
            ):
                try:
                    out[model] = (float(value[0]), float(value[1]))
                except (TypeError, ValueError):
                    continue
        return out

    @property
    def dashscope_asr_pricing_map(self) -> dict[str, float]:
        parsed = self._parse_json_mapping(self.dashscope_asr_pricing)
        out: dict[str, float] = {}
        for model, value in parsed.items():
            if not isinstance(model, str):
                continue
            try:
                out[model] = float(value)
            except (TypeError, ValueError):
                continue
        return out


settings = Settings()
