"""
LP-PC Suite — Entry point chính.

Fix G1: enable decompile cache (force=False).
Fix G2: auto-fallback no_res=False khi recompile fail.
Fix G7: watermark SAU file_cache.flush() để không bị ads patch ghi đè.

v2 fixes:
  - SafetyGuard: dùng on_mute callback, hỗ trợ safety.enabled flag
  - --no-safety CLI flag
  - Windows console UTF-8 reconfigure (fix cp1252 UnicodeEncodeError)
  - Silence androguard (loguru) — giảm noise log

v3 fixes:
  - Log App name + Package name (dễ đọc hơn)
  - Output folder theo package name (workspace/output/<pkg>/)
  - Cảnh báo packer không patchable (PairIP, 360, Tencent, ...)

v3.1 fixes (test regression):
  - _sanitize_folder_name: type-check isinstance(str) — fix MagicMock
  - summary.get() trả MagicMock trong test → coerce về str

v3.2 fixes (adaptive integration):
  - Resolve strategy từ workload_classes (fast/balanced/careful/paranoid)
  - Stage-level metrics: decompile / patch / recompile / sign / install
  - _StageTimer context manager

v3.3 fixes (trace_id integration):
  - Correlation ID xuyên pipeline qua contextvars
  - `trace_context()` wrap toàn bộ run_pipeline
  - Metrics + patch_history entries include `trace_id`
  - Thread pool tasks propagate qua `submit_with_context`

v3.4 fixes (output naming + cleanup):
  - Rename final APK → {package}.{Patch1}.{Patch2}.apk
  - Cleanup intermediate files (patched.apk, -aligned-debugSigned.apk)
  - Progress bar cho apktool recompile (parse stdout)
"""
from __future__ import annotations

import argparse
import gc
import logging
import os
import re
import shutil
import sys
import time
import traceback
from pathlib import Path

from core.pipeline_helpers import normalize_input, setup_logging
from core.config import load_config
from core.trace_context import (
    get_trace_id,
    trace_context,
)
from core.output_namer import build_output_filename

logger = logging.getLogger(__name__)


# =============================================================
# UTILITIES: UTF-8 + LOG SILENCE
# =============================================================
def _ensure_utf8_console() -> None:
    """Windows cmd.exe cp1252 → UTF-8."""
    if sys.platform != "win32":
        return
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _silence_androguard() -> None:
    """Silence androguard logs (loguru + stdlib fallback)."""
    if os.environ.get("LP_ANDROGUARD_LOG", "").strip().lower() in (
        "1", "true", "yes", "on"
    ):
        return

    try:
        from loguru import logger as _loguru
        _loguru.disable("androguard")
    except ImportError:
        pass
    except Exception:
        pass

    for name in list(logging.root.manager.loggerDict.keys()):
        if name == "androguard" or name.startswith("androguard."):
            lg = logging.getLogger(name)
            lg.setLevel(logging.CRITICAL)
            lg.propagate = False
            lg.disabled = True

    _ag = logging.getLogger("androguard")
    _ag.setLevel(logging.CRITICAL)
    _ag.propagate = False


def _silence_noisy_libs() -> None:
    for noisy, level in (
        ("urllib3", logging.WARNING),
        ("requests", logging.WARNING),
        ("asyncio", logging.WARNING),
        ("PIL", logging.WARNING),
        ("matplotlib", logging.WARNING),
    ):
        logging.getLogger(noisy).setLevel(level)


def _setup_environment() -> None:
    _ensure_utf8_console()
    _silence_androguard()
    _silence_noisy_libs()


_setup_environment()


# =============================================================
# HELPERS
# =============================================================
_FOLDER_NAME_RE = re.compile(r"[^\w.\-]")


def _sanitize_folder_name(s) -> str:
    """
    Sanitize tên folder. Chỉ chấp nhận str; các type khác (MagicMock
    trong test, None, number) → fallback "unknown".
    """
    if not isinstance(s, str) or not s:
        return "unknown"
    cleaned = _FOLDER_NAME_RE.sub("_", s).strip("._")
    return cleaned[:100] or "unknown"


