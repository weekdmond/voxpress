"""DashScope (OpenAI 兼容模式) 客户端 + token/费用统计。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from pl.config import Settings


# DashScope 公开计价（2026-04 时点 / 单位：¥/1k tokens）。如有变动改这里即可。
# 仅用于估算，不应作为账单依据。
PRICING = {
    "qwen3.6-plus":            {"input": 0.0040, "output": 0.0120},
    "qwen-plus":               {"input": 0.0008, "output": 0.0020},
    "qwen-max":                {"input": 0.0200, "output": 0.0600},
    "qwen-turbo":              {"input": 0.0003, "output": 0.0006},
    "qwen3-asr-flash-filetrans": {"input": 0.0000, "output": 0.0000},
}


@dataclass
class LLMResult:
    content: str
    raw_message: dict[str, Any]
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_yuan: float = 0.0
    latency_ms: int = 0
    finish_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_yuan": round(self.cost_yuan, 6),
            "latency_ms": self.latency_ms,
            "finish_reason": self.finish_reason,
        }


@dataclass
class CallSpec:
    model: str
    system: str
    user: str
    temperature: float = 0.3
    max_tokens: int = 4000
    json_mode: bool = False
    extra_messages: list[dict[str, str]] = field(default_factory=list)


class LLMClient:
    """对 DashScope OpenAI 兼容接口的极简包装。"""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = OpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
        )

    def call(self, spec: CallSpec) -> LLMResult:
        messages: list[dict[str, str]] = []
        if spec.system:
            messages.append({"role": "system", "content": spec.system})
        messages.extend(spec.extra_messages)
        messages.append({"role": "user", "content": spec.user})

        kwargs: dict[str, Any] = dict(
            model=spec.model,
            messages=messages,
            temperature=spec.temperature,
            max_tokens=spec.max_tokens,
        )
        if spec.json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        t0 = time.time()
        resp = self._client.chat.completions.create(**kwargs)
        latency_ms = int((time.time() - t0) * 1000)

        choice = resp.choices[0]
        content = choice.message.content or ""
        usage = resp.usage

        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        total_tokens = getattr(usage, "total_tokens", prompt_tokens + completion_tokens) or 0

        return LLMResult(
            content=content,
            raw_message=choice.message.model_dump(),
            model=spec.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_yuan=_estimate_cost(spec.model, prompt_tokens, completion_tokens),
            latency_ms=latency_ms,
            finish_reason=choice.finish_reason or "",
        )


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    p = PRICING.get(model)
    if not p:
        return 0.0
    return (prompt_tokens / 1000.0) * p["input"] + (completion_tokens / 1000.0) * p["output"]


def parse_json_safe(content: str) -> dict[str, Any] | list[Any] | None:
    """尝试把 LLM content 解析成 JSON。失败返回 None（不抛错），调用方决定怎么处理。"""
    s = content.strip()
    if not s:
        return None
    # 有些模型会用 ```json ... ``` 包起来，剥一下
    if s.startswith("```"):
        first = s.find("\n")
        if first != -1:
            s = s[first + 1 :]
        if s.endswith("```"):
            s = s[: -3]
        s = s.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None
