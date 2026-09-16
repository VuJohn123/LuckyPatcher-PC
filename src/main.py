"""
LP-PC Suite — Entry point chính.
Tuân thủ production-ready checklist:
  - Stability: fallback cho mọi lỗi có thể recover
  - Performance: lazy import, cache, GC control
  - Network: retry/timeout cho mọi call mạng
  - Logging: structured, không noisy
  - Security: validate + sanitize mọi input
  - Scalability: config-driven, modular
"""
from __future__ import annotations

import argparse
import gc
import logging
import os
import sys
import time
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# Lazy import để tăng startup speed
_pipeline_executor = None
_file_cache_mod = None


def _lazy_imports():
    """Import nặng chỉ khi cần — tránh block CLI --help."""
    global _pipeline_executor, _file_cache_mod
    if _pipeline_executor is None:
        from core.pipeline_executor import execute_modes, set_file_cache
        from core.smali_utils import FileContentCache, APKCache
        _pipeline_executor = (execute_modes, set_file_cache)
        _file_cache_mod = (FileContentCache, APKCache)


# =============================================================
# LOGGING SETUP
# =============================================================
def setup_logging(config: dict, log_callback=None) -> logging.Logger:
    """Cấu hình logging 1 lần — idempotent."""
    logger = logging.getLogger("lp_pc_suite")
    if logger.handlers:
        return logger

    log_cfg = config.get("logging", {})
    level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)
    logger.setLevel(level)

    log_file = log_cfg.get("file", "logs/pipeline.log")
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    handler = RotatingFileHandler(
        log_file,
        maxBytes=log_cfg.get("max_bytes", 10 * 1024 * 1024),
        backupCount=log_cfg.get("backup_count", 5),
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(handler)
    return logger


# =============================================================
# INPUT NORMALIZATION — .xapk → .apk BẮT BUỘC
# =============================================================
def normalize_input(path: str, config: dict, log) -> str:
    """
    Chuẩn hóa input TRƯỚC khi vào pipeline:
      - .apk   → giữ nguyên
      - .xapk  → convert thành .apk (BẮT BUỘC)
      - folder → merge split APK thành .apk

    Raise: ValueError nếu input không hợp lệ.
    """
    if not path:
        raise ValueError("Đường dẫn input rỗng")

    if not os.path.exists(path):
        raise ValueError(f"Input không tồn tại: {path}")

    # Case 1: .apk
    if os.path.isfile(path) and path.lower().endswith(".apk"):
        log(f"[*] Input là .apk — bỏ qua conversion")
        return path

    # Case 2: .xapk
    from core.xapk_converter import is_xapk, convert_xapk_to_apk, XAPKConversionError
    if os.path.isfile(path) and (path.lower().endswith(".xapk") or is_xapk(path)):
        if not config.get("conversion", {}).get("auto_convert_xapk", True):
            raise ValueError("Input là .xapk nhưng auto_convert_xapk bị tắt")
        try:
            apk = convert_xapk_to_apk(path, log_callback=log)
            return apk
        except XAPKConversionError as e:
            raise ValueError(f"Convert .xapk thất bại: {e}") from e

    # Case 3: folder split APK
    if os.path.isdir(path):
        if not config.get("conversion", {}).get("allow_split_apk", True):
            raise ValueError("Input là folder nhưng allow_split_apk bị tắt")
        from core.apk_utils import merge_split_apks
        apk_files = [f for f in os.listdir(path) if f.lower().endswith(".apk")]
        if not apk_files:
            raise ValueError(f"Folder không chứa .apk: {path}")
        out = os.path.join(os.path.dirname(path), "merged.apk")
        merge_split_apks(path, out, log)
        return out

    raise ValueError(f"Không hỗ trợ định dạng input: {path}")


# =============================================================
# PIPELINE
# =============================================================
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
    signals: Any = None,
    force_reanalyze: bool = False,
    config: dict | None = None,
    **kwargs,
) -> tuple[bool, str | None, dict]:
    """
    Chạy pipeline vá APK.

    Returns: (success, output_apk_path, patch_reports)
    """
    from core.config import load_config
    if config is None:
        config = load_config()

    log = setup_logging(config).info
    _log = log_callback  # GUI log callback (có thể khác file logger)

    t0 = time.monotonic()
    _log(f"[*] ========== LP-PC Suite — Pipeline Start ==========")
    _log(f"[*] Input: {os.path.basename(apk_path)}")
    _log(f"[*] Raw mode: {mode}")

    # ---- STEP 0: Chuẩn hóa input (.xapk → .apk BẮT BUỘC) ----
    try:
        apk_path = normalize_input(apk_path, config, _log)
    except ValueError as e:
        _log(f"[!] Input không hợp lệ: {e}")
        log.error("Input normalization failed: %s", e)
        return False, None, {}

    _log(f"[*] Processing: {os.path.basename(apk_path)}")

    # ---- Parse modes ----
    modes = (mode[6:].split(",") if mode.startswith("multi:")
             else [m.strip() for m in mode.split(",") if m.strip()])
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
    if forced_package_id is not None and not (isinstance(forced_package_id, int)
                                              and 1 <= forced_package_id <= 127):
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
        apktool_jobs = config.get("pipeline", {}).get("apktool_jobs") or \
                       max(1, (os.cpu_count() or 4) - 1)

    # ---- GC control (performance) ----
    gc_was_enabled = gc.isenabled()
    gc.disable()
    _log("[*] [GC] Disabled during pipeline")

    try:
        _lazy_imports()
        execute_modes, set_file_cache = _pipeline_executor
        FileContentCache, APKCache = _file_cache_mod

        from core.apk_utils import (
            decompile_apk, recompile_apk, sign_apk,
        )
        from core.device_bridge import install_apk
        from core.patch_history import PatchHistory
        from patcher.watermarker import Watermarker

        # ---- STEP 1: GDA pre-analysis (optional) ----
        if use_gda:
            try:
                from scanner.gda_analyzer import GDAAnalyzer
                GDAAnalyzer().analyze(apk_path)
            except Exception as e:
                _log(f"[!] [GDA] Bỏ qua (lỗi không nghiêm trọng): {e}")
                log.warning("GDA pre-analysis failed: %s", e)

        # ---- STEP 2: APK analysis (có cache) ----
        try:
            from scanner.app_classifier import AppDeepAnalyzer
            analyzer = AppDeepAnalyzer(apk_path)
            analyzer.analyze(force_reanalyze=force_reanalyze)
            _log(f"[*] Analysis done: {analyzer.get_colors()}")
        except Exception as e:
            _log(f"[!] Analysis failed (tiếp tục): {e}")
            log.warning("Analysis failed: %s", e)
            analyzer = None

        # ---- STEP 3: Decompile ----
        needs_resources = any(m in mapped_modes for m in ("change_perms", "resign"))
        _log(f"[*] [Apktool] Decompiling (no_res={not needs_resources})...")
        decompile_apk(
            apk_path, decompiled_dir, force=True,
            no_res=not needs_resources,
            jobs=apktool_jobs, max_memory=apktool_memory,
            log_callback=_log,
        )
        _log("[*] [Apktool] Decompile done")

        # ---- STEP 4: Patch ----
        file_cache = FileContentCache(decompiled_dir)
        set_file_cache(file_cache)

        ad_activities = []
        if analyzer:
            from scanner.ad_scanner import AdScanner
            try:
                ad_activities, _ = AdScanner(apk_path).scan_manifest()
            except Exception as e:
                log.warning("Ad scan failed: %s", e)

        patches_applied, patch_reports = execute_modes(
            mapped_modes, decompiled_dir, ad_activities,
            apk_path, _log, signals,
        )
        file_cache.flush(_log)

        # ---- STEP 5: Watermark ----
        if patches_applied:
            try:
                Watermarker.add_watermark(decompiled_dir, patches_applied, apk_path)
            except Exception as e:
                log.warning("Watermark failed: %s", e)

        # ---- STEP 6: Recompile ----
        _log("[*] [Apktool] Recompiling...")
        patched_apk = os.path.join(output_dir, "patched.apk")
        recompile_apk(
            decompiled_dir, patched_apk,
            forced_package_id=forced_package_id,
            log_callback=_log,
        )
        _log("[*] [Apktool] Recompile done")

        # ---- STEP 7: Sign ----
        signed_apk = sign_apk(patched_apk, key_type=key_type, log_callback=_log)
        final_apk = os.path.join(output_dir, os.path.basename(signed_apk))
        if os.path.abspath(signed_apk) != os.path.abspath(final_apk):
            if os.path.exists(final_apk):
                os.remove(final_apk)
            os.replace(signed_apk, final_apk)
        _log(f"[✔] Output: {final_apk}")

        # ---- STEP 8: Install (optional, không fail pipeline) ----
        try:
            install_apk(final_apk)
            _log("[✔] [ADB] Installed on device")
        except Exception as e:
            _log(f"[i] [ADB] Install skipped: {e}")
            log.info("ADB install skipped: %s", e)

        # ---- STEP 9: History ----
        try:
            PatchHistory().add_record(apk_path, mode, True, final_apk, patches_applied)
        except Exception as e:
            log.warning("History save failed: %s", e)

        elapsed = time.monotonic() - t0
        summary = ", ".join(patches_applied) if patches_applied else "không có patch"
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
            import shutil
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
    parser.add_argument("apk", nargs="?", help=".apk / .xapk / folder chứa split APK")
    parser.add_argument("--mode", default="all",
                        help="Mode (comma-separated), ví dụ: 'license,ads,iap_dex'")
    parser.add_argument("--config", help="Đường dẫn YAML config (mặc định: config/default.yaml)")
    parser.add_argument("--custom-patch", help="Path tới file custom patch")
    parser.add_argument("--key-type", choices=["testkey", "platform", "media", "shared"],
                        default="testkey")
    parser.add_argument("--forced-package-id", type=int)
    parser.add_argument("--fast", action="store_true", help="Fast mode")
    parser.add_argument("--gda", action="store_true", help="GDA pre-analysis")
    parser.add_argument("--apktool-jobs", type=int)
    parser.add_argument("--apktool-memory", default="4096m")
    parser.add_argument("--clean", action="store_true", help="Xóa workspace sau khi chạy")
    parser.add_argument("--clone-package")
    parser.add_argument("--force-reanalyze", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    if not args.apk:
        parser.print_help()
        return 1

    if args.custom_patch:
        os.environ["LP_CUSTOM_PATCH"] = args.custom_patch

    from core.config import load_config
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