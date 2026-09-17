"""
Load YAML config với:
  - Deep merge defaults
  - Env var overrides (LP_* prefix)
  - Preset application
  - Adaptive auto-tune (4 tầng: static/workload/runtime/history)

Precedence (cao → thấp):
  1. CLI args
  2. Env vars (LP_<SECTION>_<KEY>)
  3. Preset (LP_PRESET env)
  4. User config file
  5. default.yaml
  6. Runtime auto-tune (cho field "auto")
"""
from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
from typing import Any

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

logger = logging.getLogger(__name__)


# ============================================================
# DEFAULTS — fallback khi YAML không đọc được
# (khớp với config/default.yaml để tránh drift)
# ============================================================
_DEFAULTS: dict[str, Any] = {
    # ---------- AUTO-TUNE ENGINE ----------
    "auto_tune": {
        "enabled": True,
        "mode": "auto",
        "safety": {
            "reserve_cpu_cores": 1,
            "reserve_ram_pct": 25,
            "reserve_ram_min_mb": 1024,
            "reserve_disk_pct": 10,
            "reserve_disk_min_mb": 2048,
            "throttle_ram_pct": 80,
            "throttle_cpu_pct": 90,
            "throttle_disk_pct": 90,
            "throttle_temp_celsius": 85,
            "backoff_factor": 0.5,
            "backoff_min_workers": 1,
        },
        "workload_classes": {
            "tiny":    {"max_size_mb": 10,    "strategy": "fast"},
            "small":   {"max_size_mb": 50,    "strategy": "fast"},
            "medium":  {"max_size_mb": 200,   "strategy": "balanced"},
            "large":   {"max_size_mb": 500,   "strategy": "careful"},
            "huge":    {"max_size_mb": 2048,  "strategy": "careful"},
            "massive": {"max_size_mb": 99999, "strategy": "paranoid"},
        },
        "telemetry": {
            "enabled": True,
            "history_size": 100,
            "reuse_learned_config": True,
            "min_samples_for_trust": 3,
        },
        "concurrency": {
            "allow_multi_instance": False,
            "share_resources": True,
            "lock_file": "auto",
        },
    },

    # ---------- PIPELINE ----------
    "pipeline": {
        "apktool_jobs": "auto",
        "apktool_memory": "auto",
        "keep_workspace": True,
        "fast_mode": "auto",
        "use_gda": "auto",
        "gc_control": True,
        "max_decompile_retries": "auto",
        "max_recompile_retries": 1,
    },

    # ---------- CONVERSION ----------
    "conversion": {
        "auto_convert_xapk": True,
        "auto_convert_apks": True,
        "allow_split_apk": True,
        "cleanup_temp": True,
    },

    # ---------- SIGNING ----------
    "signing": {
        "key_type": "testkey",
        "forced_package_id": None,
        "skip_adb_if_missing": True,
    },

    # ---------- LOGGING ----------
    "logging": {
        "level": "auto",
        "file": "auto",
        "max_bytes": 10 * 1024 * 1024,
        "backup_count": 5,
        "json_format": False,
        "rotation": "size",
        "suppress_noisy_libs": True,
    },

    # ---------- CACHE ----------
    "cache": {
        "enabled": "auto",
        "dir": "auto",
        "apk_analysis_ttl_days": 30,
        "decompiled_ttl_days": "auto",
        "max_size_mb": "auto",
        "compress_decompiled": "auto",
    },

    # ---------- NETWORK ----------
    "network": {
        "connect_timeout": "auto",
        "read_timeout": 60,
        "max_retries": 3,
        "backoff_factor": 1.5,
        "retry_status_codes": [429, 500, 502, 503, 504],
        "max_download_size_mb": 500,
        "pool_connections": "auto",
        "pool_maxsize": "auto",
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "block_private_ips": True,
        "block_localhost": True,
        "block_metadata_endpoints": True,
        "allowed_schemes": ["http", "https"],
    },

    # ---------- PERFORMANCE ----------
    "performance": {
        "worker_processes": "auto",
        "regex_engine": "auto",
        "json_engine": "auto",
        "file_cache_buffer_kb": "auto",
        "mmap_threshold_bytes": 1048576,
        "prefilter_enabled": True,
        "batch": {
            "flush_batch_size": "auto",
            "flush_on_memory_mb": "auto",
            "parallel_chunk_size": "auto",
        },
    },

    # ---------- SECURITY ----------
    "security": {
        "zip_slip_guard": True,
        "validate_input_paths": True,
        "max_path_length": "auto",
        "sanitize_download_filenames": True,
        "forbid_eval_in_patches": True,
    },

    # ---------- UI ----------
    "ui": {
        "theme": "dark",
        "font_family": None,
        "font_size": 13,
        "window_width": 1280,
        "window_height": 820,
        "log_visible": "auto",
        "log_max_height": "auto",
        "log_expanded_height": 400,
        "log_auto_scroll": "auto",
        "log_max_blocks": "auto",
        "animations_enabled": "auto",
    },

    # ---------- UPDATER ----------
    "updater": {
        "check_on_startup": "auto",
        "update_url": (
            "https://raw.githubusercontent.com/Freezdy413485/"
            "LP-PC-Suite/main/version.json"
        ),
        "timeout": 8.0,
        "cache_check_hours": 24,
    },
}