def _coerce_str(v) -> str:
    """Coerce value về str, non-str → empty."""
    return v if isinstance(v, str) else ""


def _emit_step(signals, name: str, pct: int, log_callback) -> None:
    if signals:
        try:
            signals.step.emit(name, pct)
        except Exception:
            pass
    log_callback(f"[*] [{pct:3d}%] {name}")


def _cleanup_intermediates(
    output_dir: str,
    keep: str,
    log_callback=print,
) -> None:
    """
    Xóa intermediate APK files sau khi sign + rename.

    Intermediates thường gặp:
      - patched.apk                      (apktool output)
      - patched-aligned.apk              (zipalign output)
      - patched-aligned-debugSigned.apk  (uber-apk-signer output)
      - *.apk.tmp                        (partial writes)

    Chỉ giữ lại file trong `keep` (final renamed APK).
    """
    try:
        keep_abs = os.path.abspath(keep)
        removed_count = 0
        for name in os.listdir(output_dir):
            if not (name.endswith(".apk") or name.endswith(".apk.tmp")):
                continue
            full = os.path.join(output_dir, name)
            if os.path.abspath(full) == keep_abs:
                continue
            try:
                os.remove(full)
                log_callback(f"[i] [Cleanup] Đã xóa {name}")
                removed_count += 1
            except OSError as e:
                logger.debug("Cleanup skip %s: %s", full, e)
        if removed_count == 0:
            logger.debug("Cleanup: no intermediates to remove")
    except OSError as e:
        logger.debug("Cleanup listdir failed: %s", e)


def _record_metric(
    apk_path: str,
    mode: str,
    success: bool,
    duration: float,
    patches: int = 0,
    error: str = "",
) -> None:
    """Record pipeline-level metric (toàn bộ lần chạy)."""
    try:
        from core.metrics import PatchMetrics, get_metrics
        get_metrics().record(PatchMetrics(
            apk_name=os.path.basename(apk_path) if apk_path else "",
            mode=mode,
            success=success,
            duration_sec=duration,
            patches_applied=patches,
            error=error[:500],
            stage="pipeline",
            trace_id=get_trace_id(),
        ))
    except Exception:
        pass


def _record_metric_stage(
    apk_path: str,
    mode: str,
    stage: str,
    duration: float,
    success: bool = True,
    error: str = "",
) -> None:
    """Record 1 stage timing vào metrics."""
    try:
        from core.metrics import get_metrics
        get_metrics().record_stage(
            apk_name=os.path.basename(apk_path) if apk_path else "",
            mode=mode,
            stage=stage,
            duration_sec=duration,
            success=success,
            error=error[:500] if error else "",
            trace_id=get_trace_id(),
        )
    except Exception:
        pass


class _StageTimer:
    """
    Context manager: đo thời gian 1 stage + auto record metric.
    Không suppress exception — chỉ record rồi để nó propagate.
    """

    def __init__(self, apk_path: str, mode: str, stage: str,
                 log_callback=None):
        self.apk_path = apk_path
        self.mode = mode
        self.stage = stage
        self.log = log_callback
        self.t0 = 0.0

    def __enter__(self):
        self.t0 = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        dt = time.monotonic() - self.t0
        success = exc_type is None
        err = str(exc_val) if exc_val else ""
        _record_metric_stage(
            self.apk_path, self.mode, self.stage, dt, success, err,
        )
        if self.log and not success:
            self.log(
                f"[!] [Stage:{self.stage}] failed after {dt:.1f}s: "
                f"{err[:200]}"
            )
        return False  # không suppress


# =============================================================
# STRATEGY RESOLUTION
# =============================================================
_DEFAULT_STRATEGY_BY_SIZE = {
    "tiny": "fast",
    "small": "fast",
    "medium": "balanced",
    "large": "careful",
    "huge": "careful",
    "massive": "paranoid",
}

_SIZE_ORDER = ("tiny", "small", "medium", "large", "huge", "massive")


