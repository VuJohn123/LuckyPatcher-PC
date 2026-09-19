"""
Safety guard — bảo vệ hệ thống khỏi bị treo do overcommit.

Đo CPU **ngoại lai** (system - own process tree) bằng `cpu_times()` delta.
Own process tree = Python process + descendants + nailgun daemon tree
+ external tool processes (detected via cmdline keyword OR new-java heuristic).

Violation counter = CONSECUTIVE. Chỉ reset sau `reset_after_ok_checks`
lần check OK liên tiếp.

Grace: violation #1 KHÔNG throttle — tránh false positive do burst ngắn.

CLI mode: sau N vi phạm → fallback theo `cli_mode_action` (mute/continue/abort).

v2 fixes (own_pct bug):
  - Baseline PID tracking → detect NEW java processes spawned after start.
  - Keyword matching case-insensitive, không yêu cầu `.jar` extension.
  - Additional match by process name (java/javaw/apktool).
  - Diagnostic logging khi used_pct cao nhưng own_pct thấp.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)

# Keyword để nhận diện external tool processes.
# KHÔNG yêu cầu `.jar` — hỗ trợ java -jar, apktool.bat, ng client, v.v.
_TOOL_KEYWORDS = (
    "apktool",
    "apksigner",
    "uber-apk-signer",
    "baksmali",
    "smali",
    "bundletool",
    "gda.exe",
    "gda ",
    "nailgun",
    "ng-server",
    "ngserver",
    "ng.exe",
)

# Process name heuristics (lowercase match)
_JAVA_NAMES = frozenset({"java", "javaw", "java.exe", "javaw.exe"})

# Diagnostic log threshold: log chi tiết khi own_pct < ngưỡng này
_DIAG_OWN_PCT_LOW = 2.0
_DIAG_CPU_HIGH = 85.0


@dataclass
class GuardLimits:
    max_ram_pct: float = 85.0
    max_cpu_pct: float = 98.0
    min_disk_free_pct: float = 10.0
    max_temp_celsius: float = 85.0
    check_interval_sec: float = 5.0
    cpu_measurement: str = "external"

    enabled: bool = True
    reset_after_ok_checks: int = 3
    cli_mode_action: str = "mute"


class SafetyGuard:
    _GRACE_N = 2

    def __init__(
        self,
        limits: GuardLimits | None = None,
        on_violation: Callable[[str, dict], None] | None = None,
        on_prompt: Callable[[str, dict, int], bool] | None = None,
        on_mute: Callable[[str], None] | None = None,
        prompt_after_n_violations: int = 5,
        threshold_raise_pct: float = 5.0,
        log_callback=print,
    ):
        self.limits = limits or GuardLimits()
        self.on_violation = on_violation
        self.on_prompt = on_prompt
        self.on_mute = on_mute
        self.prompt_after_n = max(1, prompt_after_n_violations)
        self.threshold_raise_pct = threshold_raise_pct
        self.log = log_callback

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        # Counters
        self._consecutive: dict[str, int] = {}
        self._ok_streak: dict[str, int] = {}
        self._prompting: set[str] = set()
        self._muted: set[str] = set()

        self.abort_flag = False
        self._abort_lock = threading.Lock()

        # CPU tracking
        self._own_pid = os.getpid()
        self._own_process = None
        self._cpu_count = 1
        self._last_cpu_time: float | None = None
        self._last_cpu_ts: float = 0.0

        # v2: baseline PIDs (snapshot at start) — dùng để nhận diện
        # java process MỚI sinh ra sau khi guard start.
        self._baseline_pids: set[int] = set()
        self._baseline_ready = False

        # Diagnostic: tránh log spam
        self._diag_logged = False

    # ============================================================
    # LIFECYCLE
    # ============================================================
    def start(self) -> None:
        if not self.limits.enabled:
            self.log("[i] [SafetyGuard] Disabled via config — skip")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.abort_flag = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.log(
            f"[*] [SafetyGuard] Started "
            f"(cpu>{self.limits.max_cpu_pct}%, ram>{self.limits.max_ram_pct}%, "
            f"disk<{self.limits.min_disk_free_pct}%, "
            f"reset_ok={self.limits.reset_after_ok_checks}, "
            f"cli_action={self.limits.cli_mode_action})"
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.log("[*] [SafetyGuard] Stopped")

    # ============================================================
    # MAIN LOOP
    # ============================================================
    def _run(self) -> None:
        try:
            import psutil
        except ImportError:
            self.log("[i] [SafetyGuard] psutil không có — tắt")
            return

        self._own_process = psutil.Process(self._own_pid)
        self._cpu_count = psutil.cpu_count() or 1

        # v2: snapshot baseline PIDs
        try:
            self._baseline_pids = {
                p.pid for p in psutil.process_iter(["pid"])
                if p.pid != self._own_pid
            }
            self._baseline_ready = True
            logger.debug(
                "Baseline: %d processes at start", len(self._baseline_pids)
            )
        except Exception as e:
            logger.debug("Baseline snapshot failed: %s", e)

        psutil.cpu_percent(interval=None)
        self._last_cpu_time = self._get_own_tree_cpu_time(psutil)
        self._last_cpu_ts = time.monotonic()

        while not self._stop.is_set():
            try:
                if self.abort_flag:
                    self.log("[i] [SafetyGuard] Abort flag — stop monitor")
                    break
                self._check(psutil)
            except Exception as e:
                logger.debug("Guard check failed: %s", e)
            self._stop.wait(self.limits.check_interval_sec)

    def _check(self, psutil) -> None:
        # ---- RAM ----
        try:
            vm = psutil.virtual_memory()
            if vm.percent > self.limits.max_ram_pct:
                self._handle_violation("ram", {
                    "used_pct": round(vm.percent, 1),
                    "threshold": self.limits.max_ram_pct,
                    "available_mb": vm.available // 1024 // 1024,
                })
            else:
                self._record_ok("ram")
        except Exception:
            pass

        # ---- CPU ----
        try:
            if self.limits.cpu_measurement == "external":
                system_cpu = psutil.cpu_percent(interval=None)
                own_cpu = self._measure_own_tree_cpu(psutil)
                external_cpu = max(0.0, system_cpu - own_cpu)
                measured = external_cpu
                extra = {
                    "system_pct": round(system_cpu, 1),
                    "own_pct": round(own_cpu, 1),
                }

                # v2: diagnostic khi hệ thống busy nhưng own tree không detect
                if (system_cpu > _DIAG_CPU_HIGH
                        and own_cpu < _DIAG_OWN_PCT_LOW
                        and not self._diag_logged):
                    self._log_diagnostic(psutil, system_cpu, own_cpu)
                    self._diag_logged = True
            else:
                measured = psutil.cpu_percent(interval=None)
                extra = {}

            if measured > self.limits.max_cpu_pct:
                self._handle_violation("cpu", {
                    "used_pct": round(measured, 1),
                    "threshold": round(self.limits.max_cpu_pct, 1),
                    **extra,
                })
            else:
                self._record_ok("cpu")
        except Exception as e:
            logger.debug("CPU check failed: %s", e)

        # ---- Disk ----
        try:
            from pathlib import Path
            import shutil as _sh
            root = Path(__file__).resolve().parent.parent
            usage = _sh.disk_usage(root)
            free_pct = usage.free * 100 / usage.total
            if free_pct < self.limits.min_disk_free_pct:
                self._handle_violation("disk", {
                    "free_pct": round(free_pct, 1),
                    "threshold": self.limits.min_disk_free_pct,
                })
            else:
                self._record_ok("disk")
        except Exception:
            pass

        # ---- Temp ----
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for name in ("coretemp", "k10temp", "cpu_thermal"):
                    if name in temps and temps[name]:
                        t = temps[name][0].current
                        if t > self.limits.max_temp_celsius:
                            self._handle_violation("temp", {
                                "celsius": round(t, 1),
                                "threshold": self.limits.max_temp_celsius,
                            })
                        else:
                            self._record_ok("temp")
                        break
        except (AttributeError, NotImplementedError):
            pass

    def _log_diagnostic(self, psutil, system_cpu: float, own_cpu: float):
        """Diagnostic: liệt kê java/tool processes để debug own_pct bug."""
        try:
            tool_procs: list[str] = []
            for p in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    name = (p.info.get("name") or "").lower()
                    cmdline = " ".join(p.info.get("cmdline") or [])
                    cl = cmdline.lower()
                    if (name in _JAVA_NAMES
                            or any(k in cl for k in _TOOL_KEYWORDS)
                            or p.pid in self._baseline_pids):
                        continue
                    # Chỉ log process có thể là tool
                    if "java" in name or "apktool" in cl or "nailgun" in cl:
                        tool_procs.append(
                            f"pid={p.pid} name={name} cmd={cmdline[:120]}"
                        )
                        if len(tool_procs) >= 10:
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied,
                        ValueError, KeyError):
                    continue
            if tool_procs:
                self.log(
                    f"[i] [SafetyGuard] DIAG: system={system_cpu:.1f}% "
                    f"own={own_cpu:.1f}% — candidate processes:"
                )
                for tp in tool_procs:
                    self.log(f"[i] [SafetyGuard]   {tp}")
            else:
                self.log(
                    f"[i] [SafetyGuard] DIAG: system={system_cpu:.1f}% "
                    f"own={own_cpu:.1f}% — no java/tool process found "
                    f"(baseline={len(self._baseline_pids)} pids)"
                )
        except Exception as e:
            logger.debug("Diagnostic failed: %s", e)

    # ============================================================
    # COUNTER
    # ============================================================
    def _record_ok(self, reason: str) -> None:
        streak = self._ok_streak.get(reason, 0) + 1
        self._ok_streak[reason] = streak
        if streak >= self.limits.reset_after_ok_checks:
            if self._consecutive.get(reason, 0) > 0:
                logger.debug(
                    "Counter %s reset sau %d OK check", reason, streak
                )
            self._consecutive[reason] = 0
            self._ok_streak[reason] = 0

    # ============================================================
    # OWN TREE CPU — v2 robust detection
    # ============================================================
    def _get_own_tree_cpu_time(self, psutil) -> float:
        """
        Tổng cpu_times (user+system) của:
          1. Own process + descendants (bao gồm apktool child)
          2. Nailgun daemon + descendants (long-lived daemon)
          3. External tool processes:
             - cmdline keyword match (apktool, nailgun, ...)
             - OR process name java/javaw AND pid not in baseline
               (detached java spawned after guard start)
             - OR pid not in baseline AND cmdline có "apktool"/"nailgun"
        Dedup theo PID.
        """
        if self._own_process is None:
            return 0.0

        total = 0.0
        pids_seen: set[int] = set()

        def _acc(p) -> None:
            nonlocal total
            try:
                pid = p.pid
                if pid in pids_seen:
                    return
                ct = p.cpu_times()
                pids_seen.add(pid)
                total += ct.user + ct.system
            except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
                pass

        # ---- 1. Own process tree ----
        try:
            _acc(self._own_process)
            try:
                for child in self._own_process.children(recursive=True):
                    _acc(child)
            except Exception:
                pass
        except Exception:
            pass

        # ---- 2 & 3. Scan all processes ----
        try:
            for p in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    pid = p.pid
                    if pid in pids_seen:
                        continue

                    name = (p.info.get("name") or "").lower()
                    cmdline = " ".join(p.info.get("cmdline") or [])
                    cl = cmdline.lower()

                    matched = False
                    reason = ""

                    # 2a. Nailgun daemon
                    if ("nailgun" in cl or "ng-server" in cl
                            or "ngserver" in cl):
                        matched = True
                        reason = "nailgun"

                    # 2b. Tool keyword match (case-insensitive, no .jar req)
                    elif any(k in cl for k in _TOOL_KEYWORDS):
                        matched = True
                        reason = "keyword"

                    # 2c. NEW java process (không có trong baseline)
                    elif (self._baseline_ready
                          and pid not in self._baseline_pids
                          and (name in _JAVA_NAMES
                               or "java" in name)):
                        matched = True
                        reason = "new-java"

                    if matched:
                        _acc(p)
                        # Include children
                        try:
                            for c in p.children(recursive=True):
                                _acc(c)
                        except Exception:
                            pass
                        logger.debug(
                            "Safety own-tree match: pid=%d name=%s "
                            "reason=%s", pid, name, reason
                        )
                except (psutil.NoSuchProcess, psutil.AccessDenied,
                        ValueError, KeyError):
                    continue
        except Exception:
            pass

        return total

    def _measure_own_tree_cpu(self, psutil) -> float:
        now = time.monotonic()
        current = self._get_own_tree_cpu_time(psutil)

        if self._last_cpu_time is None:
            self._last_cpu_time = current
            self._last_cpu_ts = now
            return 0.0

        delta_cpu = current - self._last_cpu_time
        delta_wall = now - self._last_cpu_ts

        self._last_cpu_time = current
        self._last_cpu_ts = now

        if delta_wall <= 0.001:
            return 0.0

        pct = (delta_cpu / delta_wall / max(1, self._cpu_count)) * 100
        return max(0.0, min(100.0, pct))

    # ============================================================
    # VIOLATION HANDLER
    # ============================================================
    def _handle_violation(self, reason: str, details: dict) -> None:
        if reason in self._muted:
            return
        if reason in self._prompting:
            return

        self._ok_streak[reason] = 0

        count = self._consecutive.get(reason, 0) + 1
        self._consecutive[reason] = count

        if count == 1:
            self.log(f"[!] [SafetyGuard] {reason.upper()} #{count}: {details}")
        else:
            self.log(f"[!] [SafetyGuard] {reason.upper()} #{count}")

        if count >= self.prompt_after_n:
            if self.on_prompt is not None:
                self._prompt_gui(reason, details, count)
            else:
                self._cli_fallback(reason, details, count)
            return

        # Grace: violation #1 không throttle
        if self.on_violation and count == self._GRACE_N:
            try:
                self.on_violation(reason, details)
            except Exception as e:
                logger.warning("on_violation callback failed: %s", e)

    def _prompt_gui(self, reason: str, details: dict, count: int) -> None:
        self._prompting.add(reason)
        self.log(f"[!] [SafetyGuard] {count} vi phạm — hỏi user...")
        try:
            user_continue = self.on_prompt(reason, details, count)
        except Exception as e:
            logger.warning("on_prompt callback failed: %s", e)
            user_continue = True
        finally:
            self._prompting.discard(reason)

        if not user_continue:
            with self._abort_lock:
                self.abort_flag = True
            self.log("[!] [SafetyGuard] User chọn DỪNG → abort_flag=True")
            return

        self._muted.add(reason)
        self._raise_threshold(reason)
        self._consecutive[reason] = 0
        self._ok_streak[reason] = 0
        if self.on_mute:
            try:
                self.on_mute(reason)
            except Exception:
                pass
        self.log(
            f"[i] [SafetyGuard] User continue — mute {reason}, "
            f"ngưỡng mới {self._get_threshold(reason):.1f}%"
        )

    def _cli_fallback(self, reason: str, details: dict, count: int) -> None:
        action = self.limits.cli_mode_action
        if action == "mute":
            self._muted.add(reason)
            self._consecutive[reason] = 0
            self._ok_streak[reason] = 0
            if self.on_mute:
                try:
                    self.on_mute(reason)
                except Exception:
                    pass
            self.log(
                f"[i] [SafetyGuard] CLI mode — auto-MUTE {reason} sau "
                f"{count} vi phạm → dùng full resources. "
                f"(Đổi `auto_tune.safety.cli_mode_action` để thay đổi.)"
            )
        elif action == "abort":
            with self._abort_lock:
                self.abort_flag = True
            self.log(
                f"[!] [SafetyGuard] CLI mode — ABORT sau "
                f"{count} vi phạm"
            )
        elif action == "continue":
            self._raise_threshold(reason)
            self._consecutive[reason] = 0
            self._ok_streak[reason] = 0
            self.log(
                f"[i] [SafetyGuard] CLI mode — nâng ngưỡng {reason} "
                f"→ {self._get_threshold(reason):.1f}%"
            )
        else:
            self._muted.add(reason)
            self.log(
                f"[!] [SafetyGuard] cli_mode_action='{action}' không "
                f"hợp lệ — fallback MUTE {reason}"
            )

    # ============================================================
    # THRESHOLD
    # ============================================================
    def _raise_threshold(self, reason: str) -> None:
        r = self.threshold_raise_pct
        if reason == "cpu":
            self.limits.max_cpu_pct = min(99.0, self.limits.max_cpu_pct + r)
        elif reason == "ram":
            self.limits.max_ram_pct = min(99.0, self.limits.max_ram_pct + r)
        elif reason == "temp":
            self.limits.max_temp_celsius = min(
                100.0, self.limits.max_temp_celsius + r
            )

    def _get_threshold(self, reason: str) -> float:
        return {
            "cpu": self.limits.max_cpu_pct,
            "ram": self.limits.max_ram_pct,
            "temp": self.limits.max_temp_celsius,
            "disk": self.limits.min_disk_free_pct,
        }.get(reason, 0.0)