from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class DeployInfo:
    commit: str | None = None
    branch: str | None = None
    version: str | None = None
    deployed_at: datetime | None = None


def _deploy_info_path() -> Path:
    return Path(__file__).resolve().parents[1] / ".deploy-info.json"


def load_deploy_info() -> DeployInfo:
    path = _deploy_info_path()
    if not path.exists() or not path.is_file():
        return DeployInfo()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DeployInfo()
    if not isinstance(payload, dict):
        return DeployInfo()
    deployed_at_raw = payload.get("deployed_at")
    deployed_at: datetime | None = None
    if isinstance(deployed_at_raw, str) and deployed_at_raw:
        try:
            deployed_at = datetime.fromisoformat(deployed_at_raw)
        except ValueError:
            deployed_at = None
    return DeployInfo(
        commit=str(payload.get("commit") or "") or None,
        branch=str(payload.get("branch") or "") or None,
        version=str(payload.get("version") or "") or None,
        deployed_at=deployed_at,
    )