def _resolve_strategy(config: dict, apk_path: str) -> tuple[str, str]:
    """Resolve strategy dựa trên kích thước APK."""
    try:
        size_mb = os.path.getsize(apk_path) / 1024 / 1024
    except OSError:
        return "balanced", "unknown"

    classes = (
        config.get("auto_tune", {})
        .get("workload_classes", {})
    ) or {}

    for name in _SIZE_ORDER:
        cls = classes.get(name) or {}
        max_mb = cls.get("max_size_mb", 99999)
        if size_mb <= max_mb:
            strategy = cls.get(
                "strategy", _DEFAULT_STRATEGY_BY_SIZE.get(name, "balanced")
            )
            return strategy, name

    return "balanced", "massive"


def _apply_strategy(config: dict, apk_path: str, log_callback) -> str:
    """Resolve strategy + set vào pipeline_executor. Return name."""
    strategy, size_class = _resolve_strategy(config, apk_path)
    try:
        from core.pipeline_executor import set_strategy
        set_strategy(strategy)
    except Exception as e:
        log_callback(f"[i] [Strategy] set_strategy failed: {e}")
    log_callback(
        f"[*] [Strategy] {strategy} (size_class={size_class})"
    )
    return strategy


# =============================================================
# SAFETY GUARD
# =============================================================
def _build_safety_guard(config: dict, log_callback, signals=None):
    """Build SafetyGuard từ config."""
    from core.safety_guard import GuardLimits, SafetyGuard

    safety_cfg = config.get("auto_tune", {}).get("safety", {})

    limits = GuardLimits(
        max_ram_pct=safety_cfg.get("throttle_ram_pct", 85.0),
        max_cpu_pct=safety_cfg.get("throttle_cpu_pct", 98.0),
        min_disk_free_pct=safety_cfg.get("reserve_disk_pct", 10.0),
        max_temp_celsius=safety_cfg.get("throttle_temp_celsius", 85.0),
        check_interval_sec=safety_cfg.get("check_interval_sec", 5.0),
        cpu_measurement=safety_cfg.get("cpu_measurement", "external"),
        enabled=safety_cfg.get("enabled", True),
        reset_after_ok_checks=int(
            safety_cfg.get("reset_after_ok_checks", 3)
        ),
        cli_mode_action=safety_cfg.get("cli_mode_action", "mute"),
    )

    if limits.max_cpu_pct < 95:
        log_callback(
            f"[!] [Safety] throttle_cpu_pct={limits.max_cpu_pct} <95 — "
            f"dễ false positive trên Windows (Defender scan APK). "
            f"Khuyến nghị ≥98 + Defender exclusion."
        )

    log_callback(
        f"[i] [Safety] Limits: CPU>{limits.max_cpu_pct}%, "
        f"RAM>{limits.max_ram_pct}%, Disk<{limits.min_disk_free_pct}%, "
        f"interval={limits.check_interval_sec}s, "
        f"reset_ok={limits.reset_after_ok_checks}, "
        f"cli={limits.cli_mode_action}, enabled={limits.enabled}"
    )

    prompt_after_n = int(safety_cfg.get("prompt_after_n_violations", 5))
    threshold_raise = float(safety_cfg.get("threshold_raise_pct", 5.0))
    prompt_timeout = float(safety_cfg.get("prompt_timeout_sec", 60.0))

    state = {"throttled": False, "throttle_factor": 1.0, "last_reason": ""}

    def _on_violation(reason: str, details: dict) -> None:
        backoff = safety_cfg.get("backoff_factor", 0.5)
        state["throttled"] = True
        state["throttle_factor"] = backoff
        state["last_reason"] = reason
        log_callback(
            f"[!] [Safety] {reason.upper()} vượt ngưỡng "
            f"→ giảm tải xuống {backoff*100:.0f}%"
        )

    def _on_mute(reason: str) -> None:
        state["throttled"] = False
        state["throttle_factor"] = 1.0
        state["last_reason"] = ""
        log_callback(
            f"[i] [Safety] Reset throttle — dùng full resources "
            f"({reason} muted)"
        )

    def _on_prompt(reason: str, details: dict, count: int) -> bool:
        if signals is None:
            log_callback(
                f"[!] [Safety] Không có GUI — auto-continue "
                f"(vi phạm #{count})"
            )
            return True

        import threading
        event = threading.Event()
        result = {"continue": True}

        def _set_result(user_continue: bool) -> None:
            result["continue"] = user_continue
            event.set()

        try:
            signals.safety_prompt.emit(reason, details, count, _set_result)
        except Exception as e:
            log_callback(f"[!] [Safety] Không emit được prompt: {e}")
            return True

        if not event.wait(timeout=prompt_timeout):
            log_callback(
                f"[!] [Safety] Không nhận phản hồi sau "
                f"{prompt_timeout:.0f}s → auto-continue"
            )
            return True
        return result["continue"]

    guard = SafetyGuard(
        limits=limits,
        on_violation=_on_violation,
        on_prompt=_on_prompt if signals is not None else None,
        on_mute=_on_mute,
        prompt_after_n_violations=prompt_after_n,
        threshold_raise_pct=threshold_raise,
        log_callback=log_callback,
    )
    return guard, state


