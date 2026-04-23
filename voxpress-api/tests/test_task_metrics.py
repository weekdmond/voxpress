from voxpress.task_metrics import asr_usage, llm_usage_from_dashscope, merge_usage


def test_llm_usage_from_dashscope_known_model() -> None:
    usage = llm_usage_from_dashscope(
        "qwen3.6-plus",
        {"prompt_tokens": 3500, "completion_tokens": 1500, "total_tokens": 5000},
    )
    assert usage["input_tokens"] == 3500
    assert usage["output_tokens"] == 1500
    assert usage["total_tokens"] == 5000
    assert usage["cost_cny"] == 0.0250


def test_llm_usage_from_dashscope_versioned_model() -> None:
    usage = llm_usage_from_dashscope(
        "qwen3.6-plus-2026-04-02",
        {"prompt_tokens": 3500, "completion_tokens": 1500, "total_tokens": 5000},
    )
    assert usage["input_tokens"] == 3500
    assert usage["output_tokens"] == 1500
    assert usage["total_tokens"] == 5000
    assert usage["cost_cny"] == 0.0250


def test_llm_usage_from_dashscope_unknown_model_zero_cost() -> None:
    usage = llm_usage_from_dashscope("unknown-model", {"prompt_tokens": 120, "completion_tokens": 30})
    assert usage["input_tokens"] == 120
    assert usage["output_tokens"] == 30
    assert usage["total_tokens"] == 150
    assert usage["cost_cny"] == 0.0


def test_asr_usage_uses_duration_seconds() -> None:
    usage = asr_usage("qwen3-asr-flash-filetrans", duration_sec=300)
    assert usage["input_tokens"] == 0
    assert usage["output_tokens"] == 0
    assert usage["total_tokens"] == 0
    assert usage["cost_cny"] == 0.066


def test_merge_usage_sums_values() -> None:
    merged = merge_usage(
        {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120, "cost_cny": 0.1},
        {"input_tokens": 50, "output_tokens": 10, "total_tokens": 60, "cost_cny": 0.02},
    )
    assert merged == {
        "input_tokens": 150,
        "output_tokens": 30,
        "total_tokens": 180,
        "cost_cny": 0.12,
    }
