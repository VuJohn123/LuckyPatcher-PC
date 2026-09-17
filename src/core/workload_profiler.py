"""
Workload profiler — classify APK và predict resource needs.
Chạy trước pipeline để chọn strategy phù hợp.
"""
from __future__ import annotations

import logging
import os
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class SizeClass(str, Enum):
    TINY = "tiny"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    HUGE = "huge"
    MASSIVE = "massive"


class WorkloadType(str, Enum):
    UNITY_GAME = "unity_game"
    NATIVE_GAME = "native_game"
    CASUAL_APP = "casual_app"
    SYSTEM_APP = "system_app"
    MOD_HEAVY = "mod_heavy"
    UNKNOWN = "unknown"


class Strategy(str, Enum):
    FAST = "fast"           # max speed, min safety
    BALANCED = "balanced"   # default
    CAREFUL = "careful"     # slow but safe
    PARANOID = "paranoid"   # max safety for huge/unknown


@dataclass
class WorkloadProfile:
    """Kết quả profiling 1 APK."""
    apk_path: str
    size_mb: float
    size_class: SizeClass
    workload_type: WorkloadType
    strategy: Strategy

    # Predicted resource needs
    est_decompiled_mb: float        # dung lượng sau decompile (~5-15x APK)
    est_peak_ram_mb: float          # peak RAM khi decompile
    est_duration_sec: float         # thời gian dự kiến

    # Features detected
    dex_count: int = 0
    has_native_libs: bool = False
    has_obb: bool = False
    has_split_config: bool = False
    is_encrypted: bool = False

    # Metadata
    hints: dict = field(default_factory=dict)


# ============================================================
# MAIN PROFILER
# ============================================================
def profile_apk(apk_path: str) -> WorkloadProfile:
    """
    Phân tích APK để predict resource needs.
    Không decompile — chỉ đọc ZIP central directory (nhanh).
    """
    if not os.path.isfile(apk_path):
        return _unknown_profile(apk_path)

    try:
        size_bytes = os.path.getsize(apk_path)
    except OSError:
        return _unknown_profile(apk_path)

    size_mb = size_bytes / 1024 / 1024
    size_class = _classify_size(size_mb)

    # Đọc ZIP structure
    dex_count = 0
    has_native = False
    has_obb = False
    has_split = False
    entry_count = 0

    try:
        with zipfile.ZipFile(apk_path, "r") as z:
            for name in z.namelist():
                entry_count += 1
                lower = name.lower()
                if lower.endswith(".dex"):
                    dex_count += 1
                elif lower.startswith("lib/"):
                    has_native = True
                elif lower.endswith(".obb"):
                    has_obb = True
                elif lower.startswith("split_config."):
                    has_split = True
    except (zipfile.BadZipFile, OSError) as e:
        logger.warning("Không đọc được APK: %s", e)
        return _unknown_profile(apk_path, size_mb, size_class)

    # Classify workload type
    workload_type = _classify_type(
        apk_path, dex_count, has_native, has_split, size_mb
    )

    # Predict resource needs
    est_decompiled = _estimate_decompiled_size(
        size_mb, dex_count, has_native
    )
    est_ram = _estimate_peak_ram(
        est_decompiled, dex_count, has_native
    )
    est_duration = _estimate_duration(
        size_mb, dex_count, workload_type
    )

    # Choose strategy
    strategy = _choose_strategy(
        size_class, workload_type, dex_count, has_native
    )

    return WorkloadProfile(
        apk_path=apk_path,
        size_mb=size_mb,
        size_class=size_class,
        workload_type=workload_type,
        strategy=strategy,
        est_decompiled_mb=est_decompiled,
        est_peak_ram_mb=est_ram,
        est_duration_sec=est_duration,
        dex_count=dex_count,
        has_native_libs=has_native,
        has_obb=has_obb,
        has_split_config=has_split,
        hints={"entry_count": entry_count},
    )