def _check_safety_abort(guard, log_callback) -> None:
    if guard is not None and getattr(guard, "abort_flag", False):
        log_callback("[!] Pipeline stopped by user (SafetyGuard)")
        raise RuntimeError("Pipeline aborted by user via SafetyGuard")


# =============================================================
# MAIN PIPELINE
# =============================================================
def run_pipeline(
    apk_path: str,
    mode: str = "all",
    log_callback=print,
    *,
    key_type: str = "testkey",
    forced_package_id: int | None = None,
    fast_mode: bool | None = None,
    use_gda: bool | None = None,
    apktool_jobs: int | None = None,
    apktool_memory: str | None = None,
    keep_workspace: bool | None = None,
    clone_package: str | None = None,
    signals=None,
    force_reanalyze: bool = False,
    config: dict | None = None,
    **kwargs,
) -> tuple[bool, str | None, dict]:
    """
    Pipeline chính. Wrap body trong trace_context để mọi log/metric/
    history trong cùng 1 run có chung trace_id.
    """
    _setup_environment()

    if config is None:
        config = load_config(apk_path=apk_path, mode=mode)

    logger_inst = setup_logging(config)
    _log = log_callback

    with trace_context() as trace_id:
        return _run_pipeline_body(
            apk_path=apk_path,
            mode=mode,
            _log=_log,
            logger=logger_inst,
            key_type=key_type,
            forced_package_id=forced_package_id,
            fast_mode=fast_mode,
            use_gda=use_gda,
            apktool_jobs=apktool_jobs,
            apktool_memory=apktool_memory,
            keep_workspace=keep_workspace,
            clone_package=clone_package,
            signals=signals,
            force_reanalyze=force_reanalyze,
            config=config,
            trace_id=trace_id,
        )


