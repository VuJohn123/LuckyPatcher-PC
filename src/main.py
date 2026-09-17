"""
LP-PC Suite — Entry point chính.

Fix G1: enable decompile cache (force=False).
Fix G2: auto-fallback no_res=False khi recompile fail.
Fix G7: watermark SAU file_cache.flush() để không bị ads patch ghi đè.
"""
from __future__ import annotations

import argparse
import gc
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

from core.pipeline_helpers import normalize_input, setup_logging
from core.config import load_config


# =============================================================
# HELPERS
# =============================================================
def _emit_step(signals, name: str, pct: int, log_callback) -> None:
    if signals:
        try:
            signals.step.emit(name, pct)
        except Exception:
            pass
    log_callback(f"[*] [{pct:3d}%] {name}")


def _record_metric(
    apk_path: str,
    mode: str,
    success: bool,
    duration: float,
    patches: int = 0,
    error: str = "",
) -> None:
    try:
        from core.metrics import PatchMetrics, get_metrics
        get_metrics().record(PatchMetrics(
            apk_name=os.path.basename(apk_path) if apk_path else "",
            mode=mode,
            success=success,
            duration_sec=duration,
            patches_applied=patches,
            error=error[:500],
        ))
    except Exception:
        pass


# =============================================================
# SAFETY GUARD (không đổi từ lần trước)
# =============================================================
def _build_safety_guard(config: dict, log_callback, signals=None):
    from core.safety_guard import GuardLimits, SafetyGuard

    safety_cfg = config.get("auto_tune", {}).get("safety", {})

    limits = GuardLimits(
        max_ram_pct=safety_cfg.get("throttle_ram_pct", 85.0),
        max_cpu_pct=safety_cfg.get("throttle_cpu_pct", 95.0),
        min_disk_free_pct=safety_cfg.get("reserve_disk_pct", 10.0),
        max_temp_celsius=safety_cfg.get("throttle_temp_celsius", 85.0),
        check_interval_sec=safety_cfg.get("check_interval_sec", 5.0),
        cpu_measurement=safety_cfg.get("cpu_measurement", "external"),
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

    def _on_prompt(reason: str, details: dict, count: int) -> bool:
        if signals is None:
            log_callback(
                f"[!] [Safety] Không có GUI — auto-continue "
                f"(đã vi phạm {count} lần)"
            )
            state["throttled"] = False
            state["throttle_factor"] = 1.0
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
            state["throttled"] = False
            state["throttle_factor"] = 1.0
            return True

        user_continue = result["continue"]
        if user_continue:
            state["throttled"] = False
            state["throttle_factor"] = 1.0
            log_callback(
                "[i] [Safety] Reset throttle — pipeline sẽ dùng "
                "full resources"
            )
        return user_continue

    guard = SafetyGuard(
        limits=limits,
        on_violation=_on_violation,
        on_prompt=_on_prompt if signals is not None else None,
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
    if config is None:
        config = load_config(apk_path=apk_path, mode=mode)

    logger = setup_logging(config)
    _log = log_callback

    t0 = time.monotonic()
    _log("[*] ========== LP-PC Suite — Pipeline Start ==========")
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
            try: signals.finished.emit(False, "")
            except Exception: pass
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
            try: signals.finished.emit(False, "")
            except Exception: pass
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
        apktool_jobs = v if isinstance(v, int) else max(1, (os.cpu_count() or 4) - 1)

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

    # ---- Workspace ----
    base_dir = Path(__file__).resolve().parent.parent / "workspace"
    decompiled_dir = str(base_dir / "decompiled")
    output_dir = str(base_dir / "output")
    base_dir.mkdir(parents=True, exist_ok=True)
    os.makedirs(decompiled_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    # ---- SafetyGuard ----
    guard = None
    guard_state = None
    if config.get("auto_tune", {}).get("enabled", True):
        try:
            guard, guard_state = _build_safety_guard(
                config, _log, signals=signals
            )
            guard.start()
        except Exception as e:
            logger.debug("SafetyGuard setup failed: %s", e)
            guard = None

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

        # ---- GDA ----
        if use_gda:
            _check_safety_abort(guard, _log)
            _emit_step(signals, "Phân tích GDA...", 5, _log)
            try:
                from scanner.gda_analyzer import GDAAnalyzer
                GDAAnalyzer().analyze(apk_path)
            except Exception as e:
                _log(f"[i] [GDA] Bỏ qua: {e}")
                logger.warning("GDA pre-analysis failed: %s", e)

        # ---- Analyze ----
        _check_safety_abort(guard, _log)
        _emit_step(signals, "Phân tích APK...", 10, _log)
        try:
            from scanner.analyzer import AppDeepAnalyzer
            analyzer = AppDeepAnalyzer(apk_path)
            analyzer.analyze(force_reanalyze=force_reanalyze)
            _log(f"[*] Analysis: {analyzer.get_colors()}")
        except Exception as e:
            _log(f"[i] Analysis failed (tiếp tục): {e}")
            logger.warning("Analysis failed: %s", e)

        # ============================================================
        # G2: Decompile + Recompile với auto-fallback
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

        # G1: force=False để dùng cache
        decompile_apk(
            apk_path, decompiled_dir,
            force=False,               # ← FIX G1
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
        patches_applied, patch_reports = execute_modes(
            mapped_modes, decompiled_dir, ad_activities,
            apk_path, _log, signals,
        )

        _emit_step(signals, "Ghi thay đổi...", 65, _log)
        file_cache.flush(_log)

        # ---- Watermark SAU flush (G7) ----
        if patches_applied:
            _check_safety_abort(guard, _log)
            _emit_step(signals, "Thêm watermark...", 70, _log)
            try:
                Watermarker.add_watermark(
                    decompiled_dir, patches_applied, apk_path
                )
            except Exception as e:
                logger.warning("Watermark failed: %s", e)

        # ============================================================
        # G2: Recompile với fallback no_res=False khi fail
        # ============================================================
        _check_safety_abort(guard, _log)
        _emit_step(signals, "Recompiling APK...", 75, _log)
        patched_apk = os.path.join(output_dir, "patched.apk")

        try:
            recompile_apk(
                decompiled_dir, patched_apk,
                forced_package_id=forced_package_id,
                log_callback=_log,
                verify=True,
                input_apk_for_delta=apk_path,
            )
        except RuntimeError as recompile_err:
            # G2: Fallback decompile with resources nếu đang no_res
            if use_no_res:
                _log(
                    f"[!] Recompile failed ({recompile_err}) — "
                    f"retry với no_res=False"
                )
                _emit_step(
                    signals, "Retry decompile với resources...",
                    60, _log,
                )
                decompile_apk(
                    apk_path, decompiled_dir,
                    force=True,             # bypass cache
                    no_res=False,           # ← include resources
                    jobs=effective_jobs,
                    max_memory=apktool_memory,
                    log_callback=_log,
                )
                # Re-apply patches
                file_cache = FileContentCache(
                    decompiled_dir, log_callback=_log
                )
                set_file_cache(file_cache)
                patches_applied, patch_reports = execute_modes(
                    mapped_modes, decompiled_dir, ad_activities,
                    apk_path, _log, signals,
                )
                file_cache.flush(_log)
                # Retry recompile
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

        # ---- Sign ----
        _emit_step(signals, "Đang ký APK...", 92, _log)
        signed_apk = sign_apk(
            patched_apk, key_type=key_type, log_callback=_log
        )
        final_apk = os.path.join(output_dir, os.path.basename(signed_apk))
        if os.path.abspath(signed_apk) != os.path.abspath(final_apk):
            if os.path.exists(final_apk):
                os.remove(final_apk)
            os.replace(signed_apk, final_apk)

        # ---- ADB install ----
        _emit_step(signals, "Cài đặt qua ADB (optional)...", 96, _log)
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
                apk_path, mode, True, final_apk, patches_applied
            )
        except Exception as e:
            logger.warning("History save failed: %s", e)

        # ---- Tổng kết ----
        elapsed = time.monotonic() - t0
        summary = (
            ", ".join(patches_applied) if patches_applied
            else "không có patch"
        )
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
            try: signals.finished.emit(True, final_apk)
            except Exception: pass

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
            PatchHistory().add_record(apk_path, mode, False, "", [])
        except Exception:
            pass

        _record_metric(apk_path, mode, False, elapsed, error=str(e))

        if signals:
            try: signals.finished.emit(False, "")
            except Exception: pass

        return False, None, {}

    except Exception as e:
        elapsed = time.monotonic() - t0
        _log(f"[!] Pipeline failed: {e}")
        logger.exception("Pipeline crashed")
        traceback.print_exc()

        try:
            from core.patch_history import PatchHistory
            PatchHistory().add_record(apk_path, mode, False, "", [])
        except Exception:
            pass

        _record_metric(apk_path, mode, False, elapsed, error=str(e))

        if signals:
            try: signals.finished.emit(False, "")
            except Exception: pass

        return False, None, {}

    finally:
        if guard:
            try: guard.stop()
            except Exception: pass

        if gc_was_enabled:
            gc.enable()
            _log("[*] [GC] Re-enabled")

        if not keep_workspace:
            shutil.rmtree(decompiled_dir, ignore_errors=True)
            _log("[*] Workspace cleaned")
        else:
            _log(f"[*] Workspace: {decompiled_dir}")


# =============================================================
# CLI (không đổi)
# =============================================================
def main() -> int:
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
    parser.add_argument("--no-tune", action="store_true")

    args = parser.parse_args()

    if not args.apk:
        parser.print_help()
        return 1

    if args.custom_patch:
        os.environ["LP_CUSTOM_PATCH"] = args.custom_patch

    config = load_config(args.config, apk_path=args.apk, mode=args.mode)

    if args.no_tune:
        config.setdefault("auto_tune", {})["enabled"] = False

    if args.verbose:
        config.setdefault("logging", {})["level"] = "DEBUG"

    fast_mode = None
    if args.fast: fast_mode = True
    elif args.no_fast: fast_mode = False

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