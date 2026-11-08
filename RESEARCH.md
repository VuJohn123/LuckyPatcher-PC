# Research: Lucky Patcher (Android) → LP-PC map

Sources: luckypatchers.com feature/docs pages, tutorial methods #1-5 (IAP/LVL/ads), lp-compat LP-Tools info. DeepSeek share link login-gated, not accessible.

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
