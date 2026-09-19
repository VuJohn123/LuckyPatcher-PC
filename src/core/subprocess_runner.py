"""
Subprocess runner cho Java tools (apktool, apksigner, ...).

v3 (2026):
  - Thêm progress parser cho apktool (parse stdout để đếm dex done).
  - Optional `progress_total` để hiển thị `[N/M]`.
  - Streaming, heartbeat, intelligent watchdog giữ nguyên.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)

_STALL_SILENT_SEC = 300
_STALL_IDLE_CPU_PCT = 2.0
_STALL_IDLE_SEC = 180
_HEARTBEAT_QUIET_SEC = 30

# Apktool output patterns
_APKTOOL_DEX_RE = re.compile(
    r"Smaling\s+(\S+)\s+folder\s+into\s+(\S+\.dex)",
    re.IGNORECASE,
)
_APKTOOL_BUILD_RE = re.compile(r"Building\s+apk\s+file", re.IGNORECASE)
_APKTOOL_ASSETS_RE = re.compile(r"Importing\s+assets", re.IGNORECASE)
_APKTOOL_LIB_RE = re.compile(r"Importing\s+lib", re.IGNORECASE)
_APKTOOL_BUILT_RE = re.compile(r"Built\s+apk\s+into:", re.IGNORECASE)


def _get_tree_cpu_seconds(pid: int) -> float:
    """Tổng CPU time (user+system) của process + descendants."""
    try:
        import psutil
    except ImportError:
        return 0.0
    total = 0.0
    try:
        proc = psutil.Process(pid)
    except Exception:
        return 0.0
    try:
        procs = [proc]
        try:
            procs.extend(proc.children(recursive=True))
        except Exception:
            pass
        for p in procs:
            try:
                ct = p.cpu_times()
                total += ct.user + ct.system
            except Exception:
                pass
    except Exception:
        pass
    return total


def _parse_apktool_progress(
    line: str, state: dict, total_dex: int | None,
) -> str | None:
    """
    Parse 1 dòng apktool output, update `state`, trả về progress message.

    Return None nếu không phải progress line.
    """
    m = _APKTOOL_DEX_RE.search(line)
    if m:
        state["dex_done"] = state.get("dex_done", 0) + 1
        n = state["dex_done"]
        if total_dex and total_dex > 0:
            pct = int(n / total_dex * 100)
            return (
                f"[Apktool] {pct}% ({n}/{total_dex} dex) "
                f"→ {m.group(2)}"
            )
        return f"[Apktool] dex #{n} → {m.group(2)}"

    if _APKTOOL_BUILD_RE.search(line):
        return "[Apktool] Building APK..."
    if _APKTOOL_ASSETS_RE.search(line):
        return "[Apktool] Importing assets..."
    if _APKTOOL_LIB_RE.search(line):
        return "[Apktool] Importing native libs..."
    if _APKTOOL_BUILT_RE.search(line):
        return "[Apktool] ✓ Built"
    return None


def run_java_with_heartbeat(
    cmd: list[str],
    log_callback: Callable[[str], None],
    label: str,
    timeout_sec: int = 1800,
    heartbeat_sec: int = 30,
    stall_timeout_sec: int = _STALL_SILENT_SEC,
    idle_seconds: int = _STALL_IDLE_SEC,
    idle_cpu_pct: float = _STALL_IDLE_CPU_PCT,
    progress_total: int | None = None,
    parse_progress: bool = False,
) -> tuple[int, str]:
    """
    Chạy Java subprocess với streaming + heartbeat + watchdog.

    Args:
        progress_total: nếu set, hiển thị progress `[N/M]` cho apktool
        parse_progress: nếu True, parse apktool stdout thành progress msg
    """
    start = time.monotonic()
    log_callback(f"[*] [{label}] Starting...")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as e:
        log_callback(f"[!] [{label}] Không chạy được: {e}")
        return -1, ""

    stop_hb = threading.Event()
    output_lines: list[str] = []
    killed = {"flag": False, "reason": ""}
    last_output = {"ts": time.monotonic()}
    last_active = {"ts": time.monotonic()}
    last_cpu = {
        "value": _get_tree_cpu_seconds(proc.pid),
        "ts": time.monotonic(),
    }
    cpu_count = os.cpu_count() or 1
    progress_state: dict = {"dex_done": 0}

    def _heartbeat():
        while not stop_hb.wait(heartbeat_sec):
            elapsed = time.monotonic() - start
            silent = time.monotonic() - last_output["ts"]
            idle = time.monotonic() - last_active["ts"]

            if elapsed > timeout_sec:
                log_callback(f"[!] [{label}] Timeout {timeout_sec}s — kill")
                killed["flag"] = True
                killed["reason"] = "timeout"
                try:
                    proc.kill()
                except OSError:
                    pass
                return

            now = time.monotonic()
            cur = _get_tree_cpu_seconds(proc.pid)
            dt = now - last_cpu["ts"]
            d_cpu = cur - last_cpu["value"]
            last_cpu["value"] = cur
            last_cpu["ts"] = now
            cpu_pct = (d_cpu / dt / cpu_count * 100) if dt > 0.1 else 0.0

            if cpu_pct >= idle_cpu_pct:
                last_active["ts"] = now
                idle = 0.0

            if silent >= stall_timeout_sec and idle >= idle_seconds:
                log_callback(
                    f"[!] [{label}] STALL: silent {silent:.0f}s + "
                    f"idle {idle:.0f}s (cpu {cpu_pct:.1f}%) — kill"
                )
                killed["flag"] = True
                killed["reason"] = "stall-idle"
                try:
                    proc.kill()
                except OSError:
                    pass
                return

            if silent >= _HEARTBEAT_QUIET_SEC:
                # Nếu có progress data → show progress thay vì silent
                if parse_progress and progress_state.get("dex_done", 0) > 0:
                    n = progress_state["dex_done"]
                    if progress_total:
                        pct = int(n / progress_total * 100)
                        log_callback(
                            f"[i] [{label}] {pct}% ({n}/{progress_total} dex) "
                            f"cpu {cpu_pct:.0f}%, silent {silent:.0f}s"
                        )
                    else:
                        log_callback(
                            f"[i] [{label}] {n} dex done, "
                            f"cpu {cpu_pct:.0f}%, silent {silent:.0f}s"
                        )
                else:
                    log_callback(
                        f"[i] [{label}] {elapsed:.0f}s "
                        f"(cpu {cpu_pct:.0f}%, silent {silent:.0f}s)"
                    )

    def _stream():
        try:
            if proc.stdout:
                for line in proc.stdout:
                    s = line.rstrip()
                    if not s:
                        continue
                    last_output["ts"] = time.monotonic()
                    last_active["ts"] = time.monotonic()
                    output_lines.append(s)
                    if len(output_lines) > 300:
                        output_lines.pop(0)

                    # Progress parsing
                    if parse_progress:
                        msg = _parse_apktool_progress(
                            s, progress_state, progress_total,
                        )
                        if msg:
                            log_callback(msg)
                            continue

                    # Raw log
                    log_callback(f"    {s}")
        except Exception:
            pass

    hb_thread = threading.Thread(target=_heartbeat, daemon=True)
    stream_thread = threading.Thread(target=_stream, daemon=True)
    hb_thread.start()
    stream_thread.start()

    try:
        rc = proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        killed["flag"] = True
        killed["reason"] = "timeout"
        try:
            proc.kill()
        except OSError:
            pass
        rc = -1

    stop_hb.set()
    stream_thread.join(timeout=3)

    elapsed = time.monotonic() - start
    if killed["flag"]:
        log_callback(
            f"[!] [{label}] Killed ({killed['reason']}) sau {elapsed:.1f}s"
        )
        return -1, "\n".join(output_lines)

    log_callback(f"[✔] [{label}] Xong trong {elapsed:.1f}s (rc={rc})")
    return rc, "\n".join(output_lines)


_run_java_with_heartbeat = run_java_with_heartbeat