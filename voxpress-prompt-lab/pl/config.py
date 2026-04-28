"""配置加载：从 .env 读 DashScope key 与默认 LLM 参数。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
CASES_DIR = PROJECT_ROOT / "cases"
RUNS_DIR = PROJECT_ROOT / "runs"


@dataclass(frozen=True)
class Settings:
    dashscope_api_key: str
    dashscope_base_url: str
    default_model: str
    default_temperature: float
    default_max_tokens: int
    concurrency: int


def load_settings(env_file: Path | None = None) -> Settings:
    """加载 .env 并返回 Settings。env_file 不传时自动找项目根目录的 .env。"""
    if env_file is None:
        env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)

    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key or api_key.startswith("sk-your"):
        raise RuntimeError(
            "DASHSCOPE_API_KEY 未配置。复制 .env.example 为 .env 并填入真实 key。"
        )

    return Settings(
        dashscope_api_key=api_key,
        dashscope_base_url=os.getenv(
            "DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ).rstrip("/"),
        default_model=os.getenv("PL_DEFAULT_MODEL", "qwen3.6-plus"),
        default_temperature=float(os.getenv("PL_DEFAULT_TEMPERATURE", "0.3")),
        default_max_tokens=int(os.getenv("PL_DEFAULT_MAX_TOKENS", "4000")),
        concurrency=int(os.getenv("PL_CONCURRENCY", "2")),
    )
