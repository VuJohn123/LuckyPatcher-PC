"""
Safety guard — bảo vệ hệ thống khỏi bị treo do overcommit.

Đo CPU **ngoại lai** (system - own process tree) bằng `cpu_times()` delta
— cách này không cần prime Process object, chính xác cho process mới spawn.

Sau N vi phạm LIÊN TIẾP → prompt user. 
  - Continue: MUTE reason đó cho hết pipeline (không nag lại)
  - Stop: abort_flag = True → pipeline tự dừng

Mute semantics: User chọn Continue = "tôi biết rủi ro, đừng hỏi lại".
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class GuardLimits:
    max_ram_pct: float = 85.0
    max_cpu_pct: float = 95.0
    min_disk_free_pct: float = 10.0
    max_temp_celsius: float = 85.0
    check_interval_sec: float = 5.0
    cpu_measurement: str = "external"  # "system" | "external"


class SafetyGuard:
    """
    Monitor system, trigger callback khi vượt ngưỡng.

    Lifecycle:
        guard = SafetyGuard(limits, on_violation, on_prompt, N)
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
        prompt_after_n_violations: int = 5,
        threshold_raise_pct: float = 5.0,
        log_callback=print,
    ):
        self.limits = limits or GuardLimits()
        self.on_violation = on_violation
        self.on_prompt = on_prompt
        self.prompt_after_n = max(1, prompt_after_n_violations)
        self.threshold_raise_pct = threshold_raise_pct
        self.log = log_callback

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        # Counter cho vi phạm LIÊN TIẾP (không phải tổng)
        self._consecutive: dict[str, int] = {}
        # Đang chờ user prompt (tránh spam khi đang chờ)
        self._prompting: set[str] = set()
        # Reason đã được user chọn "Continue" → mute cho hết pipeline
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
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.abort_flag = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.log("[*] [SafetyGuard] Started (excl. own process tree)")

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

        # Prime system CPU counter
        psutil.cpu_percent(interval=None)

        # Prime own tree cpu_times baseline
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
                self._consecutive["ram"] = 0
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
                self._consecutive["cpu"] = 0
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
                self._consecutive["disk"] = 0
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
                            self._consecutive["temp"] = 0
                        break
        except (AttributeError, NotImplementedError):
            pass

    # ============================================================
    # OWN TREE CPU — cpu_times delta (reliable for new processes)
    # ============================================================
    def _get_own_tree_cpu_time(self, psutil) -> float:
        """Tổng cpu_times (user+system) của own process + children."""
        if self._own_process is None:
            return 0.0
        total = 0.0
        try:
            procs = [self._own_process]
            try:
                procs.extend(self._own_process.children(recursive=True))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

            for p in procs:
                try:
                    ct = p.cpu_times()
                    total += ct.user + ct.system
                except (psutil.NoSuchProcess, psutil.AccessDenied,
                        ValueError):
                    pass
        except Exception:
            pass
        return total

    def _measure_own_tree_cpu(self, psutil) -> float:
        """
        Đo CPU% của own process tree từ cpu_times delta.

        Công thức:
            cpu_pct = (delta_cpu_sec / delta_wall_sec / cpu_count) * 100

        Chính xác cho process mới spawn — không cần prime
        `Process.cpu_percent()`.
        """
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
        # Đã mute (user chọn Continue) → bỏ qua hoàn toàn
        if reason in self._muted:
            return

        # Đang chờ user prompt → không spam
        if reason in self._prompting:
            return

        count = self._consecutive.get(reason, 0) + 1
        self._consecutive[reason] = count

        self.log(
            f"[!] [SafetyGuard] {reason.upper()} violation #{count}: "
            f"{details}"
        )

        # ---------- Đã đủ N vi phạm liên tiếp → prompt ----------
        if count >= self.prompt_after_n and self.on_prompt is not None:
            self._prompting.add(reason)
            self.log(
                f"[!] [SafetyGuard] {count} vi phạm liên tiếp — hỏi user..."
            )
            try:
                user_continue = self.on_prompt(reason, details, count)
            except Exception as e:
                logger.warning("on_prompt callback failed: %s", e)
                user_continue = True  # fail-safe: continue
            finally:
                self._prompting.discard(reason)

            if not user_continue:
                with self._abort_lock:
                    self.abort_flag = True
                self.log(
                    "[!] [SafetyGuard] User chọn DỪNG → abort_flag=True"
                )
                return

            # === User chọn Continue → MUTE reason này cho hết pipeline ===
            self._muted.add(reason)
            self._raise_threshold(reason)
            self._consecutive[reason] = 0

            # Log chính xác — disk không raise được
            if reason == "disk":
                self.log(
                    f"[i] [SafetyGuard] User continue — "
                    f"bỏ qua cảnh báo {reason} cho phần còn lại "
                    f"(ngưỡng không đổi)"
                )
            else:
                self.log(
                    f"[i] [SafetyGuard] User continue — "
                    f"nâng ngưỡng {reason} lên "
                    f"{self._get_threshold(reason):.1f}% "
                    f"và bỏ qua cảnh báo tiếp theo"
                )
            return

        # ---------- Chưa đủ N → auto-throttle ----------
        if self.on_violation:
            try:
                self.on_violation(reason, details)
            except Exception as e:
                logger.warning("on_violation callback failed: %s", e)

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
        # disk: không nâng (hard limit)

    def _get_threshold(self, reason: str) -> float:
        return {
            "cpu": self.limits.max_cpu_pct,
            "ram": self.limits.max_ram_pct,
            "temp": self.limits.max_temp_celsius,
            "disk": self.limits.min_disk_free_pct,
        }.get(reason, 0.0)