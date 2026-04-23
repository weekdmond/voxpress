from __future__ import annotations

from voxpress.runtime_settings import (
    build_dashscope_runtime_settings,
    build_oss_runtime_settings,
)


def test_build_dashscope_runtime_settings_prefers_database_values(monkeypatch) -> None:
    monkeypatch.setattr("voxpress.runtime_settings.app_settings.dashscope_api_key", "env-key")
    monkeypatch.setattr(
        "voxpress.runtime_settings.app_settings.dashscope_compatible_base_url",
        "https://env.example/compatible-mode/v1",
    )

    runtime = build_dashscope_runtime_settings(
        {
            "api_key": "db-key",
            "base_url": "https://db.example/compatible-mode/v1/",
        }
    )

    assert runtime.api_key == "db-key"
    assert runtime.chat_base_url == "https://db.example/compatible-mode/v1"
    assert runtime.api_base_url == "https://db.example/api/v1"
    assert runtime.enabled is True


def test_build_oss_runtime_settings_falls_back_to_env_and_normalizes_endpoint(
    monkeypatch,
) -> None:
    monkeypatch.setattr("voxpress.runtime_settings.app_settings.oss_region", "cn-hangzhou")
    monkeypatch.setattr("voxpress.runtime_settings.app_settings.oss_endpoint", None)
    monkeypatch.setattr("voxpress.runtime_settings.app_settings.oss_bucket", "env-bucket")
    monkeypatch.setattr("voxpress.runtime_settings.app_settings.oss_access_key_id", "env-id")
    monkeypatch.setattr("voxpress.runtime_settings.app_settings.oss_access_key_secret", "env-secret")
    monkeypatch.setattr("voxpress.runtime_settings.app_settings.oss_sign_expires_sec", 7200)

    runtime = build_oss_runtime_settings({"bucket": "db-bucket"})

    assert runtime.region == "cn-hangzhou"
    assert runtime.endpoint == "https://oss-cn-hangzhou.aliyuncs.com"
    assert runtime.bucket == "db-bucket"
    assert runtime.access_key_id == "env-id"
    assert runtime.access_key_secret == "env-secret"
    assert runtime.sign_expires_sec == 7200
    assert runtime.enabled is True
