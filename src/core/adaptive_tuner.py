"""
Adaptive tuner — điều chỉnh config theo 4 tầng:
  1. Static: hardware spec
  2. Workload: APK đang xử lý
  3. Runtime: RAM/CPU/disk hiện tại
  4. History: telemetry từ past runs

Chạy trước pipeline, và có thể re-tune giữa chừng nếu throttle.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TuneMode(str, Enum):
    DAILY = "daily"
    GAMING = "gaming"
    STRESS = "stress"
    BACKGROUND = "background"
    POWER_SAVER = "power_saver"


@dataclass
class RuntimeState:
    """Snapshot runtime state — refresh mỗi 5s."""
    ram_used_pct: float
    ram_available_mb: int
    cpu_used_pct: float
    disk_free_pct: float
    cpu_temp_celsius: float | None
    is_ac_power: bool
    timestamp: float


@dataclass
class TuneResult:
    """Kết quả tuning — log lại để debug."""
    mode: TuneMode
    apktool_jobs: int
    apktool_memory: str
    worker_processes: int
    fast_mode: bool
    use_gda: bool
    cache_enabled: bool
    ui_log_visible: bool
    reasoning: list[str] = field(default_factory=list)


# ============================================================
# MAIN TUNER
# ============================================================
class AdaptiveTuner:
    """Singleton — stateful across runs."""

    _instance: "AdaptiveTuner | None" = None
    _lock = threading.RLock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._runtime: RuntimeState | None = None
        self._runtime_ts = 0.0
        self._runtime_ttl = 5.0
        self._lock = threading.RLock()

    # ============================================================
    # TUNE
    # ============================================================
    def tune(
        self,
        config: dict,
        workload=None,               # WorkloadProfile | None
        mode: str | TuneMode = "auto",
    ) -> TuneResult:
        """
        Main entry. Áp dụng tuning vào config và trả về TuneResult.
        """
        from core.env_probe import probe as probe_env

        env = probe_env()
        runtime = self._get_runtime()
        tune_mode = self._resolve_mode(mode, workload, runtime)

        reasoning: list[str] = []
        reasoning.append(f"Mode: {tune_mode.value}")

        # ---- 1. apktool_jobs ----
        jobs = self._tune_jobs(env, workload, runtime, tune_mode, reasoning)

        # ---- 2. apktool_memory ----
        memory = self._tune_memory(
            env, workload, runtime, tune_mode, reasoning
        )

        # ---- 3. worker_processes ----
        workers = self._tune_workers(
            env, workload, runtime, tune_mode, reasoning
        )

        # ---- 4. fast_mode ----
        fast = self._tune_fast_mode(
            workload, tune_mode, reasoning
        )

        # ---- 5. use_gda ----
        use_gda = self._tune_gda(workload, tune_mode, reasoning)

        # ---- 6. cache ----
        cache_enabled = self._tune_cache(
            runtime, tune_mode, reasoning
        )

        # ---- 7. ui.log_visible ----
        log_visible = self._tune_log_visible(
            tune_mode, workload, reasoning
        )

        # ---- Apply ----
        config.setdefault("pipeline", {})["apktool_jobs"] = jobs
        config.setdefault("pipeline", {})["apktool_memory"] = memory
        config.setdefault("pipeline", {})["fast_mode"] = fast
        config.setdefault("pipeline", {})["use_gda"] = use_gda
        config.setdefault("performance", {})["worker_processes"] = workers
        config.setdefault("cache", {})["enabled"] = cache_enabled
        config.setdefault("ui", {})["log_visible"] = log_visible

        result = TuneResult(
            mode=tune_mode,
            apktool_jobs=jobs,
            apktool_memory=memory,
            worker_processes=workers,
            fast_mode=fast,
            use_gda=use_gda,
            cache_enabled=cache_enabled,
            ui_log_visible=log_visible,
            reasoning=reasoning,
        )

        logger.info(
            "Tuned: mode=%s jobs=%d mem=%s workers=%d",
            tune_mode.value, jobs, memory, workers,
        )
        for r in reasoning[1:]:
            logger.debug("  → %s", r)
        return result

    # ============================================================
    # MODE RESOLUTION
    # ============================================================
    def _resolve_mode(
        self, mode, workload, runtime: RuntimeState
    ) -> TuneMode:
        if isinstance(mode, TuneMode):
            return mode
        if isinstance(mode, str) and mode.lower() in [m.value for m in TuneMode]:
            return TuneMode(mode.lower())

        # auto-detect
        # Power saver nếu đang dùng pin
        if not runtime.is_ac_power:
            return TuneMode.POWER_SAVER

        # Stress nếu CPU/RAM đang cao
        if runtime.cpu_used_pct > 85 or runtime.ram_used_pct > 85:
            return TuneMode.STRESS

        # Workload-based
        if workload is not None:
            from core.workload_profiler import SizeClass, WorkloadType
            if workload.size_class in (
                SizeClass.HUGE, SizeClass.MASSIVE
            ):
                return TuneMode.GAMING  # careful strategy
            if workload.workload_type in (
                WorkloadType.UNITY_GAME, WorkloadType.NATIVE_GAME
            ):
                return TuneMode.GAMING

        return TuneMode.DAILY

    # ============================================================
    # TUNE JOBS
    # ============================================================
    def _tune_jobs(
        self, env, workload, runtime: RuntimeState,
        mode: TuneMode, reasoning: list[str],
    ) -> int:
        # Base: min(cpu-1, 8)
        base = max(1, min(env.cpu_count - 1, 8))
        reasoning.append(f"Base jobs = {base} (cpu-1, cap 8)")

        # Mode modifiers
        multiplier = {
            TuneMode.DAILY: 1.0,
            TuneMode.GAMING: 1.25,
            TuneMode.STRESS: 1.5,
            TuneMode.BACKGROUND: 0.5,
            TuneMode.POWER_SAVER: 0.5,
        }.get(mode, 1.0)

        jobs = max(1, int(base * multiplier))
        reasoning.append(f"Mode {mode.value} × {multiplier} = {jobs}")

        # Runtime throttle
        if runtime.cpu_used_pct > 90:
            jobs = max(1, jobs // 2)
            reasoning.append("CPU > 90% → halved")
        if runtime.ram_used_pct > 85:
            jobs = max(1, jobs // 2)
            reasoning.append("RAM > 85% → halved")

        # Workload adjustment
        if workload is not None:
            from core.workload_profiler import SizeClass
            if workload.size_class in (
                SizeClass.HUGE, SizeClass.MASSIVE
            ):
                # Giảm jobs cho APK lớn để tránh I/O thrash
                jobs = max(1, min(jobs, 4))
                reasoning.append(
                    f"Workload {workload.size_class.value} → cap 4 jobs"
                )

        return max(1, min(jobs, env.cpu_count))


    # ============================================================
    # TUNE MEMORY
    # ============================================================
    def _tune_memory(
        self, env, workload, runtime: RuntimeState,
        mode: TuneMode, reasoning: list[str],
    ) -> str:
        # RAM khả dụng cho pipeline
        # Reserve 25% cho OS, hoặc theo mode
        reserve_pct = {
            TuneMode.DAILY: 25,
            TuneMode.GAMING: 20,
            TuneMode.STRESS: 15,
            TuneMode.BACKGROUND: 40,
            TuneMode.POWER_SAVER: 40,
        }.get(mode, 25)

        reserve_mb = max(1024, env.ram_total_mb * reserve_pct // 100)
        available = max(0, env.ram_available_mb - reserve_mb)
        reasoning.append(
            f"RAM avail {env.ram_available_mb}MB - reserve {reserve_mb}MB "
            f"= {available}MB usable"
        )

        # Nếu có workload profile → reserve cho peak RAM
        if workload is not None:
            predicted = workload.est_peak_ram_mb
            available = min(available, env.ram_available_mb - predicted - reserve_mb)
            reasoning.append(
                f"Workload predicts {predicted:.0f}MB peak → "
                f"{available:.0f}MB for Java heap"
            )

        # Java heap ~ 60% available
        heap_mb = max(1024, int(available * 0.6))

        # Cap
        heap_mb = min(heap_mb, 8192)
        heap_mb = max(heap_mb, 1024)

        reasoning.append(f"Java heap = {heap_mb}m")
        return f"{heap_mb}m"


    # ============================================================
    # TUNE WORKERS
    # ============================================================
    def _tune_workers(
        self, env, workload, runtime: RuntimeState,
        mode: TuneMode, reasoning: list[str],
    ) -> int:
        base = max(1, min(env.cpu_count_physical, 4))

        multiplier = {
            TuneMode.DAILY: 1,
            TuneMode.GAMING: 1,
            TuneMode.STRESS: 2,
            TuneMode.BACKGROUND: 1,
            TuneMode.POWER_SAVER: 1,
        }.get(mode, 1)

        workers = base * multiplier

        # Throttle nếu RAM thấp
        if runtime.ram_available_mb < 2048:
            workers = 1
            reasoning.append("RAM < 2GB → 1 worker")
        elif runtime.ram_available_mb < 4096:
            workers = min(workers, 2)
            reasoning.append("RAM < 4GB → cap 2 workers")

        workers = max(1, min(workers, env.cpu_count_physical))
        reasoning.append(f"Workers = {workers}")
        return workers


    # ============================================================
    # TUNE FAST MODE
    # ============================================================
    def _tune_fast_mode(
        self, workload, mode: TuneMode, reasoning: list[str]
    ) -> bool:
        # Fast mode bỏ qua classes2,3 → miss IAP/license ở dex phụ
        # Chỉ dùng khi: stress/gaming AND workload lớn
        if mode in (TuneMode.STRESS, TuneMode.GAMING):
            if workload is None:
                reasoning.append("Gaming/stress → fast_mode=True")
                return True
            from core.workload_profiler import SizeClass
            if workload.size_class in (
                SizeClass.LARGE, SizeClass.HUGE, SizeClass.MASSIVE
            ):
                reasoning.append(
                    f"Workload {workload.size_class.value} + "
                    f"mode {mode.value} → fast_mode=True"
                )
                return True

        # Daily → không fast mode để đảm bảo coverage
        reasoning.append(f"Mode {mode.value} → fast_mode=False")
        return False


    # ============================================================
    # TUNE GDA
    # ============================================================
    def _tune_gda(
        self, workload, mode: TuneMode, reasoning: list[str]
    ) -> bool:
        # GDA chậm ~10-30s nhưng chính xác hơn
        # Chỉ dùng khi: daily/balanced AND workload nhỏ/vừa
        if mode == TuneMode.DAILY:
            if workload is None:
                return False
            from core.workload_profiler import SizeClass
            if workload.size_class in (SizeClass.TINY, SizeClass.SMALL):
                reasoning.append("Small workload + daily → GDA on")
                return True
        reasoning.append(f"Mode {mode.value} → GDA off")
        return False


    # ============================================================
    # TUNE CACHE
    # ============================================================
    def _tune_cache(
        self, runtime: RuntimeState, mode: TuneMode,
        reasoning: list[str],
    ) -> bool:
        # Tắt cache khi disk gần đầy
        if runtime.disk_free_pct < 10:
            reasoning.append("Disk < 10% → cache off")
            return False

        # Stress mode: tắt cache để tránh I/O contention
        if mode == TuneMode.STRESS and runtime.disk_free_pct < 20:
            reasoning.append("Stress + disk < 20% → cache off")
            return False

        reasoning.append("Cache enabled")
        return True


    # ============================================================
    # TUNE LOG VISIBLE
    # ============================================================
    def _tune_log_visible(
        self, mode: TuneMode, workload, reasoning: list[str]
    ) -> bool:
        # Stress mode: ẩn log để giảm UI overhead
        if mode == TuneMode.STRESS:
            reasoning.append("Stress → log hidden")
            return False
        if mode == TuneMode.BACKGROUND:
            reasoning.append("Background → log hidden")
            return False
        return True


    # ============================================================
    # RUNTIME STATE
    # ============================================================
    def _get_runtime(self, force: bool = False) -> RuntimeState:
        with self._lock:
            now = time.monotonic()
            if not force and self._runtime and (
                now - self._runtime_ts
            ) < self._runtime_ttl:
                return self._runtime

            self._runtime = self._probe_runtime()
            self._runtime_ts = now
            return self._runtime

    def _probe_runtime(self) -> RuntimeState:
        """Đọc CPU/RAM/disk state hiện tại."""
        ram_used_pct = 50.0
        ram_avail_mb = 4096
        cpu_used_pct = 20.0
        cpu_temp = None
        is_ac = True

        try:
            import psutil
            vm = psutil.virtual_memory()
            ram_used_pct = vm.percent
            ram_avail_mb = int(vm.available / 1024 / 1024)

            # CPU: đo trong 0.1s
            cpu_used_pct = psutil.cpu_percent(interval=0.1)

            # Battery
            try:
                battery = psutil.sensors_battery()
                if battery:
                    is_ac = battery.power_plugged
            except (AttributeError, NotImplementedError):
                pass

            # Thermal (chỉ Linux)
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    for name in ("coretemp", "k10temp", "cpu_thermal"):
                        if name in temps and temps[name]:
                            cpu_temp = temps[name][0].current
                            break
            except (AttributeError, NotImplementedError):
                pass

        except ImportError:
            pass  # Fallback defaults

        # Disk
        try:
            from pathlib import Path
            root = Path(__file__).resolve().parent.parent
            import shutil
            usage = shutil.disk_usage(root)
            disk_free_pct = usage.free * 100 / usage.total
        except Exception:
            disk_free_pct = 50.0

        return RuntimeState(
            ram_used_pct=ram_used_pct,
            ram_available_mb=ram_avail_mb,
            cpu_used_pct=cpu_used_pct,
            disk_free_pct=disk_free_pct,
            cpu_temp_celsius=cpu_temp,
            is_ac_power=is_ac,
            timestamp=time.monotonic(),
        )


# ============================================================
# SINGLETON HELPER
# ============================================================
def get_tuner() -> AdaptiveTuner:
    return AdaptiveTuner()