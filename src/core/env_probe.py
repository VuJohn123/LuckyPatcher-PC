"""
Environment probe — detect CPU/RAM/disk/OS để auto-tune config.

Chạy 1 lần khi load_config(), kết quả cache 5 phút.
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================
# PROBE CACHE
# ============================================================
_probe_cache: "EnvSpec | None" = None
_probe_ts: float = 0.0
_PROBE_TTL = 300.0  # 5 phút


@dataclass(frozen=True)
class EnvSpec:
    """Snapshot môi trường — immutable."""
    os_name: str            # windows | linux | darwin
    cpu_count: int
    cpu_count_physical: int
    ram_total_mb: int
    ram_available_mb: int
    disk_free_mb: int
    disk_total_mb: int
    is_ssd: bool
    python_version: tuple[int, int]
    has_java: bool
    has_adb: bool
    has_re2: bool
    has_orjson: bool


# ============================================================
# PROBE
# ============================================================
def probe(force: bool = False) -> EnvSpec:
    """Detect môi trường — cache 5 phút."""
    global _probe_cache, _probe_ts

    now = time.monotonic()
    if not force and _probe_cache and (now - _probe_ts) < _PROBE_TTL:
        return _probe_cache

    spec = EnvSpec(
        os_name=_detect_os(),
        cpu_count=os.cpu_count() or 4,
        cpu_count_physical=_detect_physical_cores(),
        ram_total_mb=_detect_ram_total(),
        ram_available_mb=_detect_ram_available(),
        disk_free_mb=_detect_disk_free(),
        disk_total_mb=_detect_disk_total(),
        is_ssd=_detect_ssd(),
        python_version=(sys.version_info.major, sys.version_info.minor),
        has_java=shutil.which("java") is not None,
        has_adb=shutil.which("adb") is not None,
        has_re2=_safe_import("re2"),
        has_orjson=_safe_import("orjson"),
    )

    _probe_cache = spec
    _probe_ts = now
    logger.info(
        "Env probe: os=%s cpu=%d ram=%dMB/%dMB disk_free=%dMB ssd=%s",
        spec.os_name, spec.cpu_count, spec.ram_available_mb,
        spec.ram_total_mb, spec.disk_free_mb, spec.is_ssd,
    )
    return spec


# ============================================================
# DETECTORS
# ============================================================
def _detect_os() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def _detect_physical_cores() -> int:
    """Physical cores (không tính hyperthreading)."""
    try:
        import psutil
        return psutil.cpu_count(logical=False) or os.cpu_count() or 4
    except ImportError:
        return os.cpu_count() or 4


def _detect_ram_total() -> int:
    """RAM total (MB)."""
    try:
        import psutil
        return int(psutil.virtual_memory().total / 1024 / 1024)
    except ImportError:
        return _detect_ram_fallback()


def _detect_ram_available() -> int:
    """RAM khả dụng (MB)."""
    try:
        import psutil
        return int(psutil.virtual_memory().available / 1024 / 1024)
    except ImportError:
        return _detect_ram_fallback()


def _detect_ram_fallback() -> int:
    """Fallback khi không có psutil."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return int(stat.ullTotalPhys / 1024 / 1024)
        except Exception:
            pass
    return 4096  # assume 4GB


def _detect_disk_free() -> int:
    """Disk free của workspace (MB)."""
    try:
        root = _project_root()
        return int(shutil.disk_usage(root).free / 1024 / 1024)
    except Exception:
        return 10240  # assume 10GB


def _detect_disk_total() -> int:
    try:
        root = _project_root()
        return int(shutil.disk_usage(root).total / 1024 / 1024)
    except Exception:
        return 102400  # assume 100GB


