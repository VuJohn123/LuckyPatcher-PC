# Research: Lucky Patcher (Android) → LP-PC map

Sources: luckypatchers.com, patch.chelpus.com (custom-patch cloud DB), Freezdy413485/LP-GUI (screenshot deep-report, 16p), LP-DeCodes (LP 12.10.4 binaries). DeepSeek share gated.

## Original LP methods (root + no-root)
- IAP/LVL: modded Play Store patch, support patch (DEX/AIDL proxy), proxy server, saved purchases, auto-repeat, APK rebuild.
- Ads: Remove Google Ads, remove links, break receiver, full offline, hosts block.
- License: emulate / reverse / extreme / amazon / samsung / manual; signature disable, integrity remove, fake archive.
- Toolbox: permissions change, clone, cloud patch, hosts, busybox, APK installer, app icons, fake package, install dir.
- Custom patches: user-submitted patch files + downloader.

## Our coverage (39 modes)
License (7) + Ads (5) + IAP (4) + Signature (4+3) + Resign (7) + clone/backup/save_purchase/auto_repeat/cloud_patch/gms_spoof/event_logger/perms — all present with patchers + UI dialogs + tests.

## Gaps closed
- `fake_pkg` (`patcher/fake_package_patcher.py`), `install_dir` (`install_dir_patcher.py`), `hosts_block` (`hosts_blocker.py`) — implemented + tested, wired via `lazy_loader` + `mode_registry`.
- Play Store modded-patch: N/A on PC (needs root) — executor degrades gracefully with guidance to `iap:dex`/`iap:proxy`, never crashes.

## Verdict
Static-PC parity achieved for license/ads/IAP/signature/resign/clone. No further code gaps worth adding without diluting stability.

---

## Deep core-feature study (LP-GUI + LP-DeCodes + patch.chelpus.com)

LP core work modes (from screenshot analysis):
1. **Color-coded scan:** green=LVL/IAP, blue=Ads, yellow=custom patch, orange/purple=system, red=anti-LP, clover=patched, star=ODEX changed. → Ours: `ui/color_indicator.py` + analyzer colors. ✓
2. **License:** auto (dontAllow→void), reverse, extreme (bytecode pattern vs obfuscation), amazon/samsung native SDKs. → Ours: license_patcher/extreme. ✓
3. **IAP:** support-patch injects `IInAppBillingService` stub, intent `com.android.vending`→LP pkg, `Security.verify→true`; proxy server; modded Play; IAPManager persistence. → Ours: iap_dex/proxy + manager. ✓
4. **Ads:** remove links via `AdsBlockList[_user_edit].txt`, break receiver, fake-offline `isNetworkAvailable→false`, full-offline, remove-dependency. → Ours: ad_remover/ads_blocklist + hosts_block. ✓
5. **Signature:** disable-verify (code inject), integrity-remove (doubles size), fake-archive (ZIP header), resign-original. → Ours: signature_* 3 patchers. ✓
6. **Custom patches:** `[file] orig -> repl` with `**` masked operands, cloud DB via patch.chelpus.com (Submit Patch / Apps / Games), LPDiff diff tool, multi-patch, BootList re-apply on reboot, manual patcher. → Ours: custom_patch + downloader + lpdiff_analyzer + multi_patch_combiner + bootlist. ✓
7. **Rebuild pipeline:** fetch → dex reassembly (classes.dex..n) → patch → zip package → split zipalign → sign. → Ours: main pipeline + converters. ✓
8. **Toolbox/switches updatable:** toggles (fake-payment, proxy), saved-purchase cleanup, backup, reinstall, APK installer; settings import/export, rescan. → Ours: switches_panel + toolbox_menu + patch_history. ✓
9. **Limitations to respect (no crash):** server-side verify, Play Integrity, native .so ads, WebView dynamic URLs, strong obfuscation — degrade with warnings, never fake success. → Ours: packer warning + signed/original-sig guards. ✓

LP-DeCodes confirms version 12.10.4 + standalone proxy server APK (covered by our ws/iap proxy servers). No additional gap found.

---

## LP-GUI + LP-DeCodes Deep Architecture Study (completed 2026-11-14)

### Original LP 12.10.4 Architecture (4 Layers)

| Layer | Description | Components | LP-PC Status |
|-------|-------------|------------|--------------|
| **0. OS / Framework** | Modifies `services.jar`, `framework.jar`, `android.policy.jar` | ODEX patching, Modified Play Store (replaces Play services), Patch to Android (system sig check), BootList (re-apply patches on boot), Widgets (home screen) | ❌ Requires ADB + root; **future work** |
| **1. System / App** | Modified Play Store APK (signed with platform key), standalone billing proxy APK | `com.chelpus.lackypatch.LackyPatchService`, IAP proxy server | ✅ Layer 2 covered (DEX/AIDL proxy); Layer 1 needs ADB install |
| **2. App / Static** | Smali-level patches: license (auto/reverse/extreme/amazon/samsung), IAP (support patch), Ads (blocklist/manifest/offline), Signature (disable/integrity/fake-archive), Custom patches (hex/structural), Fake pkg, Install dir, Hosts block | 39 modes implemented | ✅ **Complete parity** |
| **3. Runtime / Hook** | Xposed/Zygisk module (min version 82), `XSupport` hooks | Signature (8), Install (3), IAP (4), License (3) = 19 hooks | ✅ Generator produces valid LSPosed module |

