from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


CHAT_PRICING_PER_1K: dict[str, tuple[Decimal, Decimal]] = {
    "qwen-plus": (Decimal("0.0008"), Decimal("0.0020")),
    "qwen-plus-latest": (Decimal("0.0008"), Decimal("0.0020")),
    "qwen-turbo": (Decimal("0.0003"), Decimal("0.0006")),
}

ASR_PRICING_PER_SEC: dict[str, Decimal] = {
    "qwen3-asr-flash-filetrans": Decimal("0.00022"),
}


def _round_cost(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def usage_bundle(
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int | None = None,
    cost_cny: float = 0.0,
) -> dict[str, int | float]:
    total = total_tokens if total_tokens is not None else input_tokens + output_tokens
    return {
        "input_tokens": max(0, int(input_tokens)),
        "output_tokens": max(0, int(output_tokens)),
        "total_tokens": max(0, int(total)),
        "cost_cny": max(0.0, float(cost_cny)),
    }


def merge_usage(*items: dict[str, Any] | None) -> dict[str, int | float]:
    total_input = 0
    total_output = 0
    total_tokens = 0
    cost = 0.0
    for item in items:
        if not item:
            continue
        total_input += int(item.get("input_tokens") or 0)
        total_output += int(item.get("output_tokens") or 0)
        total_tokens += int(item.get("total_tokens") or 0)
        cost += float(item.get("cost_cny") or 0.0)
    return usage_bundle(
        input_tokens=total_input,
        output_tokens=total_output,
        total_tokens=total_tokens,
        cost_cny=_round_cost(Decimal(str(cost))),
    )


def llm_usage_from_dashscope(model: str, usage: dict[str, Any] | None) -> dict[str, int | float]:
    usage = dict(usage or {})
    input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or input_tokens + output_tokens)
    price = CHAT_PRICING_PER_1K.get(model)
    if price is None:
        return usage_bundle(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_cny=0.0,
        )
    input_rate, output_rate = price
    cost = (Decimal(input_tokens) / Decimal(1000)) * input_rate + (
        Decimal(output_tokens) / Decimal(1000)
    ) * output_rate
    return usage_bundle(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost_cny=_round_cost(cost),
    )


def asr_usage(model: str, *, duration_sec: int) -> dict[str, int | float]:
    rate = ASR_PRICING_PER_SEC.get(model)
    if rate is None:
        return usage_bundle()
    cost = Decimal(max(0, duration_sec)) * rate
    return usage_bundle(cost_cny=_round_cost(cost))
