# Changelog

## Unreleased
- perf(e2e): `license:auto,iap:dex` on the 84 MB PairIP APK now completes in **469.7s** on the steady-state run with a reused workspace (baseline 998.3s, 2.1x); a run from a stale workspace still took 847.7s. Identical output contract: 53 pattern keys, 43 files patched, 52,845 scanned, 0 skipped, 84.8 MB, signed `[v2, v3]`.
- perf(recompile): `recompile_apk()` accepts an explicit `jobs` value; the pipeline now builds with `min(16, max(4, cpu×2))` (8 on the 4-core audit machine) instead of apktool's 1-per-CPU default. Pristine-tree builds with no `build/` reuse (the real pipeline always purges it): 4 jobs 323.3s / 280.4s (mean 301.9s) → 8 jobs 249.4s / 236.3s (mean 242.9s); E2E recompile 359.8s → 278.3s. Same 84.7 MB / 9 dex output.
- perf(cache): loading a cache into an existing workspace now uses an incremental `robocopy /PURGE` mirror instead of delete + full copy. On the 54,508-file tree: 159.5s → 12.4s (12.9x); E2E steady-state cache load 112.1s → 2.7s. All 43 modified files were restored, the stale file removed, and file counts matched. `/PURGE` also discards stale apktool `build/` artifacts. Default config keeps the workspace (`pipeline.keep_workspace: true`).
- perf(license): path prefilter no longer uses `pro` as a substring — 5,134 of 6,308 candidates were `$proxy`/provider files. Boundary/CamelCase regexes keep `ProManager` while excluding `Proxy`: candidates on the 84 MB test APK drop to 1,907 (3.3x fewer cold reads); E2E license 363.8s → 78.8s.
- perf(iap): `iap:dex` rejects blacklist-only paths before reading (2,350 of 52,830 smali files on the test APK) and uses 16–32 scan workers (32 on 4 CPUs) instead of 8. Cold-read benchmark: 8.5ms → 5.4ms per file; E2E scan 417.9s → 144.8s.
- perf(startup): `AppController` no longer imports `scanner.app_classifier` (androguard) or `core.apk_downloader` (requests/urllib3) at module load; both are deferred to `_analyze_worker` and the download dialogs. Warm `import run_gui`: **1,493ms → 574ms** (3 runs each, −62%); CLI `import main` stays at ~550–575ms. `IAPManager` and `get_installed_apps` remain eager because tests patch `ui.app_controller` module attributes; `permission_picker_dialog` keeps its top-level `APK` import because the dialog is already loaded lazily and tests patch that symbol.
- perf(ads): LP blocklist matching now groups escaped literals into `(?:...)` alternation chunks (≤800 chars), so a file gets 2 URL regex passes instead of 69 and 1 string pass instead of 16; the string pass also uses the blocklist as a prefilter. On 3,000 real smali files: URL 3.95s → 0.55s (7.2x), strings 1.19s → 0.18s (6.4x), identical output digest. New tests cover multi-domain removal and exact-literal removal.
- test(suite): a module-scoped `analyzed_apk` fixture shares one full PairIP analysis across the read-only real-APK E2E checks; cache round-trip tests still run their own scans. Full suite: **1886 passed / 8 skipped in 280.3s** (was 1884 / 8 in 1230s, 4.4x).
- test: regression coverage for license `Proxy` vs `ProManager`, IAP pre-read blacklist skip, robocopy `/PURGE`, incremental vs fresh cache load, and recompile `--jobs`; full suite **1884 passed / 8 skipped in 1230s**.
- perf(iap): `iap:dex` prefilter now scans smali files with a bounded thread pool (IAPDexPatcher), overlapping Windows Defender first-touch scans. E2E on the 84 MB PairIP APK: scan 1457.6s → 417.9s, whole run 2688s → 998.3s, with an identical result (same 53 pattern keys, 43 files patched, 52,845 scanned, 0 skipped).
- fix(safety): sustained RAM pressure in CLI mode now hard-aborts the pipeline instead of auto-muting and resuming full load; new `auto_tune.safety.cli_abort_reasons` (default `[ram]`) overrides `cli_mode_action` per reason, and the pipeline checks the abort flag again after recompile before signing.
- chore(ci): pin `ruff==0.16.8` / `mypy==2.3.1`; CI now also enforces `mypy src`.
- chore: `ruff check src` and `mypy src` are both clean (0 findings / 0 errors).
- fix(cache): decompile cache is now keyed by decode profile (`_full` / `_nores`), so a no-res tree can never be reused by resource-requiring modes; the save path records the profile actually decoded.
- fix(iap): `IAPDexPatcher` skips `abstract`/`native` method headers — injecting instructions there made apktool fail with `An abstract method cannot have any instructions`.
- fix(pipeline): invalid patcher smali now raises `SmaliAssemblyError` with the offending file; the pipeline no longer wastes a full re-decompile/repatch on it.
- fix(logs): Java subprocess failures log `[✘] ... (rc=N)` instead of a success checkmark.
- fix(signature): Pass 3 (`getPackageInfo` flag injection) is line-anchored; it no longer binds an unrelated `const` or re-emits `invoke-virtual {...}`, and emits valid `const`/`const/high16` literals.
- fix(signature): `checkSignatures`/`MessageDigest.isEqual` patches widen to `const/16` for registers above v15 and parameter registers.
- fix(iap): `iap:dex` and `iap:proxy` now route to their distinct `IAPBypass` modes instead of both running proxy mode.
- fix(iap): `INAPP_PURCHASE_DATA_LIST` is published as a `StringArrayList` (was `putInt`, breaking `getStringArrayList`).
- fix(iap): proxy-mode `IAPSmaliPatcher` accepts and writes through the pipeline `FileContentCache`.
- fix(pipeline): IAP runs surface `execute_with_report()` metrics in the pipeline summary (previously shadowed by `patch()`).
- test: full suite 1877 passed / 8 skipped; E2E `license:auto,iap:dex` on the 88 MB PairIP APK patched 43 IAP smali files (52,802 untouched), recompiled `rc=0`, signed `[v2, v3]`.

## 1.5.0
- CLI + GUI patcher (license/ads/IAP/signature/resign modes)
- Adaptive config, SafetyGuard, trace_id, pytest-qt UI tests
- Tools autodownload, XAPK/APKS convert, AIDL proxy