### Key LP-DeCodes Findings (v12.10.4)

- **Package**: `ru.aaaaaban.installer` → obfuscated to `ru.hhklsyty.wlkllqrcq` in release
- **Keystore keys**: `tools/keys/{testkey,platform,shared,media}.{pk8,x509.pem}` — our placeholders must be replaced with real AOSP keys for platform/media/shared signing
- **AIDL interfaces**: Full `IInAppBillingService` (8 methods) + licensing AIDL in `android/com/android/vending/licensing/`
- **Xposed module meta-data**: `xposedmodule=true`, `xposedminversion=82`, `xposedscope` via `@array/xposed_scope`
- **Custom patch cloud**: `patch.chelpus.com` — Apps/Games/Submit Patch endpoints (our `cloud_patch_downloader.py` covers protocol)
- **BootList mechanism**: Writes to `/data/local/tmp/lp_bootlist.sh` executed via `init.d` or Magisk module — requires root
- **ODEX patching**: `baksmali`/`smali` on `boot.oat` / `odex` files — live patching without rebuild, needs ADB shell

### ADB-Based Port Plan (Future Work)

| Feature | ADB Approach | Blockers |
|---------|-------------|----------|
| ODEX/Dalvik-cache patching | `adb shell` + `baksmali`/`smali` on device | Requires root, device-specific oat format |
| Modified Play Store | `adb install -r` platform-signed APK | Needs platform key, signature verification |
| Patch to Android (services.jar) | `adb pull` → patch → `adb push` + reboot | System partition r/w, SELinux, OTA survival |
| BootList re-apply | `adb shell` script in `init.d` / Magisk | Root, persistent across OTA |
| Widgets | `adb shell` broadcast to LP app | LP app must be installed |
| lpzip (custom patch archive) | `adb push` + LP app intent | LP app dependency |
| Xposed module install | `adb install` LSPosed module zip | LSPosed installed, scope config |

---

## Low-end device optimization research (measured 2026-11-14)

### Measured costs on 4-core, Python 3.11, 84 MB / 9-dex Test.apk
| operation | time | memory | notes |
|---|---:|---:|---|
| `import androguard.core.apk` | 0.89 s | 20 MB | loads 106 top-level modules (lxml, cryptography, loguru, apkinspector, asn1crypto, ...) |
| `APK(Test.apk)` parse | 1.83 s | 112 MB RSS | full binary manifest + resource parsing |
| `APK + all getters` | 2.06 s | 116 MB | permissions(25), activities(73), services(15), receivers(9), providers(13), package, version, app_name |
| `import PyQt6.QtWidgets` | 0.28 s | | |
| `import scanner.analyzer` | 1.27 s | | includes DexIndex, security/license/iap/packer checks |
| `orjson.dumps` x200 | 46 ms | | vs stdlib `json.dumps` 500 ms (10.9x) |
| Python `-O` startup | no gain | | 1.27 s both; bytecode opt doesn't offset cold import |
| `regex` package | not installed | | stdlib `re` used (`core/regex_safe.py` fallback) |
| **Binary manifest (stdlib prototype)** | **47 ms read + 0 ms parse** | | **Exact match** on all fields vs androguard 1031 ms |
| Analyzer full run | 4.1 s | peak 200 MB RSS | 67k classes, 9 method owners, 8 string hits |
| Without `_dex_cache` | | 94 MB RSS | drops 106 MB; no perf penalty |

### Optimization recommendations for low-end devices
1. **Keep `orjson` with stdlib fallback** (already in `core/smali_utils.py`) — 10x faster cache I/O.
2. **Lazy androguard import** — GUI already defers `scanner.analyzer` to worker thread; moves 0.9 s + 1.8 s off cold start. Background download/install paths should also import lazily.
3. **Adopt stdlib binary manifest parser** — 47 ms vs 1031 ms; exact field parity for analyzer's needs (package, version, permissions, component counts). Can wrap with androguard fallback for edge cases (APKs with unusual manifests).
4. **Optional `--no-dex-cache` / `drop_dex_after_index`** — after building `DexIndex`, clearing `_dex_cache` frees ~100 MB RSS (200 → 94 MB) with no analyze-time cost.
5. **Keep `regex` package optional** — the 1031 ms manifest parse is in androguard's binary XML, not regex. stdlib `re` is sufficient.
6. **Consider PyPy on Linux** — not applicable on Windows; on Linux the JIT can make the pure-Python `DexIndex` even faster.

### Files touched by this research
- `src/core/smali_utils.py` — orjson/json selection logic
- `src/scanner/analyzer.py` — lazy androguard already implemented (deferred to `_analyze_worker`)
- `src/scanner/dex_index.py` — pure-Python structural index (no androguard dependency)
- `src/scanner/checks/*.py` — all checks accept `index=` kwarg, no androguard in fast path
