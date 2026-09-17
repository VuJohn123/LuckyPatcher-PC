"""Pipeline executor — ThreadPool (I/O bound, không cần spawn)."""
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.mode_registry import get_mode_group
from core.lazy_loader import get_patcher_class

file_cache = None


def set_file_cache(cache):
    global file_cache
    file_cache = cache


def process_mode(mode_name, decompiled_dir, ad_activities, apk_path, log_callback):
    global file_cache
    result = {'patched': False, 'label': '', 'report': None}
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
                new_pkg = os.path.basename(apk_path).replace('.apk', '.clone') if apk_path else 'cloned.app'
                AppCloner(apk_path, new_pkg).clone()
                result['patched'] = True
                result['label'] = f"Cloned to {new_pkg}"
            elif mode_name == 'backup':
                import shutil
                backup_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'workspace', 'backups',
                )
                os.makedirs(backup_dir, exist_ok=True)
                shutil.copy2(apk_path, os.path.join(backup_dir, os.path.basename(apk_path)))
                result['patched'] = True
                result['label'] = "Backup created"
            return result

        # Khởi tạo patcher với file_cache
        kwargs = {'file_cache': file_cache} if file_cache else {}
        patcher = PatcherClass(decompiled_dir, log_callback=log_callback, **kwargs)

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
        log_callback(f"[!] [{mode_name}] Error: {e}")
    return result


def execute_modes(mapped_modes, decompiled_dir, ad_activities, apk_path,
                  log_callback, signals=None):
    patches_applied = []
    patch_reports = {}
    total_modes = len(mapped_modes)
    completed = 0

    parallel_modes, sequential_modes = _classify_modes(mapped_modes)

    # ---- G5: ThreadPoolExecutor thay ProcessPoolExecutor ----
    # Patcher là I/O bound (đọc/ghi smali), GIL release khi I/O.
    # ThreadPool tránh Windows spawn overhead (~3-5s/worker) và
    # không nhân bản file_cache state.
    if parallel_modes:
        max_workers = min(os.cpu_count() or 4, len(parallel_modes))
        log_callback(
            f"[*] [Executor] Parallel modes: {parallel_modes} "
            f"(workers={max_workers})"
        )
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
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
                    completed += 1
                    if signals:
                        signals.progress.emit(completed, total_modes)
                        signals.status.emit(f"Done: {mode_name}")
                except Exception as e:
                    log_callback(f"[!] [{mode_name}] Failed: {e}")
                    completed += 1

    # ---- Sequential modes ----
    for m in sequential_modes:
        try:
            result = process_mode(
                m, decompiled_dir, ad_activities, apk_path, log_callback
            )
            if result['patched']:
                patches_applied.append(result['label'])
            if result.get('report'):
                patch_reports[m] = result['report']
            completed += 1
            if signals:
                signals.progress.emit(completed, total_modes)
                signals.status.emit(f"Done: {m}")
        except Exception as e:
            log_callback(f"[!] [{m}] Failed: {e}")
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