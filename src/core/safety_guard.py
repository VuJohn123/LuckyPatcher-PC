"""
Safety guard — bảo vệ hệ thống khỏi bị treo do overcommit.

Đo CPU **ngoại lai** (system - own process tree) bằng `cpu_times()` delta.
Own process tree = Python process + descendants + external tool processes
(apktool.jar, apksigner, ...) — kể cả khi chạy qua nailgun daemon.

Violation counter = CONSECUTIVE. Chỉ reset sau `reset_after_ok_checks`
lần check OK liên tiếp (mặc định 3) — chống counter reset do dao động
ngắn của system load trên Windows.

CLI mode (không có GUI): sau N vi phạm → fallback theo `cli_mode_action`:
  - "mute"     : mute reason, dùng full resources (mặc định, tốt cho CLI)
  - "continue" : nâng ngưỡng + reset counter
  - "abort"    : dừng pipeline

GUI mode: emit prompt dialog như cũ.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)

# Các keyword nhận diện external tool process (kể cả nailgun daemon).
_TOOL_KEYWORDS = (
    "apktool.jar",
    "apksigner.jar",
    "uber-apk-signer.jar",
    "baksmali.jar",
    "smali.jar",
    "bundletool.jar",
    "GDA.exe",
)


@dataclass
class GuardLimits:
    max_ram_pct: float = 85.0
    max_cpu_pct: float = 98.0
    min_disk_free_pct: float = 10.0
    max_temp_celsius: float = 85.0
    check_interval_sec: float = 5.0
    cpu_measurement: str = "external"   # "system" | "external"

    # --- Mới ---
    enabled: bool = True
    reset_after_ok_checks: int = 3
    cli_mode_action: str = "mute"       # "mute" | "continue" | "abort"


class SafetyGuard:
    """
    Monitor system, trigger callback khi vượt ngưỡng.

    Lifecycle:
        guard = SafetyGuard(limits, on_violation, on_prompt, on_mute, N)
        guard.start()
        ...
        if guard.abort_flag:
            raise RuntimeError("Pipeline aborted by user")
        ...
        guard.stop()
    """

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

        # Counter cho vi phạm LIÊN TIẾP
        self._consecutive: dict[str, int] = {}
        # Đếm số lần check OK liên tiếp (để reset counter)
        self._ok_streak: dict[str, int] = {}
        # Đang chờ user prompt (tránh spam)
        self._prompting: set[str] = set()
        # Reason đã được mute → bỏ qua hoàn toàn
        self._muted: set[str] = set()

        self.abort_flag = False
        self._abort_lock = threading.Lock()

        # CPU tracking
        self._own_pid = os.getpid()
        self._own_process = None
        self._cpu_count = 1
        self._last_cpu_time: float | None = None
        self._last_cpu_ts: float = 0.0

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

    # ============================================================
    # COUNTER — CONSECUTIVE OK / VIOLATION
    # ============================================================
    def _record_ok(self, reason: str) -> None:
        """OK check: tăng OK streak. Reset counter sau N OK liên tiếp."""
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
    # OWN TREE CPU — own + descendants + external tool processes
    # ============================================================
    def _get_own_tree_cpu_time(self, psutil) -> float:
        """
        Tổng cpu_times (user+system) của:
          - own process + descendants
          - external tool processes (apktool/apksigner/...) không phải con
            (do nailgun daemon, hoặc spawn qua shell)
        Dedup theo PID để không double-count.
        """
        if self._own_process is None:
            return 0.0

        total = 0.0
        pids_seen: set[int] = set()

        # --- Own tree ---
        try:
            procs = [self._own_process]
            try:
                procs.extend(self._own_process.children(recursive=True))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            for p in procs:
                try:
                    pids_seen.add(p.pid)
                    ct = p.cpu_times()
                    total += ct.user + ct.system
                except (psutil.NoSuchProcess, psutil.AccessDenied,
                        ValueError):
                    pass
        except Exception:
            pass

        # --- External tool processes (nailgun, detached spawn) ---
        try:
            for p in psutil.process_iter(["pid", "cmdline"]):
                try:
                    pid = p.info.get("pid")
                    if pid is None or pid in pids_seen:
                        continue
                    cmdline = " ".join(p.info.get("cmdline") or [])
                    if not cmdline:
                        continue
                    if any(k in cmdline for k in _TOOL_KEYWORDS):
                        ct = p.cpu_times()
                        total += ct.user + ct.system
                        pids_seen.add(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied,
                        ValueError, KeyError):
                    continue
        except Exception:
            pass

        return total

    def _measure_own_tree_cpu(self, psutil) -> float:
        """CPU% của own tree từ cpu_times delta (normalize theo cpu_count)."""
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

        # Vừa vi phạm → reset OK streak
        self._ok_streak[reason] = 0

        count = self._consecutive.get(reason, 0) + 1
        self._consecutive[reason] = count

        # Log gọn — không spam chi tiết
        if count == 1:
            self.log(f"[!] [SafetyGuard] {reason.upper()} #{count}: {details}")
        else:
            self.log(f"[!] [SafetyGuard] {reason.upper()} #{count}")

        # ---------- Đã đủ N vi phạm liên tiếp ----------
        if count >= self.prompt_after_n:
            if self.on_prompt is not None:
                self._prompt_gui(reason, details, count)
            else:
                self._cli_fallback(reason, details, count)
            return

        # ---------- Chưa đủ N → throttle (chỉ callback lần đầu để tránh spam) ----------
        if self.on_violation and count == 1:
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
            # Unknown action → mute as safe default
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