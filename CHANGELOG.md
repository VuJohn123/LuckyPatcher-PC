# Changelog

## Unreleased
- fix(analyzer): license detection false positive on `Adjust` `LicenseData` DTO - requires real license-check method evidence (`checkLicense`, `isLicensed`, `checkAccess`, `allow`, `verify`, `licenseRequest`) for weakly named classes; strong names (`/licensing/`, `LicenseCheck`, `LicenseValidator`, `LicenseClient`, `LicenseActivity`, `LVLCheck`) accepted as-is.
- fix(analyzer): root detection false positive on SDK-only probes (GameAnalytics `GAPlatform`, Firebase `CommonUtils`, Unity Ads `Device`, BidMachine `DeviceInfo`/`DeviceUtils`, `gatewayprotocol` `hasRooted`) - hits are now attributed by owner class; SDK-owned probes report informational (`color: None`) "No - app code does not check root; only bundled SDKs probe for it (BidMachine, Firebase/Crashlytics, GameAnalytics, Unity Ads, Unity Ads bidding)" instead of red alarm.
- fix(analyzer): PairIP license finding now reports canonical package `com/pairip/licensecheck` instead of whichever inner class sorts first.
- perf(analyzer): shared structural `DexIndex` (string_ids/type_ids/method_ids parsed once) replaces per-check ASCII regex sweeps. `analyze(force)` on 84 MB / 9-dex Test.apk: **70.6 s -> 4.1 s (17.3x)**.
  - dex index build: 2.86 s (67,135 classes, 9 method owners)
  - packer: 0.42 s (reuses index)
  - license: 0.14 s (substring scan 22x faster than regex over 67k classes)
  - root/LP: 0.00 s (index already has string hits)
- perf(dex_index): candidate-name memoization in method_ids loop cuts 1.56 s -> 1.11 s; needle scan restricted to string-data region (25 MB of 62 MB) cuts 0.94 s -> 0.41 s; `classes_lower` precomputed eliminates repeated `.lower()` calls.
- perf(license): `classes_containing_any(("licens","lvl"))` substring scan replaces `_LICENSE_RE` regex (0.69 s -> 0.03 s for 67k names).
- test: regression tests for both false positives (4 license, 5 root attribution) + E2E guard relaxed from `full_scan_dt > 5.0` to `> 1.0` (old floor assumed slow path).
- lint: `ruff check src` = 0, `mypy src` = 0.
- test suite: 1918 passed, 1 failed (pre-existing UI flake in `test_ui_apk_detail_widget.py::TestRepopulate::test_populate_resets_scroll_to_top`, passes in isolation 1.69 s), 8 skipped, 182.7 s.

## Low-end device research (measured on 4-core, Python 3.11)
| metric | value | notes |
|---|---:|---|
| `import androguard.core.apk` | 0.89 s | 106 top-level modules loaded |
| `APK(Test.apk)` parse | 1.83 s | peak RSS 112 MB |
| `APK + all getters` | 2.06 s | permissions, activities, services, receivers, providers, package, version |
| `import PyQt6.QtWidgets` | 0.28 s | |
| Full analyzer startup (import) | 1.27 s | `import scanner.analyzer` |
| `orjson` vs `json` | 10.9x | orjson 46 ms / 200 dumps vs stdlib 500 ms |
| Python `-O` startup | no gain | 1.27 s both; bytecode optimizations don't offset cold cache |
| `regex` package | not installed | stdlib `re` used (fallback in `core/regex_safe.py`) |
| Binary manifest prototype | 47 ms read + 0 ms parse | Exact match on package/version/perms(25)/activities(73)/services(15)/receivers(9)/providers(13) vs androguard 1031 ms |
| Analyzer memory (Test.apk) | peak RSS 200 MB, traced 200 MB | 67k classes, 9 owners, 8 string hits; dropping `_dex_cache` leaves 94 MB |

### Low-end recommendations
1. **Use `orjson` (already present with fallback)** - 10x faster JSON I/O in cache/smali_utils.
2. **Lazy androguard import** - defer `APK` import to worker thread; saves 0.9 s cold start + 1.8 s parse on GUI load. (GUI already defers `scanner.analyzer` to `_analyze_worker`).
3. **Stdlib binary manifest parser** - 47 ms vs 1031 ms; exact field parity for analyzer needs (package, version, permissions, component counts). Can be a drop-in replacement with androguard fallback for edge cases.
4. **Consider `--no-dex-cache` flag** - dropping `_dex_cache` after indexing reduces RSS by ~100 MB (200 -> 94 MB) with no perf penalty.
5. **Keep `regex` package optional** - stdlib `re` is sufficient; the 1031 ms manifest parse is in androguard's binary XML, not regex.

## 1.5.0
- CLI + GUI patcher (license/ads/IAP/signature/resign modes)
- Adaptive config, SafetyGuard, trace_id, pytest-qt UI tests
- Tools autodownload, XAPK/APKS convert, AIDL proxy