"""
Filesystem utilities — junction/symlink, robocopy, safe copy với verify.

v2: `safe_copytree` thêm mode="copy" — never junction (dùng cho cache_load
    để tránh cache pollution khi patches modify workspace).
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from typing import Callable

from core.progress import Progress

logger = logging.getLogger(__name__)

_COPY_FAIL_TOLERANCE = 0.05
_DISK_MIN_READ_PCT = 3.0
_DISK_MIN_WRITE_PCT = 8.0


# ============================================================
# JUNCTION / SYMLINK
# ============================================================
def remove_dst(dst: str) -> None:
    """Xoá dst an toàn với junction Windows (không follow target)."""
    if not os.path.exists(dst) and not os.path.islink(dst):
        return
    try:
        os.rmdir(dst)
        return
    except OSError:
        pass
    if os.path.isdir(dst) and not os.path.islink(dst):
        shutil.rmtree(dst, ignore_errors=True)
        return
    try:
        os.remove(dst)
    except OSError:
        pass


def is_link_to(src: str, dst: str) -> bool:
    try:
        return os.path.realpath(src) == os.path.realpath(dst)
    except OSError:
        return False


def try_link(src: str, dst: str) -> bool:
    """Tạo junction/symlink thay vì copy."""
    remove_dst(dst)
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", dst, src],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        os.symlink(src, dst, target_is_directory=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


# ============================================================
# ROBOCOPY
# ============================================================
def has_robocopy() -> bool:
    return os.name == "nt" and shutil.which("robocopy") is not None


def robocopy_copy(
    src: str,
    dst: str,
    log_callback: Callable[[str], None],
    label: str = "Cache save",
) -> bool:
    """Copy src → dst dùng robocopy /MT:32. Return True nếu handled."""
    if not has_robocopy():
        return False

    try:
        os.makedirs(dst, exist_ok=True)
    except OSError as e:
        log_callback(f"[!] [{label}] mkdir fail: {e}")
        return True

    cmd = [
        "robocopy", src, dst,
        "/E", "/MT:32",
        "/NFL", "/NDL", "/NJH", "/NJS", "/NC", "/NS", "/NP",
        "/R:0", "/W:0",
    ]

    log_callback(f"[*] [{label}] robocopy /MT:32 → {os.path.basename(dst)}")
    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd, capture_output=True, timeout=1800,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        log_callback(f"[!] [{label}] robocopy timeout 1800s")
        return True
    except OSError as e:
        log_callback(f"[!] [{label}] robocopy fail: {e}")
        return False

    elapsed = time.monotonic() - start
    if result.returncode >= 8:
        log_callback(
            f"[!] [{label}] robocopy rc={result.returncode}: "
            f"{(result.stdout or '')[-200:]}"
        )
        return True

    try:
        file_count = sum(len(f) for _, _, f in os.walk(dst))
        log_callback(
            f"[✔] [{label}] robocopy copied {file_count} files "
            f"in {elapsed:.1f}s"
        )
    except OSError:
        log_callback(f"[✔] [{label}] robocopy in {elapsed:.1f}s")
    return True


# ============================================================
# SAFE COPYTREE
# ============================================================
def safe_copytree(
    src: str,
    dst: str,
    log_callback: Callable[[str], None],
    label: str = "Cache",
    heartbeat_sec: int = 15,
    mode: str = "write",
    fail_tolerance: float = _COPY_FAIL_TOLERANCE,
) -> bool:
    """
    Copy tree.

    mode:
      "read"  — thử junction trước, fallback copy (tối ưu read-only)
      "write" — copy fresh (cache save)
      "copy"  — KHÔNG BAO GIỜ junction, chỉ copy (dùng cho cache_load để
                tránh cache pollution khi patches modify workspace)
    """
    # ---- Junction fast path CHỈ cho mode="read" ----
    if mode == "read":
        if is_link_to(src, dst):
            log_callback(f"[✔] [{label}] Already linked — reuse")
            return True
        if try_link(src, dst):
            log_callback(
                f"[✔] [{label}] Linked (junction/symlink) — no disk cost"
            )
            return True

    # ---- Disk check ----
    min_pct = _DISK_MIN_READ_PCT if mode == "read" else _DISK_MIN_WRITE_PCT
    try:
        parent = os.path.dirname(dst) or dst
        os.makedirs(parent, exist_ok=True)
        usage = shutil.disk_usage(parent)
        free_pct = usage.free * 100 / usage.total
        if free_pct < min_pct:
            log_callback(
                f"[i] [{label}] Disk còn {free_pct:.1f}% (<{min_pct}%) "
                f"— skip {mode}"
            )
            return False
    except OSError:
        pass

    # ---- Collect files ----
    all_files: list[tuple[str, str]] = []
    try:
        for root, _dirs, files in os.walk(src):
            rel = os.path.relpath(root, src)
            for f in files:
                rel_p = os.path.join(rel, f) if rel != "." else f
                all_files.append((os.path.join(root, f), rel_p))
    except OSError as e:
        log_callback(f"[!] [{label}] Walk fail: {e}")
        return False

    total = len(all_files)
    log_callback(f"[*] [{label}] Copy {total} files → {dst}")

    remove_dst(dst)

    start = time.monotonic()
    prog = Progress(total, label=label, log_callback=log_callback,
                    step_pct=10)
    copied = 0
    failed = 0
    samefile = 0
    failed_samples: list[str] = []

    for abs_p, rel_p in all_files:
        target = os.path.join(dst, rel_p)
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
        except OSError as e:
            failed += 1
            if len(failed_samples) < 3:
                failed_samples.append(f"mkdir {rel_p}: {e}")
            continue
        try:
            shutil.copy2(abs_p, target)
            copied += 1
        except shutil.SameFileError:
            samefile += 1
        except (OSError, shutil.Error) as e:
            failed += 1
            if len(failed_samples) < 3:
                failed_samples.append(f"{rel_p}: {e}")
        prog.update()

    prog.close()
    elapsed = time.monotonic() - start
    grand = copied + failed

    for sample in failed_samples:
        log_callback(f"[i] [{label}] skip: {sample}")

    if samefile > 0 and failed == 0:
        log_callback(
            f"[✔] [{label}] {samefile} files đã tồn tại trong "
            f"{elapsed:.1f}s"
        )
        return True

    if failed > 0:
        fail_ratio = failed / grand if grand else 0.0
        log_callback(
            f"[!] [{label}] {failed}/{grand} fail "
            f"({fail_ratio*100:.2f}%) sau {elapsed:.1f}s"
        )
        if fail_ratio > fail_tolerance:
            raise RuntimeError(
                f"[{label}] fail ratio {fail_ratio*100:.2f}% > "
                f"{fail_tolerance*100:.0f}% — bỏ."
            )

    log_callback(f"[✔] [{label}] Copied {copied}/{grand} in {elapsed:.1f}s")
    return True


# Backward compat
_remove_dst = remove_dst
_is_link_to = is_link_to
_try_link = try_link
_safe_copytree = safe_copytree
_find_robocopy = has_robocopy
_robocopy_copy = robocopy_copy