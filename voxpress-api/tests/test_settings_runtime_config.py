from __future__ import annotations

from voxpress.routers.settings import (
    _normalize_settings_dict,
    _prepare_settings_value_for_storage,
)
from voxpress.pipeline.runner import _normalize_runtime_settings
from voxpress.prompts import DEFAULT_BACKGROUND_NOTES_TEMPLATE, DEFAULT_ORGANIZER_TEMPLATE, DEFAULT_PROMPT_VERSION
from voxpress.runtime_settings import (
    build_prompt_runtime_settings,
    build_topic_taxonomy_runtime_settings,
)
from voxpress.schemas import SettingsOut, SettingsPatch


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

    assert dumped["prompt"]["version"] == DEFAULT_PROMPT_VERSION
    assert dumped["prompt"]["template"] == DEFAULT_ORGANIZER_TEMPLATE.strip()
    assert dumped["prompt"]["background_notes_template"] == DEFAULT_BACKGROUND_NOTES_TEMPLATE.strip()
    assert dumped["topic_taxonomy"]["version"] == "v1"
    assert dumped["topic_taxonomy"]["taxonomy"]
    assert dumped["topic_taxonomy"]["synonyms"]


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


def test_prepare_prompt_settings_value_for_storage_normalizes_empty_templates() -> None:
    assert _prepare_settings_value_for_storage("prompt", {"template": "", "version": ""}) == {
        "version": DEFAULT_PROMPT_VERSION,
        "template": DEFAULT_ORGANIZER_TEMPLATE.strip(),
        "background_notes_template": DEFAULT_BACKGROUND_NOTES_TEMPLATE.strip(),
    }


def test_build_prompt_runtime_settings_preserves_custom_templates() -> None:
    runtime = build_prompt_runtime_settings(
        {
            "version": "custom-v1",
            "template": "custom organizer prompt",
            "background_notes_template": "custom background prompt",
        }
    )

    assert runtime.version == "custom-v1"
    assert runtime.organizer_template == "custom organizer prompt"
    assert runtime.background_notes_template == "custom background prompt"


def test_build_topic_taxonomy_runtime_settings_normalizes_paths_and_synonyms() -> None:
    runtime = build_topic_taxonomy_runtime_settings(
        {
            "version": "custom-taxonomy",
            "taxonomy": [{"topic": "金融投资", "subtopics": ["股票市场"]}],
            "synonyms": {"技术分析": "金融投资/股票市场", "无效": "不存在/路径"},
        }
    )

    assert runtime.version == "custom-taxonomy"
    assert runtime.paths == ["金融投资/股票市场"]
    assert runtime.synonyms == {"技术分析": "金融投资/股票市场"}


def test_prompt_settings_patch_keeps_partial_payload_partial() -> None:
    patch = SettingsPatch.model_validate(
        {"prompt": {"background_notes_template": "custom background prompt"}}
    )

    assert patch.model_dump(exclude_none=True, mode="json") == {
        "prompt": {"background_notes_template": "custom background prompt"}
    }