# ============================================================
# CLASSIFIERS
# ============================================================
def _classify_size(size_mb: float) -> SizeClass:
    if size_mb < 10:
        return SizeClass.TINY
    if size_mb < 50:
        return SizeClass.SMALL
    if size_mb < 200:
        return SizeClass.MEDIUM
    if size_mb < 500:
        return SizeClass.LARGE
    if size_mb < 2048:
        return SizeClass.HUGE
    return SizeClass.MASSIVE


def _classify_type(
    apk_path: str, dex_count: int,
    has_native: bool, has_split: bool, size_mb: float,
) -> WorkloadType:
    name = Path(apk_path).stem.lower()

    # Heuristic từ tên file
    unity_hints = ("unity", "il2cpp", "unity3d")
    game_hints = (
        "game", "surf", "temple", "subway", "clash",
        "minecraft", "freefire", "pubg", "genshin",
    )
    system_hints = ("system", "systemui", "framework", "settings")

    if any(h in name for h in system_hints):
        return WorkloadType.SYSTEM_APP
    if any(h in name for h in unity_hints):
        return WorkloadType.UNITY_GAME
    if any(h in name for h in game_hints):
        return WorkloadType.NATIVE_GAME

    # Heuristic từ structure
    if has_native and dex_count >= 3 and size_mb > 100:
        return WorkloadType.NATIVE_GAME
    if dex_count >= 5:
        return WorkloadType.MOD_HEAVY
    if has_split:
        return WorkloadType.CASUAL_APP
    return WorkloadType.CASUAL_APP


def _choose_strategy(
    size_class: SizeClass,
    workload_type: WorkloadType,
    dex_count: int,
    has_native: bool,
) -> Strategy:
    """Chọn strategy dựa vào complexity."""
    # Massive/large + game → careful
    if size_class in (SizeClass.HUGE, SizeClass.MASSIVE):
        return Strategy.PARANOID
    if size_class == SizeClass.LARGE:
        return Strategy.CAREFUL
    if workload_type in (
        WorkloadType.UNITY_GAME, WorkloadType.NATIVE_GAME
    ):
        return Strategy.CAREFUL if dex_count > 3 else Strategy.BALANCED
    if dex_count > 5:
        return Strategy.CAREFUL
    if size_class in (SizeClass.TINY, SizeClass.SMALL):
        return Strategy.FAST
    return Strategy.BALANCED


# ============================================================
# ESTIMATORS
# ============================================================
def _estimate_decompiled_size(
    apk_mb: float, dex_count: int, has_native: bool
) -> float:
    """APK nén → decompiled thường 5-15x."""
    ratio = 8.0  # base
    if has_native:
        ratio = 6.0  # native libs ít nén hơn
    if dex_count > 5:
        ratio += 1.5
    return apk_mb * ratio


def _estimate_peak_ram(
    decompiled_mb: float, dex_count: int, has_native: bool
) -> float:
    """Peak RAM khi decompile ~ 1.5-2.5x decompiled size."""
    base = decompiled_mb * 2.0
    base += dex_count * 50  # mỗi dex ~50MB khi parse
    if has_native:
        base *= 1.2
    return base


def _estimate_duration(
    apk_mb: float, dex_count: int, workload_type: WorkloadType
) -> float:
    """Thời gian dự kiến (giây) trên máy trung bình."""
    # Base: ~1s per MB với apktool
    base = apk_mb * 1.0
    # Game decompile chậm hơn
    if workload_type in (
        WorkloadType.UNITY_GAME, WorkloadType.NATIVE_GAME
    ):
        base *= 1.5
    # Nhiều dex → tăng
    base += dex_count * 5
    return base


def _unknown_profile(
    apk_path: str, size_mb: float = 0.0,
    size_class: SizeClass = SizeClass.MEDIUM,
) -> WorkloadProfile:
    return WorkloadProfile(
        apk_path=apk_path,
        size_mb=size_mb,
        size_class=size_class,
        workload_type=WorkloadType.UNKNOWN,
        strategy=Strategy.BALANCED,
        est_decompiled_mb=size_mb * 8,
        est_peak_ram_mb=size_mb * 16,
        est_duration_sec=size_mb * 1.5,
    )