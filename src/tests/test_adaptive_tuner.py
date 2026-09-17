"""Test core/adaptive_tuner.py."""
import time
from unittest.mock import MagicMock, patch

import pytest

from core.adaptive_tuner import (
    AdaptiveTuner,
    RuntimeState,
    TuneMode,
    TuneResult,
    get_tuner,
)


# ============================================================
# Enums
# ============================================================
def test_tune_mode_values():
    assert TuneMode.DAILY.value == "daily"
    assert TuneMode.GAMING.value == "gaming"
    assert TuneMode.STRESS.value == "stress"
    assert TuneMode.BACKGROUND.value == "background"
    assert TuneMode.POWER_SAVER.value == "power_saver"


# ============================================================
# Singleton
# ============================================================
def test_singleton():
    t1 = AdaptiveTuner()
    t2 = AdaptiveTuner()
    assert t1 is t2


def test_get_tuner():
    assert isinstance(get_tuner(), AdaptiveTuner)


# ============================================================
# RuntimeState / TuneResult dataclasses
# ============================================================
def test_runtime_state():
    r = RuntimeState(
        ram_used_pct=50.0,
        ram_available_mb=4096,
        cpu_used_pct=20.0,
        disk_free_pct=80.0,
        cpu_temp_celsius=None,
        is_ac_power=True,
        timestamp=time.time(),
    )
    assert r.ram_available_mb == 4096


def test_tune_result():
    r = TuneResult(
        mode=TuneMode.DAILY,
        apktool_jobs=4,
        apktool_memory="4096m",
        worker_processes=2,
        fast_mode=False,
        use_gda=False,
        cache_enabled=True,
        ui_log_visible=True,
    )
    assert r.reasoning == []


# ============================================================
# _resolve_mode
# ============================================================
def _make_runtime(
    cpu=20.0, ram_used=50.0, is_ac=True, disk_free=80.0
):
    return RuntimeState(
        ram_used_pct=ram_used,
        ram_available_mb=4096,
        cpu_used_pct=cpu,
        disk_free_pct=disk_free,
        cpu_temp_celsius=None,
        is_ac_power=is_ac,
        timestamp=time.time(),
    )


def test_resolve_mode_explicit():
    t = AdaptiveTuner()
    r = _make_runtime()
    assert t._resolve_mode("daily", None, r) == TuneMode.DAILY
    assert t._resolve_mode("gaming", None, r) == TuneMode.GAMING
    assert t._resolve_mode("stress", None, r) == TuneMode.STRESS


def test_resolve_mode_enum_input():
    t = AdaptiveTuner()
    r = _make_runtime()
    assert t._resolve_mode(TuneMode.STRESS, None, r) == TuneMode.STRESS


def test_resolve_mode_battery():
    t = AdaptiveTuner()
    r = _make_runtime(is_ac=False)
    assert t._resolve_mode("auto", None, r) == TuneMode.POWER_SAVER


def test_resolve_mode_high_cpu():
    t = AdaptiveTuner()
    r = _make_runtime(cpu=90.0)
    assert t._resolve_mode("auto", None, r) == TuneMode.STRESS


def test_resolve_mode_high_ram():
    t = AdaptiveTuner()
    r = _make_runtime(ram_used=90.0)
    assert t._resolve_mode("auto", None, r) == TuneMode.STRESS


def test_resolve_mode_default_daily():
    t = AdaptiveTuner()
    r = _make_runtime()
    assert t._resolve_mode("auto", None, r) == TuneMode.DAILY


# ============================================================
# Tune full flow
# ============================================================
def test_tune_updates_config():
    t = AdaptiveTuner()

    with patch.object(t, "_get_runtime", return_value=_make_runtime()), \
         patch("core.env_probe.probe") as mock_probe:
        mock_env = MagicMock(
            cpu_count=8, cpu_count_physical=4,
            ram_total_mb=16384, ram_available_mb=8192,
            disk_free_mb=100000, disk_total_mb=500000,
        )
        mock_probe.return_value = mock_env

        config = {"pipeline": {}, "performance": {}, "cache": {}, "ui": {}}
        result = t.tune(config, workload=None, mode="daily")

        assert isinstance(result, TuneResult)
        assert config["pipeline"]["apktool_jobs"] >= 1
        assert config["performance"]["worker_processes"] >= 1