# ============================================================
# PUBLIC API
# ============================================================
def load_config(
    path: str | None = None,
    apk_path: str | None = None,
    mode: str = "auto",
) -> dict[str, Any]:
    """
    Load config với 4 tầng auto-tune.

    Args:
        path: đường dẫn YAML. None = <project_root>/config/default.yaml
        apk_path: APK cần xử lý (để workload profiling). Optional.
        mode: pipeline mode string (để chọn tune mode). Optional.

    Returns:
        dict config đã merge + preset + env overrides + auto-tune.
    """
    # --- 1. Resolve YAML path ---
    if path is None:
        path = str(_project_root() / "config" / "default.yaml")

    # --- 2. Load user YAML ---
    user_config: dict[str, Any] = {}
    if os.path.exists(path):
        if not YAML_AVAILABLE:
            logger.warning("PyYAML không cài — dùng defaults")
        else:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    user_config = yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning("Load YAML fail (%s): %s", path, e)

    # --- 3. Deep merge defaults <- user ---
    config = _deep_merge(_DEFAULTS, user_config)

    # --- 4. Preset (LP_PRESET env) ---
    preset_name = os.environ.get("LP_PRESET", "").strip().lower()
    presets = user_config.get("presets", {})
    if preset_name and preset_name in presets:
        config = _deep_merge(config, presets[preset_name])
        logger.info("Preset applied: %s", preset_name)
    elif preset_name:
        logger.warning("Preset '%s' không tồn tại", preset_name)

    # --- 5. Env var overrides ---
    config = _apply_env_overrides(config)

    # --- 6. Adaptive auto-tune ---
    if config.get("auto_tune", {}).get("enabled", True):
        config = _apply_adaptive_tune(config, apk_path, mode)

    return config


