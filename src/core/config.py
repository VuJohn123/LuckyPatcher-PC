"""Load YAML config với deep merge + fallback defaults."""
from __future__ import annotations

import copy
import os
from typing import Any

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


_DEFAULTS: dict[str, Any] = {
    "pipeline": {
        "apktool_jobs": None,
        "apktool_memory": "4096m",
        "keep_workspace": True,
        "fast_mode": True,
        "use_gda": False,
    },
    "conversion": {
        "auto_convert_xapk": True,
        "auto_convert_apks": True,
        "allow_split_apk": True,
    },
    "signing": {
        "key_type": "testkey",
        "forced_package_id": None,
    },
    "logging": {
        "level": "INFO",
        "file": "logs/pipeline.log",
        "max_bytes": 10 * 1024 * 1024,
        "backup_count": 5,
    },
    "cache": {
        "enabled": True,
        "dir": "workspace/cache",
        "apk_analysis_ttl_days": 30,
        "decompiled_ttl_days": 7,
    },
    "network": {
        "connect_timeout": 10,
        "read_timeout": 60,
        "max_retries": 3,
        "backoff_factor": 1.5,
    },
}


def load_config(path: str | None = None) -> dict[str, Any]:
    """Load config. Nếu file không tồn tại hoặc YAML lỗi → dùng defaults."""
    if path is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base, "config", "default.yaml")

    if not os.path.exists(path):
        return copy.deepcopy(_DEFAULTS)

    if not YAML_AVAILABLE:
        return copy.deepcopy(_DEFAULTS)

    try:
        with open(path, "r", encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
    except Exception:
        return copy.deepcopy(_DEFAULTS)

    return _deep_merge(_DEFAULTS, user)


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge 2 dict, ưu tiên override. Không modify input."""
    result = copy.deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result