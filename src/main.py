"""
LP-PC Suite — Entry point chính.
Tuân thủ production-ready:
  - Stability: try/except mọi layer, fallback
  - Performance: lazy import, cache, GC control
  - Network: retry/timeout qua helper
  - Logging: RotatingFileHandler + GUI callback
  - Security: validate input qua normalize_input
  - Scalability: config-driven, modular
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


def run_pipeline(
    apk_path: str,
    mode: str = "all",
    log_callback=print,
    *,
    key_type: str = "testkey",
    forced_package_id: int | None = None,
    fast_mode: bool = True,
    use_gda: bool = False,
    apktool_jobs: int | None = None,
    apktool_memory: str = "4096m",
    keep_workspace: bool = True,
    clone_package: str | None = None,
    signals=None,
    force_reanalyze: bool = False,
    config: dict | None = None,
    **kwargs,
) -> tuple[bool, str | None, dict]:
    """
    Chạy pipeline vá APK.

    Args:
        apk_path: đường dẫn .apk / .xapk / folder split APK
        mode: chuỗi mode (vd "license,ads" hoặc "multi:license:auto,ads:offline")
        log_callback: hàm nhận str để log ra GUI
        key_type: testkey | platform | media | shared
        forced_package_id: 1-127 hoặc None
        fast_mode: chỉ decompile main classes
        use_gda: chạy GDA pre-analysis
        apktool_jobs: số thread; None = auto (cpu_count - 1)
        apktool_memory: Java heap (vd "4096m")
        keep_workspace: giữ thư mục decompiled sau khi chạy
        clone_package: tên package mới cho chế độ clone
        signals: PipelineSignals để cập nhật GUI
        force_reanalyze: bỏ qua cache phân tích
        config: dict config đã load; None = load mặc định

    Returns:
        (success, output_apk_path, patch_reports)
    """
    if config is None:
        config = load_config()

    log = setup_logging(config).info
    _log = log_callback

    t0 = time.monotonic()
    _log("[*] ========== LP-PC Suite — Pipeline Start ==========")
    _log(f"[*] Input: {os.path.basename(apk_path)}")

    # ---- BƯỚC 0: chuẩn hóa input (.xapk → .apk bắt buộc) ----
    try:
        apk_path = normalize_input(apk_path, config, _log)
    except ValueError as e:
        _log(f"[!] Input không hợp lệ: {e}")
        log.error("Input normalization failed: %s", e)
        return False, None, {}

    _log(f"[*] Processing: {os.path.basename(apk_path)}")

    # ---- Parse modes ----
    modes = (
        mode[6:].split(",") if mode.startswith("multi:")
        else [m.strip() for m in mode.split(",") if m.strip()]
    )
    if not modes:
        _log("[!] Không có mode nào được chọn")
        return False, None, {}

    from core.mode_registry import MODE_MAP
    from core.plugin_manager import PluginManager

    plugin_manager = PluginManager()
    all_modes = {**MODE_MAP, **plugin_manager.get_all_modes()}
    mapped_modes = [all_modes.get(m, m) for m in modes]
    _log(f"[*] Mapped modes: {mapped_modes}")

    # ---- Validate forced_package_id ----
    if forced_package_id is not None and not (
        isinstance(forced_package_id, int) and 1 <= forced_package_id <= 127
    ):
        _log(f"[!] forced_package_id={forced_package_id} không hợp lệ, bỏ qua")
        forced_package_id = None

    # ---- Workspace ----
    base_dir = Path(__file__).resolve().parent.parent / "workspace"
    decompiled_dir = str(base_dir / "decompiled")
    output_dir = str(base_dir / "output")
    base_dir.mkdir(parents=True, exist_ok=True)
    os.makedirs(decompiled_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    if apktool_jobs is None:
        apktool_jobs = (
            config.get("pipeline", {}).get("apktool_jobs")
            or max(1, (os.cpu_count() or 4) - 1)
        )

    # ---- GC control (performance) ----
    gc_was_enabled = gc.isenabled()
    gc.disable()

    try:
        from core.pipeline_executor import execute_modes, set_file_cache
        from core.smali_utils import APKCache, FileContentCache
        from core.apk_utils import (
            decompile_apk,
            recompile_apk,
            sign_apk,
        )
        from core.device_bridge import install_apk
        from core.patch_history import PatchHistory
        from patcher.watermarker import Watermarker

        # ---- BƯỚC 1: GDA pre-analysis (optional) ----
        if use_gda:
            try:
                from scanner.gda_analyzer import GDAAnalyzer
                GDAAnalyzer().analyze(apk_path)
            except Exception as e:
                _log(f"[i] [GDA] Bỏ qua: {e}")
                log.warning("GDA pre-analysis failed: %s", e)

        # ---- BƯỚC 2: Phân tích APK (có cache) ----
        analyzer = None
        try:
            from scanner.analyzer import AppDeepAnalyzer
            analyzer = AppDeepAnalyzer(apk_path)
            analyzer.analyze(force_reanalyze=force_reanalyze)
            _log(f"[*] Analysis: {analyzer.get_colors()}")
        except Exception as e:
            _log(f"[i] Analysis failed (tiếp tục): {e}")
            log.warning("Analysis failed: %s", e)

        # ---- BƯỚC 3: Decompile ----
        needs_resources = any(
            m in mapped_modes for m in ("change_perms", "resign")
        )
        _log(f"[*] [Apktool] Decompiling (no_res={not needs_resources})...")
        decompile_apk(
            apk_path, decompiled_dir,
            force=True,
            no_res=not needs_resources,
            jobs=apktool_jobs,
            max_memory=apktool_memory,
            log_callback=_log,
        )
        _log("[*] [Apktool] Decompile completed")

        # ---- BƯỚC 4: Patch ----
        file_cache = FileContentCache(decompiled_dir)
        set_file_cache(file_cache)

        ad_activities: list[str] = []
        try:
            from scanner.ad_scanner import AdScanner
            ad_activities, _ = AdScanner(apk_path).scan_manifest()
        except Exception as e:
            log.warning("Ad scan failed: %s", e)

        patches_applied, patch_reports = execute_modes(
            mapped_modes, decompiled_dir, ad_activities,
            apk_path, _log, signals,
        )

        # Ghi tất cả thay đổi một lần duy nhất
        file_cache.flush(_log)

        # ---- BƯỚC 5: Watermark ----
        if patches_applied:
            try:
                Watermarker.add_watermark(
                    decompiled_dir, patches_applied, apk_path
                )
            except Exception as e:
                log.warning("Watermark failed: %s", e)

        # ---- BƯỚC 6: Recompile ----
        _log("[*] [Apktool] Recompiling...")
        patched_apk = os.path.join(output_dir, "patched.apk")
        recompile_apk(
            decompiled_dir, patched_apk,
            forced_package_id=forced_package_id,
            log_callback=_log,
        )
        _log("[*] [Apktool] Recompile completed")

        # ---- BƯỚC 7: Sign ----
        signed_apk = sign_apk(
            patched_apk, key_type=key_type, log_callback=_log
        )
        final_apk = os.path.join(output_dir, os.path.basename(signed_apk))
        if os.path.abspath(signed_apk) != os.path.abspath(final_apk):
            if os.path.exists(final_apk):
                os.remove(final_apk)
            os.replace(signed_apk, final_apk)

        _log(f"[✔] Output: {final_apk}")

        # ---- BƯỚC 8: ADB install (optional) ----
        try:
            install_apk(final_apk)
            _log("[✔] [ADB] Installed on device")
        except Exception as e:
            _log(f"[i] [ADB] Install skipped: {e}")
            log.info("ADB install skipped: %s", e)

        # ---- BƯỚC 9: Lưu lịch sử ----
        try:
            PatchHistory().add_record(
                apk_path, mode, True, final_apk, patches_applied
            )
        except Exception as e:
            log.warning("History save failed: %s", e)

        # ---- Tổng kết ----
        elapsed = time.monotonic() - t0
        summary = (
            ", ".join(patches_applied) if patches_applied
            else "không có patch"
        )
        _log(f"[✔] Done in {elapsed:.1f}s — {summary}")

        if signals:
            try:
                signals.finished.emit(True, final_apk)
            except Exception:
                pass

        return True, final_apk, patch_reports

    except Exception as e:
        _log(f"[!] Pipeline failed: {e}")
        log.exception("Pipeline crashed")
        traceback.print_exc()

        try:
            from core.patch_history import PatchHistory
            PatchHistory().add_record(apk_path, mode, False, "", [])
        except Exception:
            pass

        if signals:
            try:
                signals.finished.emit(False, "")
            except Exception:
                pass

        return False, None, {}

    finally:
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
    parser = argparse.ArgumentParser(
        prog="lp-pc-suite",
        description="LP-PC Suite — APK patcher (production-ready)",
    )
    parser.add_argument(
        "apk", nargs="?",
        help=".apk / .xapk / folder chứa split APK",
    )
    parser.add_argument(
        "--mode", default="all",
        help="Mode (comma-separated), vd 'license,ads,iap_dex'",
    )
    parser.add_argument(
        "--config",
        help="Đường dẫn YAML config (mặc định: config/default.yaml)",
    )
    parser.add_argument(
        "--custom-patch",
        help="Path tới file custom patch (.txt/.lpzip)",
    )
    parser.add_argument(
        "--key-type",
        choices=["testkey", "platform", "media", "shared"],
        default="testkey",
    )
    parser.add_argument("--forced-package-id", type=int)
    parser.add_argument(
        "--fast", action="store_true",
        help="Fast mode (chỉ main classes)",
    )
    parser.add_argument(
        "--gda", action="store_true",
        help="GDA pre-analysis",
    )
    parser.add_argument("--apktool-jobs", type=int)
    parser.add_argument("--apktool-memory", default="4096m")
    parser.add_argument(
        "--clean", action="store_true",
        help="Xóa workspace sau khi chạy",
    )
    parser.add_argument("--clone-package")
    parser.add_argument("--force-reanalyze", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    if not args.apk:
        parser.print_help()
        return 1

    if args.custom_patch:
        os.environ["LP_CUSTOM_PATCH"] = args.custom_patch

    config = load_config(args.config)
    if args.verbose:
        config.setdefault("logging", {})["level"] = "DEBUG"

    ok, _, _ = run_pipeline(
        args.apk,
        mode=args.mode,
        key_type=args.key_type,
        forced_package_id=args.forced_package_id,
        fast_mode=args.fast,
        use_gda=args.gda,
        apktool_jobs=args.apktool_jobs,
        apktool_memory=args.apktool_memory,
        keep_workspace=not args.clean,
        clone_package=args.clone_package,
        force_reanalyze=args.force_reanalyze,
        config=config,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())