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