def test_tune_returns_reasoning():
    t = AdaptiveTuner()
    with patch.object(t, "_get_runtime", return_value=_make_runtime()), \
         patch("core.env_probe.probe") as mock_probe:
        mock_probe.return_value = MagicMock(
            cpu_count=8, cpu_count_physical=4,
            ram_total_mb=16384, ram_available_mb=8192,
            disk_free_mb=100000, disk_total_mb=500000,
        )
        result = t.tune({}, None, "daily")
        assert len(result.reasoning) > 0


# ============================================================
# _tune_jobs
# ============================================================
def test_tune_jobs_base_capped():
    t = AdaptiveTuner()
    env = MagicMock(cpu_count=32, cpu_count_physical=16)
    runtime = _make_runtime()
    reasoning = []
    jobs = t._tune_jobs(env, None, runtime, TuneMode.DAILY, reasoning)
    # Cap 8
    assert jobs <= 8


def test_tune_jobs_throttled_on_high_cpu():
    t = AdaptiveTuner()
    env = MagicMock(cpu_count=8, cpu_count_physical=4)
    runtime = _make_runtime(cpu=95.0)
    reasoning = []
    jobs = t._tune_jobs(env, None, runtime, TuneMode.DAILY, reasoning)
    # CPU throttle halved
    assert any("halved" in r for r in reasoning)


# ============================================================
# _tune_memory
# ============================================================
def test_tune_memory_returns_string():
    t = AdaptiveTuner()
    env = MagicMock(
        ram_total_mb=16384, ram_available_mb=8192,
    )
    runtime = _make_runtime()
    reasoning = []
    mem = t._tune_memory(env, None, runtime, TuneMode.DAILY, reasoning)
    assert mem.endswith("m")


def test_tune_memory_low_ram():
    t = AdaptiveTuner()
    env = MagicMock(ram_total_mb=2048, ram_available_mb=512)
    runtime = _make_runtime()
    reasoning = []
    mem = t._tune_memory(env, None, runtime, TuneMode.DAILY, reasoning)
    # Min heap 1024m
    assert mem == "1024m"


# ============================================================
# _tune_workers
# ============================================================
def test_tune_workers_returns_positive():
    t = AdaptiveTuner()
    env = MagicMock(cpu_count_physical=4)
    runtime = _make_runtime()
    reasoning = []
    workers = t._tune_workers(env, None, runtime, TuneMode.DAILY, reasoning)
    assert 1 <= workers <= 4


def test_tune_workers_low_ram():
    t = AdaptiveTuner()
    env = MagicMock(cpu_count_physical=4)
    runtime = RuntimeState(
        ram_used_pct=90.0,
        ram_available_mb=1024,  # < 2048
        cpu_used_pct=20.0,
        disk_free_pct=80.0,
        cpu_temp_celsius=None,
        is_ac_power=True,
        timestamp=time.time(),
    )
    reasoning = []
    workers = t._tune_workers(env, None, runtime, TuneMode.DAILY, reasoning)
    assert workers == 1


# ============================================================
# _tune_cache
# ============================================================
def test_tune_cache_low_disk():
    t = AdaptiveTuner()
    runtime = _make_runtime(disk_free=5.0)
    reasoning = []
    assert t._tune_cache(runtime, TuneMode.DAILY, reasoning) is False


def test_tune_cache_ok():
    t = AdaptiveTuner()
    runtime = _make_runtime(disk_free=80.0)
    reasoning = []
    assert t._tune_cache(runtime, TuneMode.DAILY, reasoning) is True


# ============================================================
# _tune_log_visible
# ============================================================
def test_tune_log_visible_stress():
    t = AdaptiveTuner()
    reasoning = []
    assert t._tune_log_visible(TuneMode.STRESS, None, reasoning) is False


def test_tune_log_visible_daily():
    t = AdaptiveTuner()
    reasoning = []
    assert t._tune_log_visible(TuneMode.DAILY, None, reasoning) is True


# ============================================================
# _tune_fast_mode
# ============================================================
def test_tune_fast_mode_daily():
    t = AdaptiveTuner()
    reasoning = []
    assert t._tune_fast_mode(None, TuneMode.DAILY, reasoning) is False


def test_tune_fast_mode_stress():
    t = AdaptiveTuner()
    reasoning = []
    assert t._tune_fast_mode(None, TuneMode.STRESS, reasoning) is True