"""Test core/workload_profiler.py."""
import io
import os
import zipfile

import pytest

from core.workload_profiler import (
    SizeClass,
    Strategy,
    WorkloadProfile,
    WorkloadType,
    _choose_strategy,
    _classify_size,
    _classify_type,
    _estimate_decompiled_size,
    _estimate_duration,
    _estimate_peak_ram,
    profile_apk,
)


def _make_apk(tmp_path, name: str = "test.apk", files: dict = None) -> str:
    apk = tmp_path / name
    files = files or {"AndroidManifest.xml": b"<manifest/>"}
    with zipfile.ZipFile(apk, "w") as z:
        for n, data in files.items():
            z.writestr(n, data)
    return str(apk)


# ============================================================
# _classify_size
# ============================================================
def test_classify_size_tiny():
    assert _classify_size(5) == SizeClass.TINY


def test_classify_size_small():
    assert _classify_size(30) == SizeClass.SMALL


def test_classify_size_medium():
    assert _classify_size(100) == SizeClass.MEDIUM


def test_classify_size_large():
    assert _classify_size(300) == SizeClass.LARGE


def test_classify_size_huge():
    assert _classify_size(1000) == SizeClass.HUGE


def test_classify_size_massive():
    assert _classify_size(3000) == SizeClass.MASSIVE


# ============================================================
# profile_apk
# ============================================================
def test_profile_nonexistent():
    p = profile_apk("/nonexistent.apk")
    assert isinstance(p, WorkloadProfile)
    assert p.size_mb == 0.0


def test_profile_small_apk(tmp_path):
    apk = _make_apk(tmp_path)
    p = profile_apk(apk)
    assert p.size_mb > 0
    assert isinstance(p.size_class, SizeClass)
    assert isinstance(p.strategy, Strategy)


def test_profile_apk_with_dex(tmp_path):
    apk = _make_apk(tmp_path, files={
        "classes.dex": b"\x00" * 100,
        "classes2.dex": b"\x00" * 100,
        "AndroidManifest.xml": b"<manifest/>",
    })
    p = profile_apk(apk)
    assert p.dex_count == 2


def test_profile_apk_with_native(tmp_path):
    apk = _make_apk(tmp_path, files={
        "lib/arm64-v8a/libtest.so": b"binary",
        "AndroidManifest.xml": b"<manifest/>",
    })
    p = profile_apk(apk)
    assert p.has_native_libs is True


def test_profile_bad_zip(tmp_path):
    bad = tmp_path / "bad.apk"
    bad.write_bytes(b"not a zip")
    p = profile_apk(str(bad))
    assert isinstance(p, WorkloadProfile)


# ============================================================
# _classify_type
# ============================================================
def test_classify_type_unity_from_name():
    t = _classify_type("UnityGame.apk", 1, False, False, 50)
    assert t == WorkloadType.UNITY_GAME


def test_classify_type_game_from_name():
    t = _classify_type("subway_surfers.apk", 1, False, False, 50)
    assert t == WorkloadType.NATIVE_GAME


def test_classify_type_system():
    t = _classify_type("systemui.apk", 1, False, False, 50)
    assert t == WorkloadType.SYSTEM_APP


def test_classify_type_native_game_by_structure():
    t = _classify_type("app.apk", 4, True, False, 150)
    assert t == WorkloadType.NATIVE_GAME


def test_classify_type_mod_heavy():
    t = _classify_type("app.apk", 6, False, False, 50)
    assert t == WorkloadType.MOD_HEAVY


def test_classify_type_casual():
    t = _classify_type("app.apk", 1, False, False, 20)
    assert t == WorkloadType.CASUAL_APP


# ============================================================
# _choose_strategy
# ============================================================
def test_strategy_huge():
    s = _choose_strategy(SizeClass.HUGE, WorkloadType.CASUAL_APP, 1, False)
    assert s == Strategy.PARANOID


def test_strategy_large():
    s = _choose_strategy(SizeClass.LARGE, WorkloadType.CASUAL_APP, 1, False)
    assert s == Strategy.CAREFUL


def test_strategy_unity_large():
    s = _choose_strategy(
        SizeClass.MEDIUM, WorkloadType.UNITY_GAME, 4, False
    )
    assert s == Strategy.CAREFUL


def test_strategy_tiny_fast():
    s = _choose_strategy(
        SizeClass.TINY, WorkloadType.CASUAL_APP, 1, False
    )
    assert s == Strategy.FAST


# ============================================================
# Estimators
# ============================================================
def test_estimate_decompiled_size():
    size = _estimate_decompiled_size(50, 1, False)
    assert size > 50


def test_estimate_decompiled_size_with_native():
    size = _estimate_decompiled_size(50, 1, True)
    assert 50 < size < 50 * 8


def test_estimate_peak_ram():
    ram = _estimate_peak_ram(100, 1, False)
    assert ram > 100


def test_estimate_duration():
    duration = _estimate_duration(50, 1, WorkloadType.CASUAL_APP)
    assert duration > 0