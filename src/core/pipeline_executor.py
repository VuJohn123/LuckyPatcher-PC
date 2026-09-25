"""
Pipeline executor — ThreadPool (I/O bound, không cần spawn).

v3 (2026) — trace_id propagation:
  - `submit_with_context` cho ThreadPool → worker thread kế thừa
    trace_id từ main thread (contextvars.copy_context).
  - Log header emit `[tid:xxx]` prefix.
  - Per-mode timing giữ nguyên.

v2 fixes:
  - Adaptive strategy (fast/balanced/careful/paranoid).
  - Per-mode timing metric.
"""
from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.mode_registry import get_mode_group
from core.lazy_loader import get_patcher_class
from core.trace_context import (
    get_trace_id,
    prefix_with_trace,
    submit_with_context,
)

logger = logging.getLogger(__name__)

# Module-level state (giữ backward compat với caller cũ)
file_cache = None
_strategy = "balanced"


def set_file_cache(cache):
    global file_cache
    file_cache = cache


def set_strategy(strategy: str) -> None:
    """Set runtime strategy — ảnh hưởng patcher behavior."""
    global _strategy
    _strategy = strategy or "balanced"
    # Bridge sang env var cho patchers đọc (loose coupling)
    os.environ["LP_STRATEGY"] = _strategy
    if _strategy in ("careful", "paranoid"):
        os.environ["LP_IAP_FULL_SCAN"] = "1"
        logger.info(
            "Strategy=%s → ép FULL scan cho IAPSmali", _strategy
        )


def get_strategy() -> str:
    return _strategy


# ============================================================
# PROCESS ONE MODE
# ============================================================
def process_mode(mode_name, decompiled_dir, ad_activities,
                 apk_path, log_callback):
    global file_cache
    result = {'patched': False, 'label': '', 'report': None,
              'duration': 0.0}
    t0 = time.monotonic()
    try:
        PatcherClass = get_patcher_class(mode_name)
        if PatcherClass is None:
            # Fallback: các mode không cần patcher
            if mode_name == 'save_purchase':
                from patcher.iap_manager import IAPManager
                IAPManager().save_for_restore_enabled = True
                result['patched'] = True
                result['label'] = "Save purchase enabled"
            elif mode_name == 'auto_repeat':
                from patcher.iap_manager import IAPManager
                IAPManager().auto_repeat_enabled = True
                result['patched'] = True
                result['label'] = "Auto-repeat enabled"
            elif mode_name == 'clone':
                from patcher.app_cloner import AppCloner
                new_pkg = (
                    os.path.basename(apk_path).replace('.apk', '.clone')
                    if apk_path else 'cloned.app'
                )
                AppCloner(apk_path, new_pkg).clone()
                result['patched'] = True
                result['label'] = f"Cloned to {new_pkg}"
            elif mode_name == 'backup':
                import shutil
                backup_dir = os.path.join(
                    os.path.dirname(os.path.dirname(
                        os.path.abspath(__file__)
                    )),
                    'workspace', 'backups',
                )
                os.makedirs(backup_dir, exist_ok=True)
                shutil.copy2(
                    apk_path,
                    os.path.join(backup_dir, os.path.basename(apk_path)),
                )
                result['patched'] = True
                result['label'] = "Backup created"
            result['duration'] = time.monotonic() - t0
            return result

        # Khởi tạo patcher với file_cache
        kwargs = {'file_cache': file_cache} if file_cache else {}
        patcher = PatcherClass(
            decompiled_dir, log_callback=log_callback, **kwargs
        )

        # Gọi phương thức patch
        if mode_name == 'ads':
            cnt = patcher.remove_activities(ad_activities)
        elif hasattr(patcher, 'patch'):
            cnt = patcher.patch()
        elif hasattr(patcher, 'patch_license_check'):
            cnt = patcher.patch_license_check()
        elif hasattr(patcher, 'execute_with_report'):
            result['report'] = patcher.execute_with_report()
            cnt = result['report'].get('total_patched', 0)
        else:
            cnt = 0

        if cnt > 0:
            result['patched'] = True
            result['label'] = (
                f"{mode_name} ({cnt} files)"
                if isinstance(cnt, int) else mode_name
            )
    except Exception as e:
        log_callback(prefix_with_trace(
            f"[!] [{mode_name}] Error: {e}"
        ))
        logger.exception("process_mode failed")
    finally:
        result['duration'] = time.monotonic() - t0
    return result


# ============================================================
# EXECUTE ALL MODES
# ============================================================
def execute_modes(mapped_modes, decompiled_dir, ad_activities,
                  apk_path, log_callback, signals=None,
                  strategy: str | None = None):
    """
    Run all modes. strategy optional — nếu None dùng _strategy global.

    v3: parallel worker threads propagate trace_id qua
    `submit_with_context` → log từ patcher có prefix [tid:xxx].
    """
    if strategy is not None:
        set_strategy(strategy)

    patches_applied = []
    patch_reports = {}
    total_modes = len(mapped_modes)
    completed = 0

    parallel_modes, sequential_modes = _classify_modes(mapped_modes)

    if parallel_modes:
        max_workers = min(os.cpu_count() or 4, len(parallel_modes))
        log_callback(prefix_with_trace(
            f"[*] [Executor] Parallel modes: {parallel_modes} "
            f"(workers={max_workers}, strategy={_strategy}, "
            f"trace={get_trace_id()})"
        ))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # submit_with_context copy contextvars từ caller thread
            # → worker kế thừa trace_id.
            futures = {
                submit_with_context(
                    executor,
                    process_mode, m, decompiled_dir, ad_activities,
                    apk_path, log_callback,
                ): m
                for m in parallel_modes
            }
            for future in as_completed(futures):
                mode_name = futures[future]
                try:
                    result = future.result()
                    if result['patched']:
                        patches_applied.append(result['label'])
                    if result.get('report'):
                        patch_reports[mode_name] = result['report']
                    log_callback(prefix_with_trace(
                        f"[i] [Executor] {mode_name} done "
                        f"({result['duration']:.1f}s)"
                    ))
                    completed += 1
                    if signals:
                        signals.progress.emit(completed, total_modes)
                        signals.status.emit(f"Done: {mode_name}")
                except Exception as e:
                    log_callback(prefix_with_trace(
                        f"[!] [{mode_name}] Failed: {e}"
                    ))
                    completed += 1

    for m in sequential_modes:
        try:
            result = process_mode(
                m, decompiled_dir, ad_activities, apk_path, log_callback
            )
            if result['patched']:
                patches_applied.append(result['label'])
            if result.get('report'):
                patch_reports[m] = result['report']
            log_callback(prefix_with_trace(
                f"[i] [Executor] {m} done ({result['duration']:.1f}s)"
            ))
            completed += 1
            if signals:
                signals.progress.emit(completed, total_modes)
                signals.status.emit(f"Done: {m}")
        except Exception as e:
            log_callback(prefix_with_trace(
                f"[!] [{m}] Failed: {e}"
            ))
            completed += 1

    return patches_applied, patch_reports


def _classify_modes(mapped_modes):
    parallel_modes = []
    sequential_modes = []
    used_groups = set()
    for m in mapped_modes:
        group = get_mode_group(m)
        if group and group not in used_groups:
            parallel_modes.append(m)
            used_groups.add(group)
        elif not group:
            parallel_modes.append(m)
        else:
            sequential_modes.append(m)
    return parallel_modes, sequential_modes