"""
Safety guard — bảo vệ hệ thống khỏi bị treo do overcommit.
Chạy periodic trong pipeline (thread riêng).
"""
from __future__ import annotations

import logging
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
    check_interval_sec: float = 3.0


class SafetyGuard:
    """
    Monitor system, trigger callback khi vượt ngưỡng.
    Callback có thể giảm workers, pause, hoặc abort.
    """

    def __init__(
        self,
        limits: GuardLimits | None = None,
        on_violation: Callable[[str, dict], None] | None = None,
        log_callback=print,
    ):
        self.limits = limits or GuardLimits()
        self.on_violation = on_violation
        self.log = log_callback
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_trigger: dict[str, float] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True
        )
        self._thread.start()
        self.log("[*] [SafetyGuard] Started")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.log("[*] [SafetyGuard] Stopped")

    def _run(self) -> None:
        try:
            import psutil
        except ImportError:
            self.log("[i] [SafetyGuard] psutil không có — tắt")
            return

        while not self._stop.is_set():
            try:
                self._check(psutil)
            except Exception as e:
                logger.debug("Guard check failed: %s", e)
            self._stop.wait(self.limits.check_interval_sec)

    def _check(self, psutil) -> None:
        # RAM
        vm = psutil.virtual_memory()
        if vm.percent > self.limits.max_ram_pct:
            self._trigger("ram", {
                "used_pct": vm.percent,
                "threshold": self.limits.max_ram_pct,
                "available_mb": vm.available // 1024 // 1024,
            })

        # CPU
        cpu = psutil.cpu_percent(interval=None)
        if cpu > self.limits.max_cpu_pct:
            self._trigger("cpu", {
                "used_pct": cpu,
                "threshold": self.limits.max_cpu_pct,
            })

        # Disk
        from pathlib import Path
        import shutil
        root = Path(__file__).resolve().parent.parent
        usage = shutil.disk_usage(root)
        free_pct = usage.free * 100 / usage.total
        if free_pct < self.limits.min_disk_free_pct:
            self._trigger("disk", {
                "free_pct": free_pct,
                "threshold": self.limits.min_disk_free_pct,
            })

        # Temp
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for name in ("coretemp", "k10temp", "cpu_thermal"):
                    if name in temps and temps[name]:
                        t = temps[name][0].current
                        if t > self.limits.max_temp_celsius:
                            self._trigger("temp", {
                                "celsius": t,
                                "threshold": self.limits.max_temp_celsius,
                            })
                        break
        except (AttributeError, NotImplementedError):
            pass

    def _trigger(self, reason: str, details: dict) -> None:
        # Debounce: 1 lần / 30s cho mỗi loại
        now = time.monotonic()
        last = self._last_trigger.get(reason, 0)
        if (now - last) < 30.0:
            return
        self._last_trigger[reason] = now

        self.log(
            f"[!] [SafetyGuard] {reason.upper()} violation: {details}"
        )
        if self.on_violation:
            try:
                self.on_violation(reason, details)
            except Exception as e:
                logger.exception("Guard callback failed: %s", e)