from __future__ import annotations

from voxpress.routers.settings import (
    _normalize_settings_dict,
    _prepare_settings_value_for_storage,
)
from voxpress.pipeline.runner import _normalize_runtime_settings
from voxpress.schemas import SettingsOut


def test_normalize_settings_dict_exposes_configured_flags_without_leaking_secrets() -> None:
    normalized = _normalize_settings_dict(
        {
            "llm": {},
            "whisper": {},
            "corrector": {},
            "article": {},
            "prompt": {},
            "cookie": {"status": "ok", "text": "cookie-secret"},
            "dashscope": {
                "api_key": "sk-db",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            },
            "oss": {
                "region": "cn-hangzhou",
                "bucket": "voxpress-media",
                "access_key_id": "oss-id",
                "access_key_secret": "oss-secret",
            },
            "storage": {},
        }
    )

    out = SettingsOut.model_validate(normalized)
    dumped = out.model_dump(mode="json")

    assert dumped["dashscope"]["configured"] is True
    assert dumped["dashscope"]["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert "api_key" not in dumped["dashscope"]

    assert dumped["oss"]["configured"] is True
    assert dumped["oss"]["bucket"] == "voxpress-media"
    assert dumped["oss"]["endpoint"] == "https://oss-cn-hangzhou.aliyuncs.com"
    assert "access_key_secret" not in dumped["oss"]

    assert dumped["cookie"]["status"] == "ok"
    assert "text" not in dumped["cookie"]


def test_prepare_settings_value_for_storage_strips_derived_secret_status_fields() -> None:
    assert _prepare_settings_value_for_storage(
        "dashscope",
        {
            "configured": True,
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "sk-db",
        },
    ) == {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": "sk-db",
    }

    assert _prepare_settings_value_for_storage(
        "oss",
        {
            "configured": True,
            "region": "cn-hangzhou",
            "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
            "bucket": "voxpress-media",
            "access_key_id": "oss-id",
            "access_key_secret": "oss-secret",
        },
    ) == {
        "region": "cn-hangzhou",
        "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
        "bucket": "voxpress-media",
        "access_key_id": "oss-id",
        "access_key_secret": "oss-secret",
    }


def test_normalize_settings_dict_preserves_custom_model_names() -> None:
    normalized = _normalize_settings_dict(
        {
            "llm": {"model": "custom-llm-model"},
            "whisper": {"model": "custom-asr-model", "language": "auto"},
            "corrector": {"model": "custom-corrector-model"},
        }
    )

    assert normalized["llm"]["model"] == "custom-llm-model"
    assert normalized["whisper"]["model"] == "custom-asr-model"
    assert normalized["corrector"]["model"] == "custom-corrector-model"


def test_runner_normalize_runtime_settings_preserves_custom_model_names() -> None:
    assert _normalize_runtime_settings("llm", {"model": "custom-llm-model"})["model"] == "custom-llm-model"
    assert _normalize_runtime_settings("whisper", {"model": "custom-asr-model"})["model"] == "custom-asr-model"
    assert _normalize_runtime_settings("corrector", {"model": "custom-corrector-model"})["model"] == "custom-corrector-model"
