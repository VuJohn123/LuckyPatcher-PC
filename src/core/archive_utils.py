"""
Archive utilities — 7z (ưu tiên) + Python zipfallback.

Format quyết định dựa trên disk free:
  >40%  → 7z -mx=0 (COPY mode, fastest)
  20-40% → 7z -mx=1
  <20%  → 7z -mx=3
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
import zipfile
from typing import Callable

from core.progress import Progress

logger = logging.getLogger(__name__)

_TOOLS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)
    ))),
    "tools",
)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))

_DISK_MIN_WRITE_PCT = 8.0
_DISK_LOW_PCT = 20.0
_DISK_MEDIUM_PCT = 40.0


# ============================================================
# 7-ZIP DETECTION
# ============================================================
def find_7zip() -> str | None:
    for name in ("7z.exe", "7za.exe", "7zr.exe", "7z"):
        p = os.path.join(_TOOLS_DIR, "bin", name)
        if os.path.exists(p):
            return p
    for name in ("7z", "7z.exe", "7za", "7zr"):
        p = shutil.which(name)
        if p:
            return p
    for p in (
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ):
        if os.path.exists(p):
            return p
    return None


# ============================================================
# 7Z ARGS (DISK-ADAPTIVE)
# ============================================================
def choose_7z_args() -> tuple[list[str], str]:
    try:
        usage = shutil.disk_usage(_PROJECT_ROOT)
        free_pct = usage.free * 100 / usage.total
    except OSError:
        free_pct = 50.0

    if free_pct > _DISK_MEDIUM_PCT:
        return ["-t7z", "-mx=0", "-mmt", "-y"], "copy"
    elif free_pct > _DISK_LOW_PCT:
        return ["-t7z", "-mx=1", "-mmt", "-y"], "mx1"
    else:
        return ["-t7z", "-mx=3", "-mmt", "-y"], "mx3"


# ============================================================
# 7Z RUN WITH PROGRESS PARSING
# ============================================================
def run_7z_with_progress(
    cmd: list[str],
    log_callback: Callable[[str], None],
    label: str,
    cwd: str | None = None,
    timeout_sec: int = 1800,
) -> int:
    """Chạy 7z với progress parsing (7z dùng \\r cho updates)."""
    if "-bsp1" not in cmd:
        cmd = cmd + ["-bsp1", "-bso0", "-bse0"]

    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=0,
        )
    except OSError as e:
        log_callback(f"[!] [{label}] 7z không chạy được: {e}")
        return -1

    start = time.monotonic()
    last_pct = -1
    last_emit_ts = start
    output_buf = b""
    killed = {"flag": False, "reason": ""}
    stop = threading.Event()

    def _watch():
        while not stop.is_set():
            if time.monotonic() - start > timeout_sec:
                killed["flag"] = True
                killed["reason"] = "timeout"
                try:
                    proc.kill()
                except OSError:
                    pass
                return
            if time.monotonic() - last_emit_ts > 60:
                log_callback(
                    f"[i] [{label}] 7z {time.monotonic()-start:.0f}s "
                    f"(silent >60s)"
                )
            stop.wait(5)

    hb = threading.Thread(target=_watch, daemon=True)
    hb.start()

    try:
        while True:
            chunk = proc.stdout.read(256)
            if not chunk:
                break
            output_buf += chunk
            while True:
                i_r = output_buf.find(b"\r")
                i_n = output_buf.find(b"\n")
                if i_r == -1 and i_n == -1:
                    break
                if i_r == -1:
                    i = i_n
                elif i_n == -1:
                    i = i_r
                else:
                    i = min(i_r, i_n)
                line = output_buf[:i].decode(
                    "utf-8", errors="replace"
                ).strip()
                output_buf = output_buf[i + 1:]
                if not line:
                    continue

                pct = None
                try:
                    pct = int(line.strip().split()[0].rstrip("%"))
                except (ValueError, IndexError):
                    pct = None

                now = time.monotonic()
                if pct is not None and pct >= last_pct + 5:
                    log_callback(
                        f"[i] [{label}] {pct}% ({now-start:.0f}s)"
                    )
                    last_pct = pct
                    last_emit_ts = now
                elif now - last_emit_ts > 60:
                    log_callback(
                        f"[i] [{label}] 7z running {now-start:.0f}s..."
                    )
                    last_emit_ts = now

        rc = proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass
        rc = -1
    finally:
        stop.set()

    elapsed = time.monotonic() - start
    if killed["flag"]:
        log_callback(
            f"[!] [{label}] 7z killed ({killed['reason']}) "
            f"sau {elapsed:.1f}s"
        )
        return -1

    log_callback(f"[✔] [{label}] 7z xong {elapsed:.1f}s (rc={rc})")
    return rc


# ============================================================
# ARCHIVE / EXTRACT VIA 7Z
# ============================================================
def archive_via_7z(
    src_dir: str,
    archive_path: str,
    log_callback: Callable[[str], None],
    label: str = "Cache save",
) -> bool:
    exe = find_7zip()
    if not exe:
        return False

    try:
        parent = os.path.dirname(archive_path) or "."
        os.makedirs(parent, exist_ok=True)
        usage = shutil.disk_usage(parent)
        free_pct = usage.free * 100 / usage.total
        if free_pct < _DISK_MIN_WRITE_PCT:
            log_callback(
                f"[i] [{label}] Disk còn {free_pct:.1f}% "
                f"(<{_DISK_MIN_WRITE_PCT}%) — skip"
            )
            return True
    except OSError:
        pass

    tmp_path = archive_path + ".tmp"
    try:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    except OSError:
        pass

    total = 0
    total_bytes = 0
    try:
        for root, _dirs, files in os.walk(src_dir):
            for f in files:
                total += 1
                try:
                    total_bytes += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    except OSError:
        pass

    args, mode = choose_7z_args()
    log_callback(
        f"[*] [{label}] 7z ({mode}) {total} files "
        f"({total_bytes / 1024 / 1024:.1f} MB) → "
        f"{os.path.basename(archive_path)}"
    )

    cmd = [exe, "a"] + args + [tmp_path, "."]
    rc = run_7z_with_progress(
        cmd, log_callback, label, cwd=src_dir, timeout_sec=1800,
    )

    if rc != 0:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return True

    try:
        os.replace(tmp_path, archive_path)
    except OSError as e:
        log_callback(f"[!] [{label}] Rename fail: {e}")
        return True

    try:
        size_mb = os.path.getsize(archive_path) / 1024 / 1024
        ratio = size_mb / (total_bytes / 1024 / 1024) if total_bytes else 0
        log_callback(
            f"[✔] [{label}] Archive {size_mb:.1f} MB (ratio {ratio:.2f})"
        )
    except OSError:
        pass
    return True


def extract_via_7z(
    archive_path: str,
    dst_dir: str,
    log_callback: Callable[[str], None],
    label: str = "Cache load",
) -> bool:
    exe = find_7zip()
    if not exe or not os.path.exists(archive_path):
        return False

    from core.fs_utils import remove_dst
    tmp_dir = dst_dir + ".tmp"
    remove_dst(tmp_dir)
    try:
        os.makedirs(tmp_dir, exist_ok=True)
    except OSError as e:
        log_callback(f"[!] [{label}] mkdir tmp fail: {e}")
        return True

    cmd = [exe, "x", archive_path, f"-o{tmp_dir}", "-y", "-mmt"]
    rc = run_7z_with_progress(cmd, log_callback, label, timeout_sec=1800)

    if rc != 0:
        remove_dst(tmp_dir)
        return True

    if os.path.exists(dst_dir):
        remove_dst(dst_dir)
    try:
        os.replace(tmp_dir, dst_dir)
    except OSError as e:
        log_callback(f"[!] [{label}] Rename fail: {e}")
        remove_dst(tmp_dir)
        return True

    try:
        fc = sum(len(f) for _, _, f in os.walk(dst_dir))
        log_callback(f"[✔] [{label}] Extracted {fc} files")
    except OSError:
        pass
    return True


# ============================================================
# PYTHON FALLBACK (zipfile STORED — fast)
# ============================================================
def archive_via_python(
    src_dir: str,
    archive_path: str,
    log_callback: Callable[[str], None],
    label: str = "Cache save",
) -> bool:
    try:
        parent = os.path.dirname(archive_path) or "."
        os.makedirs(parent, exist_ok=True)
        usage = shutil.disk_usage(parent)
        free_pct = usage.free * 100 / usage.total
        if free_pct < _DISK_MIN_WRITE_PCT:
            return False
    except OSError:
        pass

    all_files: list[tuple[str, str]] = []
    try:
        for root, _dirs, files in os.walk(src_dir):
            for f in files:
                abs_p = os.path.join(root, f)
                rel_p = os.path.relpath(abs_p, src_dir)
                all_files.append((abs_p, rel_p))
    except OSError as e:
        log_callback(f"[!] [{label}] Walk fail: {e}")
        return False

    total = len(all_files)
    if total == 0:
        return False

    log_callback(
        f"[*] [{label}] Python zip STORED {total} files → "
        f"{os.path.basename(archive_path)}"
    )

    try:
        if os.path.exists(archive_path):
            os.remove(archive_path)
    except OSError:
        pass

    tmp_path = archive_path + ".tmp"
    start = time.monotonic()
    prog = Progress(total, label=label, log_callback=log_callback,
                    step_pct=10)
    success = False
    try:
        with zipfile.ZipFile(
            tmp_path, "w",
            compression=zipfile.ZIP_STORED,
            allowZip64=True,
        ) as zf:
            for abs_p, rel_p in all_files:
                try:
                    zf.write(abs_p, rel_p)
                except (OSError, zipfile.BadZipFile) as e:
                    logger.debug("Zip skip %s: %s", rel_p, e)
                prog.update()
        os.replace(tmp_path, archive_path)
        success = True
    except Exception as e:
        log_callback(f"[!] [{label}] Zip fail: {e}")
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
    finally:
        prog.close()

    if success:
        elapsed = time.monotonic() - start
        log_callback(f"[✔] [{label}] Python zipped in {elapsed:.1f}s")
    return success


def extract_via_python(
    archive_path: str,
    dst_dir: str,
    log_callback: Callable[[str], None],
    label: str = "Cache load",
) -> bool:
    if not os.path.exists(archive_path):
        return False

    from core.fs_utils import remove_dst
    try:
        if os.path.exists(dst_dir):
            remove_dst(dst_dir)
        parent = os.path.dirname(dst_dir) or "."
        os.makedirs(parent, exist_ok=True)
    except OSError as e:
        log_callback(f"[!] [{label}] prep fail: {e}")
        return False

    tmp_dir = dst_dir + ".tmp"
    remove_dst(tmp_dir)
    try:
        os.makedirs(tmp_dir, exist_ok=True)
    except OSError as e:
        log_callback(f"[!] [{label}] mkdir tmp fail: {e}")
        return False

    start = time.monotonic()
    success = False
    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            names = zf.namelist()
            prog = Progress(
                len(names), label=label,
                log_callback=log_callback, step_pct=10,
            )
            try:
                for name in names:
                    try:
                        zf.extract(name, tmp_dir)
                    except (OSError, zipfile.BadZipFile) as e:
                        logger.debug("Unzip skip %s: %s", name, e)
                    prog.update()
            finally:
                prog.close()

        if os.path.exists(dst_dir):
            remove_dst(dst_dir)
        os.replace(tmp_dir, dst_dir)
        success = True
    except (zipfile.BadZipFile, OSError) as e:
        log_callback(f"[!] [{label}] Unzip fail: {e}")
        remove_dst(tmp_dir)

    if success:
        elapsed = time.monotonic() - start
        log_callback(f"[✔] [{label}] Python unzipped in {elapsed:.1f}s")
    return success


# Backward compat aliases
_find_7zip = find_7zip
_run_7z_with_progress = run_7z_with_progress
_archive_via_7z = archive_via_7z
_extract_via_7z = extract_via_7z
_archive_via_python = archive_via_python
_extract_via_python = extract_via_python