# ============================================================
# ADAPTIVE TUNING
# ============================================================
def _apply_adaptive_tune(
    config: dict,
    apk_path: str | None,
    mode: str,
) -> dict:
    """
    Áp dụng adaptive tuner + workload profiler.
    Không crash nếu module thiếu — chỉ log warning.
    """
    try:
        from core.adaptive_tuner import get_tuner

        # ---- Workload profiling ----
        workload = None
        if apk_path and os.path.isfile(apk_path):
            try:
                from core.workload_profiler import profile_apk
                workload = profile_apk(apk_path)
                logger.info(
                    "Workload: size=%s type=%s strategy=%s "
                    "(%.1fMB, %d dex, native=%s)",
                    workload.size_class.value,
                    workload.workload_type.value,
                    workload.strategy.value,
                    workload.size_mb,
                    workload.dex_count,
                    workload.has_native_libs,
                )
            except Exception as e:
                logger.debug("Workload profile failed: %s", e)

        # ---- Resolve tune mode ----
        tune_mode = mode
        if mode == "auto" or mode == "all":
            tune_mode = config.get("auto_tune", {}).get("mode", "auto")

        # ---- Run tuner ----
        tuner = get_tuner()
        result = tuner.tune(config, workload=workload, mode=tune_mode)

        logger.info(
            "Adaptive tune result: mode=%s jobs=%d mem=%s workers=%d "
            "fast=%s gda=%s cache=%s",
            result.mode.value,
            result.apktool_jobs,
            result.apktool_memory,
            result.worker_processes,
            result.fast_mode,
            result.use_gda,
            result.cache_enabled,
        )

        # Attach tune result để caller có thể inspect
        config["_tune_result"] = {
            "mode": result.mode.value,
            "reasoning": result.reasoning,
        }
    except Exception as e:
        logger.warning("Adaptive tune failed: %s", e)

    return config


# ============================================================
# DEEP MERGE
# ============================================================
def _deep_merge(base: dict, override: dict) -> dict:
    """
    Merge 2 dict, ưu tiên override.
    Không modify input.
    """
    result = copy.deepcopy(base)
    for k, v in override.items():
        if (
            k in result
            and isinstance(result[k], dict)
            and isinstance(v, dict)
        ):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


# ============================================================
# ENV OVERRIDES
# ============================================================
def _apply_env_overrides(config: dict) -> dict:
    """
    Apply env vars LP_<SECTION>_<KEY>.

    Ví dụ:
      LP_PIPELINE_APKTOOL_JOBS=8
      LP_LOGGING_LEVEL=DEBUG
      LP_NETWORK_CONNECT_TIMEOUT=30
      LP_AUTO_TUNE_MODE=stress
    """
    result = copy.deepcopy(config)

    # Reserved keys không phải config
    reserved = {"LP_PRESET", "LP_CUSTOM_PATCH", "LP_CONFIG_PATH"}

    for key, value in os.environ.items():
        if not key.startswith("LP_") or key in reserved:
            continue

        # LP_PIPELINE_APKTOOL_JOBS → ["pipeline", "apktool_jobs"]
        stripped = key[3:].lower()  # Bỏ "LP_"
        parts = stripped.split("_", 1)
        if len(parts) < 2:
            continue

        section, rest = parts
        if section not in result:
            continue

        try:
            _set_nested(result[section], rest, value)
        except Exception as e:
            logger.warning(
                "Env override fail (%s=%s): %s", key, value, e
            )

    return result


def _set_nested(d: dict, key_path: str, raw_value: str) -> None:
    """
    Set nested value với type coercion.
    Chỉ set nếu key đã tồn tại (tránh typo).
    """
    # Thử khớp trực tiếp (snake_case / kebab-case)
    candidates = [key_path, key_path.replace("-", "_")]

    for candidate in candidates:
        if candidate in d:
            d[candidate] = _coerce_value(raw_value, d[candidate])
            return

    # Thử split để vào nested dict: apktool_jobs → apktool.jobs
    parts = key_path.split("_")
    for i in range(len(parts) - 1, 0, -1):
        prefix = "_".join(parts[:i])
        suffix = "_".join(parts[i:])
        if prefix in d and isinstance(d[prefix], dict):
            _set_nested(d[prefix], suffix, raw_value)
            return

    # Không khớp → bỏ qua (không tạo key mới)


def _coerce_value(raw: str, template: Any) -> Any:
    """Coerce string env var về type của template."""
    if isinstance(template, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(template, int):
        try:
            return int(raw)
        except ValueError:
            return template
    if isinstance(template, float):
        try:
            return float(raw)
        except ValueError:
            return template
    if isinstance(template, list):
        return [s.strip() for s in raw.split(",") if s.strip()]
    return raw


# ============================================================
# HELPERS
# ============================================================
def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent