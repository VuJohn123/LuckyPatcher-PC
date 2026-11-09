# Changelog

## Unreleased
- fix(signature): Pass 3 (`getPackageInfo` flag injection) is line-anchored; it no longer binds an unrelated `const` or re-emits `invoke-virtual {...}`, and emits valid `const`/`const/high16` literals.
- fix(signature): `checkSignatures`/`MessageDigest.isEqual` patches widen to `const/16` for registers above v15 and parameter registers.
- fix(iap): `iap:dex` and `iap:proxy` now route to their distinct `IAPBypass` modes instead of both running proxy mode.
- fix(iap): `INAPP_PURCHASE_DATA_LIST` is published as a `StringArrayList` (was `putInt`, breaking `getStringArrayList`).
- fix(iap): proxy-mode `IAPSmaliPatcher` accepts and writes through the pipeline `FileContentCache`.
- fix(pipeline): IAP runs surface `execute_with_report()` metrics in the pipeline summary (previously shadowed by `patch()`).

## 1.5.0
- CLI + GUI patcher (license/ads/IAP/signature/resign modes)
- Adaptive config, SafetyGuard, trace_id, pytest-qt UI tests
- Tools autodownload, XAPK/APKS convert, AIDL proxy
