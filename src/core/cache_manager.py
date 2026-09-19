"""
Cache manager — quyết định raw vs archive, save/load decompiled cache.

v2: cache_load KHÔNG dùng junction (tránh cache pollution khi patches
    modify workspace). Luôn dùng robocopy/Python copy.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Callable

from core.fs_utils import (
    has_robocopy,
    remove_dst,
    robocopy_copy,
    safe_copytree,
)
from core.archive_utils import (
    archive_via_7z,
    archive_via_python,
    extract_via_7z,
    extract_via_python,
)

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

_CACHE_ARCHIVE_THRESHOLD_FILES = 3000
_CACHE_ARCHIVE_THRESHOLD_MB = 50.0

_CACHE_7Z_FILENAME = "decompiled.7z"
_CACHE_ZIP_FILENAME = "decompiled.zip"
_CACHE_TAR_FILENAME = "decompiled.tar"


# ============================================================
# HASH + DIR
# ============================================================
def get_apk_hash(apk_path: str) -> str:
    hasher = hashlib.md5()
    with open(apk_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_cache_dir(apk_path: str, base_cache_dir: str | None = None) -> str:
    if base_cache_dir is None:
        base_cache_dir = os.path.join(_PROJECT_ROOT, "workspace", "cache")
    cache_dir = os.path.join(base_cache_dir, get_apk_hash(apk_path))
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


# ============================================================
# FORMAT DECISION
# ============================================================
def decide_cache_format(src_dir: str) -> str:
    """Return "archive" | "raw"."""
    file_count = 0
    total_bytes = 0
    try:
        for root, _dirs, files in os.walk(src_dir):
            for f in files:
                file_count += 1
                try:
                    total_bytes += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
                if (file_count > _CACHE_ARCHIVE_THRESHOLD_FILES
                        or total_bytes > _CACHE_ARCHIVE_THRESHOLD_MB * 1024 * 1024):
                    return "archive"
    except OSError:
        pass
    return "raw"


# ============================================================
# DISCOVERY
# ============================================================
def find_existing_archive(cache_dir: str) -> str | None:
    for name in (_CACHE_7Z_FILENAME, _CACHE_TAR_FILENAME,
                 _CACHE_ZIP_FILENAME):
        p = os.path.join(cache_dir, name)
        if os.path.exists(p):
            return p
    return None


def cache_is_valid(cache_dir: str) -> bool:
    if not os.path.isdir(cache_dir):
        return False
    if find_existing_archive(cache_dir):
        return True
    if os.path.exists(os.path.join(cache_dir, "apktool.yml")):
        return True
    return False


def cache_mtime(cache_dir: str) -> float:
    arch = find_existing_archive(cache_dir)
    if arch:
        try:
            return os.path.getmtime(arch)
        except OSError:
            pass
    yml = os.path.join(cache_dir, "apktool.yml")
    if os.path.exists(yml):
        try:
            return os.path.getmtime(yml)
        except OSError:
            pass
    return 0.0


# ============================================================
# SAVE
# ============================================================
def write_cache_marker(cache_dir: str, marker: str) -> None:
    try:
        p = os.path.join(cache_dir, ".cache_format")
        with open(p, "w", encoding="utf-8") as f:
            f.write(marker)
    except OSError:
        pass


def cache_save(
    output_dir: str,
    cache_dir: str,
    log_callback: Callable[[str], None],
) -> bool:
    """
    Save output_dir → cache_dir.
    Strategy:
      1. robocopy /MT:32 (Windows, fastest) — raw copy
      2. 7z archive (disk-adaptive)
      3. Python zip STORED
    """
    format_type = decide_cache_format(output_dir)

    # --- Robocopy first (fastest on Windows) ---
    if format_type == "archive" and has_robocopy():
        remove_dst(cache_dir)
        log_callback(
            "[i] [Cache save] Mode: robocopy /MT:32 (raw copy, fastest)"
        )
        if robocopy_copy(output_dir, cache_dir, log_callback,
                         label="Cache save"):
            write_cache_marker(cache_dir, "raw")
            return True

    # --- 7z archive ---
    if format_type == "archive":
        archive_name = _CACHE_7Z_FILENAME
        archive_path = os.path.join(cache_dir, archive_name)

        for name in (_CACHE_7Z_FILENAME, _CACHE_TAR_FILENAME,
                     _CACHE_ZIP_FILENAME, "apktool.yml", ".cache_format"):
            p = os.path.join(cache_dir, name)
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass

        if archive_via_7z(output_dir, archive_path, log_callback):
            write_cache_marker(cache_dir, archive_name)
            return os.path.exists(archive_path)

        log_callback("[i] [Cache save] Fallback Python zip STORED")
        fallback_path = os.path.join(cache_dir, _CACHE_ZIP_FILENAME)
        ok = archive_via_python(output_dir, fallback_path, log_callback)
        if ok:
            write_cache_marker(cache_dir, _CACHE_ZIP_FILENAME)
        return ok

    # --- Raw mode (small dirs) ---
    remove_dst(cache_dir)
    ok = safe_copytree(
        output_dir, cache_dir,
        log_callback=log_callback,
        label="Cache save",
        heartbeat_sec=15,
        mode="write",
    )
    if ok:
        write_cache_marker(cache_dir, "raw")
    return ok


# ============================================================
# LOAD — v2: KHÔNG junction (tránh cache pollution)
# ============================================================
def cache_load(
    cache_dir: str,
    output_dir: str,
    log_callback: Callable[[str], None],
) -> bool:
    """
    Load cache_dir → output_dir.

    QUAN TRỌNG: KHÔNG dùng junction (unlike v1). Vì sau khi load,
    pipeline sẽ PATCH workspace — nếu workspace = junction → cache bị
    ô nhiễm bởi patches. Dùng copy (robocopy/Python) để cache luôn sạch.
    """
    archive_path = find_existing_archive(cache_dir)
    if archive_path:
        if extract_via_7z(archive_path, output_dir, log_callback):
            return os.path.isdir(output_dir)
        if archive_path.endswith(".zip"):
            return extract_via_python(
                archive_path, output_dir, log_callback
            )
        log_callback(
            f"[!] [Cache load] Không có 7z.exe để extract "
            f"{os.path.basename(archive_path)}"
        )
        return False

    # Raw cache — copy (NO junction)
    # Remove any stale junction/symlink from previous runs
    if os.path.islink(output_dir) or (
        os.path.exists(output_dir) and os.path.isdir(output_dir)
    ):
        remove_dst(output_dir)

    if has_robocopy():
        log_callback(
            "[i] [Cache load] robocopy (no junction — cache stays clean)"
        )
        if robocopy_copy(cache_dir, output_dir, log_callback,
                         label="Cache load"):
            return os.path.isdir(output_dir)

    # Python copy fallback — mode="copy" (no junction)
    return safe_copytree(
        cache_dir, output_dir,
        log_callback=log_callback,
        label="Cache load",
        heartbeat_sec=15,
        mode="copy",
    )


# Backward compat
_decide_cache_format = decide_cache_format
_find_existing_archive = find_existing_archive
_cache_save = cache_save
_cache_load = cache_load
_write_cache_marker = write_cache_marker
_cache_is_valid = cache_is_valid
_cache_mtime = cache_mtime