def _run_pipeline_body(
    *,
    apk_path: str,
    mode: str,
    _log,
    logger,
    key_type: str,
    forced_package_id: int | None,
    fast_mode: bool | None,
    use_gda: bool | None,
    apktool_jobs: int | None,
    apktool_memory: str | None,
    keep_workspace: bool | None,
    clone_package: str | None,
    signals,
    force_reanalyze: bool,
    config: dict,
    trace_id: str,
) -> tuple[bool, str | None, dict]:
    """Body thực sự của pipeline — chạy trong trace_context."""
    t0 = time.monotonic()

    _log(f"[*] [tid:{trace_id}] ========== LP-PC Suite — Pipeline Start ==========")
    _log(f"[*] Input: {os.path.basename(apk_path)}")

    tune_info = config.get("_tune_result", {})
    if tune_info:
        _log(f"[*] Tune mode: {tune_info.get('mode', '?')}")

    # ---- BƯỚC 0: Normalize ----
    _emit_step(signals, "Chuẩn hóa input...", 2, _log)
    try:
        apk_path = normalize_input(apk_path, config, _log)
    except ValueError as e:
        _log(f"[!] Input không hợp lệ: {e}")
        logger.error("Input normalization failed: %s", e)
        _record_metric(apk_path, mode, False, time.monotonic() - t0,
                       error=str(e))
        if signals:
            try:
                signals.finished.emit(False, "")
            except Exception:
                pass
        return False, None, {}

    _log(f"[*] Processing: {os.path.basename(apk_path)}")

    # ---- Parse modes ----
    modes = (
        mode[6:].split(",") if mode.startswith("multi:")
        else [m.strip() for m in mode.split(",") if m.strip()]
    )
    if not modes:
        _log("[!] Không có mode nào được chọn")
        _record_metric(apk_path, mode, False,
                       time.monotonic() - t0, error="No modes")
        if signals:
            try:
                signals.finished.emit(False, "")
            except Exception:
                pass
        return False, None, {}

    from core.mode_registry import MODE_MAP
    from core.plugin_manager import PluginManager

    plugin_manager = PluginManager()
    all_modes = {**MODE_MAP, **plugin_manager.get_all_modes()}
    mapped_modes = [all_modes.get(m, m) for m in modes]
    _log(f"[*] Mapped modes: {mapped_modes}")

    if forced_package_id is not None and not (
        isinstance(forced_package_id, int)
        and 1 <= forced_package_id <= 127
    ):
        _log(f"[!] forced_package_id={forced_package_id} không hợp lệ")
        forced_package_id = None

    # ---- Resolve auto values ----
    pipe_cfg = config.get("pipeline", {})

    if apktool_jobs is None:
        v = pipe_cfg.get("apktool_jobs", "auto")
        apktool_jobs = (
            v if isinstance(v, int)
            else max(1, (os.cpu_count() or 4) - 1)
        )

    if apktool_memory is None:
        v = pipe_cfg.get("apktool_memory", "4096m")
        apktool_memory = v if isinstance(v, str) else "4096m"

    if fast_mode is None:
        fast_mode = pipe_cfg.get("fast_mode", False)
        fast_mode = fast_mode if isinstance(fast_mode, bool) else False

    if use_gda is None:
        use_gda = pipe_cfg.get("use_gda", False)
        use_gda = use_gda if isinstance(use_gda, bool) else False

    if keep_workspace is None:
        keep_workspace = pipe_cfg.get("keep_workspace", True)

    # ---- STRATEGY ----
    strategy = _apply_strategy(config, apk_path, _log)

    # ============================================================
    # ANALYZE (trước workspace để lấy package name)
    # ============================================================
    _emit_step(signals, "Phân tích APK...", 10, _log)
    app_name = ""
    package_name = ""
    with _StageTimer(apk_path, mode, "analyze", _log):
        try:
            from scanner.analyzer import AppDeepAnalyzer
            analyzer = AppDeepAnalyzer(apk_path)
            analyzer.analyze(force_reanalyze=force_reanalyze)
            summary = analyzer.get_summary() or {}

            app_name = _coerce_str(summary.get("app_name"))
            package_name = _coerce_str(summary.get("package"))

            if app_name:
                _log(f"[*] App: {app_name}")
            if package_name:
                _log(f"[*] Package: {package_name}")
            _log(f"[*] Analysis: {analyzer.get_colors()}")

            # Cảnh báo packer không patchable
            packer = getattr(analyzer, "packer_info", None)
            if isinstance(packer, dict) and not packer.get("patchable", True):
                _log(
                    f"[!] Packer detected: {packer.get('name', '?')} "
                    f"({packer.get('confidence', '?')} confidence) — "
                    f"patch license/iap/ads có thể patch 0 files "
                    f"(silent fail)"
                )
        except Exception as e:
            _log(f"[i] Analysis failed (tiếp tục): {e}")
            logger.warning("Analysis failed: %s", e)

    # ============================================================
    # WORKSPACE (package-based output folder)
    # ============================================================
    base_dir = Path(__file__).resolve().parent.parent / "workspace"
    decompiled_dir = str(base_dir / "decompiled")
    pkg_folder = _sanitize_folder_name(
        package_name or Path(apk_path).stem
    )
    output_dir = str(base_dir / "output" / pkg_folder)
    base_dir.mkdir(parents=True, exist_ok=True)
    os.makedirs(decompiled_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    _log(f"[*] Output dir: {output_dir}")

    # ---- SafetyGuard ----
    guard = None
    guard_state = None
    auto_tune_on = config.get("auto_tune", {}).get("enabled", True)
    safety_on = (
        config.get("auto_tune", {})
        .get("safety", {})
        .get("enabled", True)
    )

    if auto_tune_on and safety_on:
        try:
            guard, guard_state = _build_safety_guard(
                config, _log, signals=signals
            )
            guard.start()
        except Exception as e:
            logger.debug("SafetyGuard setup failed: %s", e)
            guard = None
    else:
        _log(
            f"[i] [Safety] Disabled "
            f"(auto_tune={auto_tune_on}, safety={safety_on})"
        )

    # ---- GC control ----
    gc_was_enabled = gc.isenabled()
    if config.get("pipeline", {}).get("gc_control", True):
        gc.disable()

    try:
        from core.pipeline_executor import execute_modes, set_file_cache
        from core.smali_utils import FileContentCache
        from core.apk_utils import (
            decompile_apk, recompile_apk, sign_apk,
        )
        from core.device_bridge import install_apk
        from core.patch_history import PatchHistory
        from patcher.watermarker import Watermarker

        # ---- GDA (optional) ----
        if use_gda:
            _check_safety_abort(guard, _log)
            _emit_step(signals, "Phân tích GDA...", 5, _log)
            with _StageTimer(apk_path, mode, "gda", _log):
                try:
                    from scanner.gda_analyzer import GDAAnalyzer
                    GDAAnalyzer().analyze(apk_path)
                except Exception as e:
                    _log(f"[i] [GDA] Bỏ qua: {e}")
                    logger.warning("GDA pre-analysis failed: %s", e)

        # ============================================================
        # Decompile
        # ============================================================
        needs_resources = any(
            m in mapped_modes for m in
            ("change_perms", "resign", "ads", "ads_full_offline",
             "ads_offline", "ads_other")
        )
        use_no_res = not needs_resources

        _check_safety_abort(guard, _log)
        _emit_step(signals, "Decompiling APK...", 15, _log)

        effective_jobs = apktool_jobs
        if guard_state and guard_state["throttled"]:
            factor = guard_state.get("throttle_factor", 1.0)
            effective_jobs = max(1, int(apktool_jobs * factor))
            _log(
                f"[i] [Safety] Throttle → jobs {apktool_jobs} "
                f"→ {effective_jobs}"
            )

        with _StageTimer(apk_path, mode, "decompile", _log):
            decompile_apk(
                apk_path, decompiled_dir,
                force=False,
                no_res=use_no_res,
                jobs=effective_jobs,
                max_memory=apktool_memory,
                log_callback=_log,
            )
        _emit_step(signals, "Decompile xong", 40, _log)

        # ---- Patch ----
        _check_safety_abort(guard, _log)
        file_cache = FileContentCache(
            decompiled_dir,
            log_callback=_log,
        )
        set_file_cache(file_cache)

        ad_activities: list[str] = []
        try:
            from scanner.ad_scanner import AdScanner
            ad_activities, _ = AdScanner(apk_path).scan_manifest()
        except Exception as e:
            logger.warning("Ad scan failed: %s", e)

        _emit_step(
            signals,
            f"Đang vá {len(mapped_modes)} mode...",
            45, _log,
        )
        with _StageTimer(apk_path, mode, "patch", _log):
            patches_applied, patch_reports = execute_modes(
                mapped_modes, decompiled_dir, ad_activities,
                apk_path, _log, signals,
                strategy=strategy,
            )

        _emit_step(signals, "Ghi thay đổi...", 65, _log)
        file_cache.flush(_log)

        # ---- Watermark SAU flush (G7) ----
        if patches_applied:
            _check_safety_abort(guard, _log)
            _emit_step(signals, "Thêm watermark...", 70, _log)
            with _StageTimer(apk_path, mode, "watermark", _log):
                try:
                    Watermarker.add_watermark(
                        decompiled_dir, patches_applied, apk_path
                    )
                except Exception as e:
                    logger.warning("Watermark failed: %s", e)

        # ============================================================
        # Recompile với fallback no_res=False khi fail
        # ============================================================
        _check_safety_abort(guard, _log)
        _emit_step(signals, "Recompiling APK...", 75, _log)
        patched_apk = os.path.join(output_dir, "patched.apk")

        with _StageTimer(apk_path, mode, "recompile", _log):
            try:
                recompile_apk(
                    decompiled_dir, patched_apk,
                    forced_package_id=forced_package_id,
                    log_callback=_log,
                    verify=True,
                    input_apk_for_delta=apk_path,
                )
            except RuntimeError as recompile_err:
                if use_no_res:
                    _log(
                        f"[!] Recompile failed ({recompile_err}) — "
                        f"retry với no_res=False"
                    )
                    _emit_step(
                        signals, "Retry decompile với resources...",
                        60, _log,
                    )
                    with _StageTimer(
                        apk_path, mode, "decompile-retry", _log
                    ):
                        decompile_apk(
                            apk_path, decompiled_dir,
                            force=True,
                            no_res=False,
                            jobs=effective_jobs,
                            max_memory=apktool_memory,
                            log_callback=_log,
                        )
                    file_cache = FileContentCache(
                        decompiled_dir, log_callback=_log
                    )
                    set_file_cache(file_cache)
                    patches_applied, patch_reports = execute_modes(
                        mapped_modes, decompiled_dir, ad_activities,
                        apk_path, _log, signals,
                        strategy=strategy,
                    )
                    file_cache.flush(_log)
                    recompile_apk(
                        decompiled_dir, patched_apk,
                        forced_package_id=forced_package_id,
                        log_callback=_log,
                        verify=True,
                        input_apk_for_delta=apk_path,
                    )
                else:
                    raise

        _emit_step(signals, "Recompile xong", 88, _log)

        # ============================================================
        # Sign → Rename → Cleanup intermediates
        # ============================================================
        _emit_step(signals, "Đang ký APK...", 92, _log)
        with _StageTimer(apk_path, mode, "sign", _log):
            signed_apk = sign_apk(
                patched_apk, key_type=key_type, log_callback=_log
            )

        # ---- Rename → {package}.{Patch1}.{Patch2}.apk ----
        new_filename = build_output_filename(
            package_name=package_name,
            mapped_modes=mapped_modes,
            fallback_stem=Path(apk_path).stem,
        )
        final_apk = os.path.join(output_dir, new_filename)
        _log(f"[*] Renaming → {new_filename}")

        if os.path.abspath(signed_apk) != os.path.abspath(final_apk):
            if os.path.exists(final_apk):
                try:
                    os.remove(final_apk)
                except OSError:
                    pass
            os.replace(signed_apk, final_apk)

        # ---- Cleanup intermediates ----
        _cleanup_intermediates(
            output_dir=output_dir,
            keep=final_apk,
            log_callback=_log,
        )

        # ---- ADB install ----
        _emit_step(signals, "Cài đặt qua ADB (optional)...", 96, _log)
        with _StageTimer(apk_path, mode, "install", _log):
            try:
                install_apk(final_apk)
                _log("[✔] [ADB] Installed on device")
            except Exception as e:
                _log(f"[i] [ADB] Install skipped: {e}")
                logger.info("ADB install skipped: %s", e)

        # ---- History ----
        _emit_step(signals, "Lưu lịch sử...", 98, _log)
        try:
            PatchHistory().add_record(
                apk_path, mode, True, final_apk, patches_applied,
                trace_id=trace_id,
            )
        except Exception as e:
            logger.warning("History save failed: %s", e)

        # ---- Tổng kết ----
        elapsed = time.monotonic() - t0
        if patches_applied:
            summary = (
                f"{len(patches_applied)} mode(s) applied: "
                f"{', '.join(patches_applied)}"
            )
        else:
            summary = "không có patch"

        _emit_step(
            signals, f"Hoàn thành trong {elapsed:.1f}s", 100, _log
        )
        _log(f"[✔] Output: {final_apk}")
        _log(f"[✔] Done in {elapsed:.1f}s — {summary}")

        _record_metric(
            apk_path, mode, True, elapsed,
            patches=len(patches_applied),
        )

        if signals:
            try:
                signals.finished.emit(True, final_apk)
            except Exception:
                pass

        return True, final_apk, patch_reports

    except RuntimeError as e:
        elapsed = time.monotonic() - t0
        if "aborted by user" in str(e):
            _log(f"[!] Pipeline dừng bởi user sau {elapsed:.1f}s")
        else:
            _log(f"[!] Pipeline failed: {e}")
            logger.exception("Pipeline crashed")

        try:
            from core.patch_history import PatchHistory
            PatchHistory().add_record(
                apk_path, mode, False, "", [],
                trace_id=trace_id,
            )
        except Exception:
            pass

        _record_metric(apk_path, mode, False, elapsed, error=str(e))

        if signals:
            try:
                signals.finished.emit(False, "")
            except Exception:
                pass

        return False, None, {}

    except Exception as e:
        elapsed = time.monotonic() - t0
        _log(f"[!] Pipeline failed: {e}")
        logger.exception("Pipeline crashed")
        traceback.print_exc()

        try:
            from core.patch_history import PatchHistory
            PatchHistory().add_record(
                apk_path, mode, False, "", [],
                trace_id=trace_id,
            )
        except Exception:
            pass

        _record_metric(apk_path, mode, False, elapsed, error=str(e))

        if signals:
            try:
                signals.finished.emit(False, "")
            except Exception:
                pass

        return False, None, {}

    finally:
        if guard:
            try:
                guard.stop()
            except Exception:
                pass

        if gc_was_enabled:
            gc.enable()
            _log("[*] [GC] Re-enabled")

        if not keep_workspace:
            shutil.rmtree(decompiled_dir, ignore_errors=True)
            _log("[*] Workspace cleaned")
        else:
            _log(f"[*] Workspace: {decompiled_dir}")


# =============================================================
# CLI
# =============================================================
def main() -> int:
    _setup_environment()

    parser = argparse.ArgumentParser(
        prog="lp-pc-suite",
        description="LP-PC Suite — APK patcher (production-ready)",
    )
    parser.add_argument("apk", nargs="?")
    parser.add_argument("--mode", default="all")
    parser.add_argument("--config")
    parser.add_argument("--custom-patch")
    parser.add_argument(
        "--key-type",
        choices=["testkey", "platform", "media", "shared"],
        default="testkey",
    )
    parser.add_argument("--forced-package-id", type=int)
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--no-fast", action="store_true")
    parser.add_argument("--gda", action="store_true")
    parser.add_argument("--apktool-jobs", type=int)
    parser.add_argument("--apktool-memory")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--clone-package")
    parser.add_argument("--force-reanalyze", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--no-tune", action="store_true",
        help="Tắt toàn bộ auto_tune (bao gồm safety guard)",
    )
    parser.add_argument(
        "--no-safety", action="store_true",
        help="Tắt SafetyGuard (vẫn giữ auto_tune cho jobs/memory)",
    )
    parser.add_argument(
        "--trace-id",
        help="Override trace_id (default: auto-gen 8-char hex)",
    )

    args = parser.parse_args()

    if not args.apk:
        parser.print_help()
        return 1

    if args.custom_patch:
        os.environ["LP_CUSTOM_PATCH"] = args.custom_patch

    if args.trace_id:
        os.environ["LP_TRACE_ID"] = args.trace_id

    config = load_config(args.config, apk_path=args.apk, mode=args.mode)

    if args.no_tune:
        config.setdefault("auto_tune", {})["enabled"] = False

    if args.no_safety:
        config.setdefault("auto_tune", {}) \
              .setdefault("safety", {})["enabled"] = False
        print("[i] SafetyGuard disabled via --no-safety")

    if args.verbose:
        config.setdefault("logging", {})["level"] = "DEBUG"

    fast_mode = None
    if args.fast:
        fast_mode = True
    elif args.no_fast:
        fast_mode = False

    use_gda = True if args.gda else None
    keep_workspace = False if args.clean else None

    ok, _, _ = run_pipeline(
        args.apk, mode=args.mode, key_type=args.key_type,
        forced_package_id=args.forced_package_id,
        fast_mode=fast_mode, use_gda=use_gda,
        apktool_jobs=args.apktool_jobs,
        apktool_memory=args.apktool_memory,
        keep_workspace=keep_workspace,
        clone_package=args.clone_package,
        force_reanalyze=args.force_reanalyze,
        config=config,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())