def _detect_ssd() -> bool:
    """
    Detect SSD vs HDD.
    Không chính xác 100% — dùng heuristic.
    """
    if sys.platform.startswith("win"):
        return True  # Windows 10+ thường SSD
    # Linux: check /sys/block/*/queue/rotational
    try:
        for dev in Path("/sys/block").iterdir():
            rotational = dev / "queue" / "rotational"
            if rotational.exists():
                if rotational.read_text().strip() == "1":
                    return False  # có ít nhất 1 HDD
        return True
    except Exception:
        return True  # assume SSD


def _safe_import(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


# ============================================================
# AUTO-TUNE FUNCTIONS
# ============================================================
def tune_apktool_jobs(spec: EnvSpec) -> int:
    """Số thread apktool: giữ 1 core cho OS, cap 8 để tránh I/O contention."""
    return max(1, min(spec.cpu_count - 1, 8))


def tune_apktool_memory(spec: EnvSpec) -> str:
    """Java heap: ~50% RAM available, cap 8GB."""
    available = spec.ram_available_mb
    if available < 4096:
        heap = 2048
    elif available < 8192:
        heap = 4096
    elif available < 16384:
        heap = 6144
    else:
        heap = 8192
    return f"{heap}m"


def tune_worker_processes(spec: EnvSpec) -> int:
    """ProcessPool workers: physical cores, cap 4."""
    return max(1, min(spec.cpu_count_physical, 4))


def tune_cache_dir(spec: EnvSpec) -> str:
    return str(_project_root() / "workspace" / "cache")


def tune_log_file(spec: EnvSpec) -> str:
    return str(_project_root() / "logs" / "pipeline.log")


def tune_cache_max_mb(spec: EnvSpec) -> int:
    """5% disk free, min 1GB, max 20GB."""
    pct = spec.disk_free_mb * 5 // 100
    return max(1024, min(pct, 20480))


def tune_cache_compress(spec: EnvSpec) -> bool:
    """Compress nếu disk còn < 20% free."""
    if spec.disk_total_mb == 0:
        return False
    free_pct = spec.disk_free_mb * 100 / spec.disk_total_mb
    return free_pct < 20


def tune_regex_engine(spec: EnvSpec) -> str:
    """re2 nếu có và tương thích API, ngược lại re."""
    if not spec.has_re2:
        return "re"
    try:
        import re2
        # Verify API tương thích
        if hasattr(re2, "DOTALL") and hasattr(re2, "IGNORECASE"):
            return "re2"
    except ImportError:
        pass
    return "re"


def tune_json_engine(spec: EnvSpec) -> str:
    return "orjson" if spec.has_orjson else "stdlib"


# ============================================================
# MAIN AUTO-TUNE
# ============================================================
def auto_tune(config: dict) -> dict:
    """
    Apply auto-tune vào config dict (in-place modifications).
    Chỉ động vào field có giá trị "auto".
    """
    spec = probe()

    def _resolve(section: str, key: str, value, tuned):
        if value == "auto":
            config.setdefault(section, {})[key] = tuned

    # pipeline
    pl = config.get("pipeline", {})
    _resolve("pipeline", "apktool_jobs",
             pl.get("apktool_jobs"), tune_apktool_jobs(spec))
    _resolve("pipeline", "apktool_memory",
             pl.get("apktool_memory"), tune_apktool_memory(spec))

    # logging
    lg = config.get("logging", {})
    _resolve("logging", "file", lg.get("file"), tune_log_file(spec))

    # cache
    ca = config.get("cache", {})
    _resolve("cache", "dir", ca.get("dir"), tune_cache_dir(spec))
    _resolve("cache", "max_size_mb",
             ca.get("max_size_mb"), tune_cache_max_mb(spec))
    _resolve("cache", "compress_decompiled",
             ca.get("compress_decompiled"), tune_cache_compress(spec))

    # performance
    pf = config.get("performance", {})
    _resolve("performance", "worker_processes",
             pf.get("worker_processes"), tune_worker_processes(spec))
    _resolve("performance", "regex_engine",
             pf.get("regex_engine"), tune_regex_engine(spec))
    _resolve("performance", "json_engine",
             pf.get("json_engine"), tune_json_engine(spec))

    return config