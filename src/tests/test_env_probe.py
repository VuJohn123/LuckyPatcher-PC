"""Test core/env_probe.py."""
from unittest.mock import MagicMock, patch

import pytest

from core.env_probe import (
    EnvSpec,
    _detect_os,
    _detect_physical_cores,
    _detect_ssd,
    _safe_import,
    auto_tune,
    probe,
    tune_apktool_jobs,
    tune_apktool_memory,
    tune_cache_compress,
    tune_cache_dir,
    tune_cache_max_mb,
    tune_json_engine,
    tune_log_file,
    tune_regex_engine,
    tune_worker_processes,
)


def _make_spec(**overrides) -> EnvSpec:
    defaults = dict(
        os_name="windows",
        cpu_count=8,
        cpu_count_physical=4,
        ram_total_mb=16384,
        ram_available_mb=8192,
        disk_free_mb=100000,
        disk_total_mb=500000,
        is_ssd=True,
        python_version=(3, 11),
        has_java=True,
        has_adb=False,
        has_re2=False,
        has_orjson=True,
    )
    defaults.update(overrides)
    return EnvSpec(**defaults)


# ============================================================
# _detect_os
# ============================================================
def test_detect_os_returns_string():
    os_name = _detect_os()
    assert os_name in ("windows", "linux", "darwin")


# ============================================================
# _safe_import
# ============================================================
def test_safe_import_true():
    assert _safe_import("os") is True


def test_safe_import_false():
    assert _safe_import("nonexistent_xyz_123") is False


# ============================================================
# _detect_physical_cores
# ============================================================
def test_detect_physical_cores_returns_int():
    n = _detect_physical_cores()
    assert isinstance(n, int)
    assert n >= 1


# ============================================================
# probe
# ============================================================
def test_probe_returns_envspec():
    spec = probe(force=True)
    assert isinstance(spec, EnvSpec)
    assert spec.cpu_count >= 1


def test_probe_cached():
    probe(force=True)
    spec1 = probe(force=False)
    spec2 = probe(force=False)
    assert spec1 is spec2


# ============================================================
# tune_apktool_jobs
# ============================================================
def test_tune_jobs_small_cpu():
    spec = _make_spec(cpu_count=4)
    assert tune_apktool_jobs(spec) == 3


def test_tune_jobs_large_cpu_capped():
    spec = _make_spec(cpu_count=32)
    assert tune_apktool_jobs(spec) == 8


def test_tune_jobs_single_core():
    spec = _make_spec(cpu_count=1)
    assert tune_apktool_jobs(spec) == 1


# ============================================================
# tune_apktool_memory
# ============================================================
def test_tune_memory_low_ram():
    spec = _make_spec(ram_available_mb=2048)
    assert tune_apktool_memory(spec) == "2048m"


def test_tune_memory_mid_ram():
    spec = _make_spec(ram_available_mb=8192)
    assert tune_apktool_memory(spec) == "6144m"


def test_tune_memory_high_ram():
    spec = _make_spec(ram_available_mb=32768)
    assert tune_apktool_memory(spec) == "8192m"


# ============================================================
# tune_worker_processes
# ============================================================
def test_tune_workers_basic():
    spec = _make_spec(cpu_count_physical=2)
    assert tune_worker_processes(spec) == 2


def test_tune_workers_capped():
    spec = _make_spec(cpu_count_physical=16)
    assert tune_worker_processes(spec) == 4


# ============================================================
# tune_cache_dir
# ============================================================
def test_tune_cache_dir_returns_path():
    spec = _make_spec()
    path = tune_cache_dir(spec)
    assert "cache" in path


def test_tune_log_file_returns_path():
    spec = _make_spec()
    path = tune_log_file(spec)
    assert "pipeline.log" in path


# ============================================================
# tune_cache_max_mb
# ============================================================
def test_tune_cache_max_min():
    spec = _make_spec(disk_free_mb=1000)
    assert tune_cache_max_mb(spec) == 1024


def test_tune_cache_max_capped():
    spec = _make_spec(disk_free_mb=10000000)
    assert tune_cache_max_mb(spec) == 20480


# ============================================================
# tune_cache_compress
# ============================================================
def test_tune_cache_compress_low_disk():
    spec = _make_spec(disk_free_mb=50000, disk_total_mb=500000)
    assert tune_cache_compress(spec) is True


def test_tune_cache_compress_ok():
    spec = _make_spec(disk_free_mb=400000, disk_total_mb=500000)
    assert tune_cache_compress(spec) is False


def test_tune_cache_compress_zero_total():
    spec = _make_spec(disk_free_mb=0, disk_total_mb=0)
    assert tune_cache_compress(spec) is False


# ============================================================
# tune_regex_engine
# ============================================================
def test_tune_regex_engine_no_re2():
    spec = _make_spec(has_re2=False)
    assert tune_regex_engine(spec) == "re"


# ============================================================
# tune_json_engine
# ============================================================
def test_tune_json_engine_orjson():
    spec = _make_spec(has_orjson=True)
    assert tune_json_engine(spec) == "orjson"


def test_tune_json_engine_stdlib():
    spec = _make_spec(has_orjson=False)
    assert tune_json_engine(spec) == "stdlib"


# ============================================================
# auto_tune
# ============================================================
def test_auto_tune_updates_auto_fields():
    config = {
        "pipeline": {"apktool_jobs": "auto", "apktool_memory": "auto"},
        "logging": {"file": "auto"},
        "cache": {
            "dir": "auto", "max_size_mb": "auto",
            "compress_decompiled": "auto",
        },
        "performance": {
            "worker_processes": "auto",
            "regex_engine": "auto",
            "json_engine": "auto",
        },
    }
    result = auto_tune(config)
    assert result["pipeline"]["apktool_jobs"] != "auto"
    assert result["pipeline"]["apktool_memory"] != "auto"
    assert result["performance"]["worker_processes"] != "auto"


def test_auto_tune_keeps_explicit_values():
    config = {
        "pipeline": {"apktool_jobs": 4, "apktool_memory": "2048m"},
    }
    result = auto_tune(config)
    assert result["pipeline"]["apktool_jobs"] == 4
    assert result["pipeline"]["apktool_memory"] == "2048m"