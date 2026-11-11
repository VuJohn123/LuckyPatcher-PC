# Changelog

## Unreleased
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
- test: full suite 1861 passed / 8 skipped; E2E `license:auto,iap:dex` on the 88 MB PairIP APK patched 43 IAP smali files (52,802 untouched), recompiled `rc=0`, signed `[v2, v3]`.

## 1.5.0
- CLI + GUI patcher (license/ads/IAP/signature/resign modes)
- Adaptive config, SafetyGuard, trace_id, pytest-qt UI tests
- Tools autodownload, XAPK/APKS convert, AIDL proxy
