# 📚 KNOW — Lucky Patcher Mechanics & LP-PC Suite (v5 — dense reference)

Reference for contributors. **Every claim below is grounded in this project's
source or LP 12.10.4 research** (`Freezdy413485/LP-DeCodes`, `Freezdy413485/LP-GUI`).
Cross-reference `HANDOFF*.txt` for project state, `src/tests/` for behavioural
contracts (tests are the spec).

**Test baseline**: 1884 passed, 8 skipped, 0 failed. Cache v10.

---

## 0. Big picture

LP-PC Suite reimplements LP's **static** patch side on PC (Python 3.11 + PyQt6)
and generates **Xposed modules** for the runtime side. It is not a network MITM
tool; "proxy" in LP/this project means an **app-side AIDL shim** for Google
Play Billing.

| Capability | Static (smali/dex) | Runtime (Xposed) | Reliable on packed APK |
|---|---|---|---|
| License removal | ✅ primary | ✅ hook `dontAllow`/`verify` | ❌ |
| IAP emulation | ⚠️ DEX heuristic | ✅ hook `BillingClient.*` + AIDL proxy | ❌ |
| Ads removal | ✅ manifest + strings | — | ⚠️ (partial) |
| Signature bypass | ✅ 8 targets | ✅ 8 hooks + spoof | ⚠️ (static ok, spoof better) |
| Signature integrity (anti-tamper) | ✅ string/method patch | ✅ hook `isVerified` | ⚠️ |

**Packed APK (PairIP, Tencent, 360, …)**: real logic lives in native `.so`; smali
patch matches 0 files, logs "success", game stays locked. Detect via
`analyzer.packer_info` and refuse/warn. That is the #1 silent-failure mode.

---

## 1. License verification (LVL)

### 1.1 Class map (Android LVL)

```
LicenseChecker           — client wrapper, binds LicensingService
LicenseValidator         — AIDL callback impl, calls policy
ServerManagedPolicy      — retry policy, calls callback
StrictPolicy             — minimal retry
LicenseCheckerCallback   — app-side: allow(ResponseData) / dontAllow(int)
```

Response codes (`LicenseValidator`): `0=LICENSED, 1=NOT_LICENSED, 2=RETRY,
3=SERVER_ERROR, 4=NOT_MARKET_MANAGED, 5=LICENSED_OLD_KEY, 6=ERROR_NOT_LICENSED,
7=ERROR_INVALID_PACKAGE_NAME, 8=ERROR_NON_MATCHING_UID, 9=ERROR_NOT_AUTHENTICATED`.

### 1.2 Three static patches (LP parity)

**Auto (patch `verify`)** — highest success rate on stock LVL apps:
```smali
.method public verify(...)V
    .registers N
    const/4 vX, 0x0        # LICENSED instead of LICENSED/error
    # → policy will call callback.allow()
```

**Reverse (patch `dontAllow`)** — replace all
`invoke-interface {vX}, L…/LicenseCheckerCallback;->dontAllow(I)V` with
`invoke-interface {vX}, L…/LicenseCheckerCallback;->allow(L…/ResponseData;)V`.
Requires constructing a dummy `ResponseData(0, null, null)` — safer via
`const/4 vA, 0x0` + reflection.

**Extreme (bytecode pattern)** — inverse auto: find `dontAllow` callers and
NOP them entirely, then pre-fill `LicenseChecker.mCheckerCallback` with a stub.
Used when caller hides behind obfuscation.

### 1.3 Amazon DRM (`com.amazon.venezia`)
Entry `LicenseEnforcementService` (AIDL); callback `LicenseResultReceiver`.
Return codes: `LICENSE_OK=0`, `LICENSE_FAILED=1`. Patch return constant.

### 1.4 Samsung Apps (`com.sec.android.app.samsungapps`)
Return `SamsungLicenseResult.OK`. Packed apps often verify via Play Integrity
after Samsung check → double failure mode.

### 1.5 Detection contract (`scanner/checks/license_check.py`)
- Class name match: `(license|licensing|lvl|LicenseCheck|LicenseValidat)` (case-insens)
- Skip blacklist: `OfflineLicenseHelper, LicenseManager, BidToken, Moloco,
  ImpLvlRevData, ClientBidToken, LicensingListener`
- Method hints: `(checkAccess|allow|verify|checkLicense|isLicensed)`
- **PairIP** → emit `type=license_packed`, color=red, **do not** add `license` to
  available patches (unpatchable)
- Manifest fallback: activities matching `license` (except `exoplayer`) → finding.
- Fast path: ASCII regex on raw dex (bytes ≥ 1 KB), androguard fallback for
  test mocks < 1 KB.

---

## 2. IAP — Google Play Billing

### 2.1 `IInAppBillingService` AIDL (all 8 must be handled)

```
isBillingSupported(int, String, String)                    → int
getSkuDetails(int, String, String, Bundle)                 → Bundle
getBuyIntent(int, String, String, String, String)          → Bundle
getPurchases(int, String, String, String)                  → Bundle
consumePurchase(int, String, String)                       → int
getBuyIntentToReplaceSkus(int, String, List, String, String, String) → Bundle
getBuyIntentExtraParams(int, String, String, String, String, Bundle) → Bundle
getPurchaseHistory(int, String, String, String, Bundle)    → Bundle
```

Any missing method → `RESPONSE_CODE=ServiceUnavailable` → app shows error.

**Bundle keys**: `RESPONSE_CODE` (0=OK, 1=user cancel, 2=svc unavailable,
3=billing unavailable, 7=already owned), `INAPP_PURCHASE_ITEM_LIST`,
`INAPP_PURCHASE_DATA_LIST`, `INAPP_DATA_SIGNATURE_LIST`, `BUY_INTENT`.
Response code 0 required even on `consumePurchase` failure or app retries loop.

### 2.2 The `com.chelpus.lackypatch` proxy

LP's trick: repoint billing Service ComponentName to
`com.chelpus.lackypatch.LackyPatchService`, which implements all 8 AIDL actions
returning canned bundles. Installed on-device separately (LP ships the APK).

Fake receipt shape (must be schema-valid JSON):
```json
{"orderId":"GPA.0000-0000-0000-00000","packageName":"com.x",
 "productId":"com.x.premium","purchaseTime":1234567890000,
 "purchaseState":0,"purchaseToken":"lppc_fake_<sku>",
 "acknowledged":true,"autoRenewing":false}
```

Signature verification is defeated by patching `Security.verifyPurchase`
(a common static helper) to `return true`. Without this, most modern apps reject
the fake receipt.

### 2.3 Unity IAP
Packages: `com.unity.purchasing.` (v4+), `com.unity3d.purchasing.` (v3).
Flow: `UnityPurchasing.Initialize` → `IStoreListener.OnInitialized` →
`IStoreController.PurchaseProduct` → `IStoreListener.ProcessPurchase`.
Patcher: force `IsInitialized()` true + inject `OnPurchaseSucceeded` call in
`ProcessPurchase` before original logic (return early).

### 2.4 Detection (`scanner/checks/iap_check.py`)
1. Manifest `com.android.vending.BILLING` → hit, return immediately.
2. DEX fast scan for any of:
   `com/android/billingclient/api/BillingClient`, `IInAppBillingService`,
   `com/unity3d/purchasing/`, `com/unity/purchasing/`,
   `Lcom/unity3d/plugin/`, `IStoreListener`, `UnityPurchasing`,
   `com/android/vending/billing/`.

### 2.5 Why proxy alone often fails
`Intent("com.android.vending.billing.InAppBillingService.BIND")` resolves to
**Google Play Services** (priority over 3rd-party on normal devices). The only
reliable way to intercept is Xposed-hooking `BillingClient` methods directly,
or patching `PackageManager.setComponentEnabledSetting` to disable GMS's billing
service (needs root). LP-PC Suite's Xposed path is the correct one; AIDL proxy
is a fallback that works on de-Googled / GMS-renamed devices.

---

## 3. Ads removal

### 3.1 Three layers (LP parity)

**Manifest**: remove activity entries for ~40 SDKs — AdMob (`com.google.android.gms.ads.AdActivity`),
FAN (`com.facebook.ads.InterstitialAdActivity`), Unity (`com.unity3d.ads.adunit.AdUnitActivity`,
`com.unity3d.services.ads.adunit.AdUnitActivity`), AppLovin, MoPub,
Chartboost, Ironsource, Vungle, InMobi, Flurry, Mintegral, Pangle, Amazon
Ads, Tapjoy. Also drop corresponding `<meta-data>` (`com.google.android.gms.ads.APPLICATION_ID`).
Removing manifest alone is partial (SDK silently no-ops).

**String replacement (`[ALL_STRINGS]`)** — LP embeds thousands of ad host substrings;
patcher scans DEX strings and replaces with `""`. Works only for SDKs that do
string comparison at runtime. Fastest, least invasive. **LP-PC Suite implements
this, warns `[HTTP]` requires root**.

**Init bypass**: patch `MobileAds.initialize(Context, …)` → `return-void`;
`AdRequest.Builder.build()` → `return null`; `InterstitialAd.loadAd(...)` →
immediate `onAdFailedToLoad(LoadAdError(0, "offline", "offline", null))`.
Requires per-SDK method knowledge; only implement for top 10 SDKs.

### 3.2 Offline mode
`ads:offline` / `ads:full_offline`: patch
`ConnectivityManager.getActiveNetworkInfo().isConnected()` → `false` and
`NetworkInfo.getType()==TYPE_WIFI` → false. Many SDKs skip loading. **Breaks
all networking**. Use only on offline-capable apps.

### 3.3 Detection (`scanner/checks/ads_check.py`)
Manifest only: `com.google.android.gms.ads.APPLICATION_ID` → AdMob; FAN keys
(`com.facebook.sdk.ApplicationId`, `AutoLogAppEventsEnabled`); Unity
(`unityplayer.UnityActivity` + `unity3d.ads.*` strings);
`com.android.vending.BILLING` alone is **not** ads.

---

## 4. Signature bypass (deep)

### 4.1 Android signing layers
v1 (JAR `META-INF/CERT.RSA`+`.SF`+`MANIFEST.MF`), v2 (APK Signature Scheme,
appended before ZIP Central Directory), v3 (key rotation + proof-of-rotation),
v4 (streaming). LP-PC Suite re-signs with testkey → **all layers rotate**.

### 4.2 What breaks after re-sign
1. `PackageManager.checkSignatures(p1, p2)` → returns `SIGNATURE_MISMATCH (-3)`.
2. `getPackageInfo(...).signatures` → different cert.
3. Play Integrity / SafetyNet server verdicts → fail. **Out of scope**
   (same limitation as LP).

### 4.3 Static patch targets (8)

| Target | Patch |
|---|---|
| `PackageManager.checkSignatures(String, String)` | return `0` |
| `PackageManager.checkSignatures(int, int)` | return `0` |
| `PackageManager.getPackageInfo(String, int)` | null `.signatures[]` |
| `SigningDetails.checkCapability(…)` | return `true` |
| `SigningDetails.hasAncestorOrSelf(…)` | return `true` |
| `ApkSignatureVerifier.verifySignatures(…)` | force `isVerified=true` |
| `PackageManagerServiceUtils.verifySignatures(…)` | return `true` |
| `ScanPackageUtils.getMinimumSignatureSchemeVersionForTargetSdk(…)` | return `0` |

### 4.4 The 0x80 flag
Two distinct meanings depending on context:
- `PackageManager.INSTALL_ALLOW_DOWNGRADE = 0x80` (install flags)
- `PackageParser.PARSE_IGNORE_PACKAGE_INSTALLED = 0x80` (parse flags)

LP's "Patch to Android" modifies `PackageManagerService` to accept mismatched
signatures (root). LP-PC Suite only uses 0x80 in the app-side `PackageInstaller`
flow (rare). Do not conflate with `INSTALL_REPLACE_EXISTING = 0x02`.

### 4.5 Anti-tamper / anti-root / anti-Frida (integrity patcher)
String scan + method patch: `RootBeer.*`, `SafetyNet.*`, `PlayIntegrity.*`,
`isDebuggerConnected()` → false, `Debug.isDebuggerConnected()` → false,
strings `frida`, `xposed`, `/proc/self/maps`, `getprop ro.build.tags` → "release-keys"
via replacing test-keys check with constant. For `System.getProperty(...)`-based
detection, patch the caller, not the property read.

---

## 5. Xposed / LSPosed module (LP parity)

### 5.1 Generated module layout
```
xposed_module/
  AndroidManifest.xml          (xposedmodule=true, xposedminversion=82,
                                 xposedscope=@array/xposed_scope, minSdk 24, targetSdk 34)
  assets/xposed_init           (single line: com.lppc.xposed.hooks.XposedEntry)
  res/values/arrays.xml        (<string-array name="xposed_scope"><item>com.target</item></string-array>)
  smali/com/lppc/xposed/hooks/
    XposedEntry.smali
    SignatureHook.smali  + SignatureHook$0..$7.smali
    InstallHook.smali    + InstallHook$0..$2.smali
    IAPHook.smali        + IAPHook$0..$3.smali
    LicenseHook.smali    + LicenseHook$0..$2.smali
  README.md
```

Compile: `java -jar tools/bin/smali.jar assemble -a 24 xposed_module/smali -o classes.dex`
then zip `classes.dex + AndroidManifest.xml + assets/xposed_init + res/values/arrays.xml`.

### 5.2 Hook target table (19 hooks, from `_HOOK_TARGETS`)

Signature (8):
```
PackageManager.checkSignatures(String,String)            return_zero
PackageManager.getPackageInfo                            after_signature_spoof
SigningDetails.checkCapability                           return_true
SigningDetails.hasAncestorOrSelf                         return_true
ApkSignatureVerifier.verifySignatures                    after
com.android.apksig.ApkVerifier.<init>                    after
PackageManagerServiceUtils.verifySignatures              after
ScanPackageUtils.getMinimumSignatureSchemeVersionForTargetSdk  return_zero
```
Install (3): `PackageManagerService.<init>`, `InstallPackageHelper.installPackagesLI`,
`InstallPackageHelper.preparePackage` — all `after`.
IAP (4): `BillingClient.onPurchasesUpdated`, `launchBillingFlow`, `queryPurchases`,
`consumeAsync` — all `after`.
License (3): `LicenseCheckerCallback.dontAllow` (before), `LicenseValidator.verify`
(return_true), `ServerManagedPolicy.<init>` (after).

**hook_type enum**: `before` | `after` | `return_true` | `return_zero` |
`after_signature_spoof`.

### 5.3 `after_signature_spoof` (v4, key LP parity trick)
Null out `PackageInfo.signatures` after getPackageInfo. Apps calling
`signatures[0]` hit NPE → caught → treated as "no signature" → check skipped.
Apps checking `signatures.length > 0` see 0 → skipped. Do **not** re-construct
PackageInfo (slower, more fragile).

```smali
invoke-virtual {p1}, getResult()           # v0 = result
if-eqz v0, :done
instance-of v1, v0, Landroid/content/pm/PackageInfo;
if-eqz v1, :done
check-cast v0, Landroid/content/pm/PackageInfo;
const/4 v1, 0x0
iput-object v1, v0, Landroid/content/pm/PackageInfo;->signatures:[Landroid/content/pm/Signature;
:done
return-void
```

### 5.4 Smali templates — MUST-know rules (compile-real tests enforce)

1. **`.registers N` minimums**:
   - Constructor → **N ≥ 1** (needs `p0` for `invoke-direct`)
   - `initZygote(StartupParam)V` instance method → **N ≥ 2** (p0 + p1)
   - `handleLoadPackage(LoadPackageParam)V` → N ≥ 2 (p0 + p1, plus locals)
   - `afterHookedMethod(MethodHookParam)V` → N ≥ 2 (p0 + p1)
   - `static init(ClassLoader)V` → **no `p` registers**, N = locals only

2. **Labels must be `__IDX__`-templated** when a body is concatenated per
   target: `:try_start___IDX__`, `:try_end___IDX__`, `:cond_done___IDX__`,
   `:catch___IDX__`, `:goto_done___IDX__`. Hardcoding `:try_start_0` on multi-target
   hooks produces duplicate labels → `smali.jar` fails with "label already exists".

3. **`.catch` directive must reference the same indices**:
   `.catch Ljava/lang/Throwable; {:try_start___IDX__ .. :try_end___IDX__} :catch___IDX__`

4. **Inner class files are independent compilation units** — labels in
   `SignatureHook$0.smali` and `SignatureHook$1.smali` do **not** conflict.
   Only labels within one `.smali` file matter.

### 5.5 Xposed API surface used
- `IXposedHookLoadPackage.handleLoadPackage(XC_LoadPackage.LoadPackageParam)`
- `IXposedHookZygoteInit.initZygote(StartupParam)` — noop in generator
- `XposedHelpers.findClass(String, ClassLoader)`
- `XposedHelpers.callMethod(Object, String, Object…)`
- `XposedBridge.hookAllMethods(Class, String, XC_MethodHook) → Set<Unhook>`
- `XC_MethodHook.MethodHookParam`: `.thisObject`, `.args`, `.getResult()`,
  `.setResult(Object)`
- `XC_MethodHook` overrides: `beforeHookedMethod`, `afterHookedMethod`

### 5.6 Deployment
- **LSPosed** (Android 8.1+, recommended): install zip, enable scope, reboot.
- **Magisk + Riru + EdXposed**: legacy, Android 10–11.
- **No LSPosed = no runtime hooks**. Static patches work independently.
- Verify runtime: check LSPosed logs for `[LP-PC-<Class>]` TAG entries from our `Log.d`.

---

## 6. AIDL proxy generator

Per-target generated source (not LP's prebuilt APK):
```
com/lppc/aidl/proxy/IInAppBillingService.smali       (interface stub)
com/lppc/aidl/proxy/InAppBillingServiceStub.smali    (impl, 8 methods)
com/lppc/aidl/proxy/BillingProxyService.smali        (Service wrapper)
```

Manifest inject:
```xml
<service android:name="com.lppc.aidl.proxy.BillingProxyService"
         android:exported="true"
         android:permission="com.android.vending.BILLING">
  <intent-filter>
    <action android:name="com.android.vending.billing.InAppBillingService.BIND"/>
  </intent-filter>
</service>
```
Also patch `<queries>` for `BIND` intent on Android 11+ (package visibility).

**Defeating GMS priority**: patch target's
`PackageManager.setComponentEnabledSetting(GMS_BILLING_COMPONENT, DISABLED, …)`
or block via Xposed. Proxy alone on a GMS device resolves to GMS, not proxy.

---

## 7. LP file formats

### 7.1 `AdsBlockList.txt`
```
[HTTP]
https://googleads.g.doubleclick.net/*
https://*.ads.example.com/path*
# comment

[ALL_STRINGS]
*.googlesyndication.com
*.unityads.unity3d.com
com/google/ads/.*
```
`*` = glob. `[HTTP]` = hosts/VPN layer (root, LP-PC Suite skips with warning).
`[ALL_STRINGS]` = substring match on every DEX string (LP-PC Suite static mode).

### 7.2 Hex pattern (`[FILE_IN_APK]`)
```
[FILE_IN_APK:classes.dex]
search: DE AD BE EF ?? ?? CA FE
replace: 00 00 00 00 00 00 CA FE

[FILE_IN_APK:lib/armeabi-v7a/libfoo.so]
search: 55 8B EC 83 EC ** ** 53 56
replace: 55 8B EC 83 EC 00 00 53 56
```
- `??` = exactly 1 byte
- `**` = 0+ bytes (variable)
- hex literals = exact
- Multiple blocks/file allowed, applied sequentially. `search` must match
  uniquely or first-match (ambiguous with `**`).
Applied **after recompile, before sign** (invalidates existing signature).

### 7.3 Custom patch (`.txt` / `.lpzip`)
Declarative smali find/replace. LP-PC Suite supports `**` mask, `<reg>`,
`<label>`, `<any>`. **Not yet**: `[Condition]` blocks.

### 7.4 `appdata.txt` (saved purchases)
Line format observed (undocumented):
```
<package>|<product_id>|<purchase_token>|<timestamp>|<receipt_json_b64>
```
LP-PC Suite uses its own `workspace/iap_history.json` (incompatible).

---

## 8. Packer detection (16 signatures)

| Packer | Stub classes | Native | Patchable |
|---|---|---|---|
| PairIP (Google Play Integrity) | `com.pairip.application.Application`, `com.pairip.VMRunner` | `libpairipcore.so` | ❌ |
| Tencent Legu | `com.tencent.StubShell.TxAppEntry` | `libshell*.so` | ❌ |
| 360 Jiagu | `com.qihoo.util.StubApplication`, `com.stub.StubApp` | `libjiagu*.so` | ❌ |
| Bangcle / SecNeo | `com.bangcle.application.ProtectApplication` | `libsecexe.so` | ❌ |
| Ijiami | `s.h.e.l.l.S` (obf.) | `libshella*.so` | ❌ |
| LIAPP | `com.liapp.application.LIAPPApplication` | `libliapp*.so` | ❌ |
| Virbox | `com.virbox.*` | — | ❌ |
| Nagain (Korean) | `com.nagain.NagainApplication` | — | ❌ |
| AppSealing (Inka) | `com.inka.AppSealing` | — | ❌ |
| Baidu Protect | `com.baidu.protect.ProtectApplication` | — | ❌ |
| ChaosVM | `com.chaosvm.*` | — | ❌ |
| NQ Shield | `com.nqshield.NQShieldApplication` | — | ❌ |
| Promon Shield | `com.promon.shield.*` | — | ❌ |
| DexProtector (Licel) | `com.licel.dexprotector.*` | — | ❌ |
| DexGuard (Guardsquare) | `com.guardsquare.dexguard.runtime.*` | — | ✅ (obfuscator) |
| Arxan | `com.arxan.*` (native ≥5) | — | ✅ (native, DEX visible) |

### 8.1 Bytecode scoring (`packer_bytecode.py` v4)
Per signature: `stub_class match +3`, `invocation match +2`,
`encrypted_dex evidence +2`, `native_mass threshold +1`. Strongest score wins.
Fallback order: primary (4-tier) → bytecode (tier 5).

### 8.2 Entropy window analysis (v4)
`entropy_window_analysis(dex_bytes, window_size=16384, sample_stride=4, threshold=7.5)`:
- Non-overlapping 16 KB windows, sample every 4th byte (fast)
- `WindowEntropyResult.max_entropy, max_offset, high_entropy_count, total_windows`
- `has_encrypted_region = high_pct >= 20%`
- Catches partial encryption that global entropy misses (packer encrypts only
  strings section → low global, high local entropy).

`_fast_entropy()` uses `Counter` (≈5× faster than loop for 16 KB windows).

### 8.3 Detection layers (all active)
1. `<application android:name>` in manifest
2. DEX class prefixes (ASCII regex on raw dex bytes; ~0.3 s/dex vs androguard 5–8 s)
3. Native lib basename `lib/<abi>/*.so`
4. Assets entries (`ijiami.dat`, `classes.jar`, …)
5. Bytecode: stub classes + invocation regex + entropy windows

### 8.4 PairIP specific behaviour
Detected via `Lcom/pairip/application/Application;` in ASCII blob (2.34 s for
88 MB `Test.apk`). `patchable=False`. `main.py` prints:
`[!] Packer detected: PairIP … patch license/iap/ads có thể patch 0 files`.
`license_check.py` emits `license_packed` finding (red) instead of `license`.

---

## 9. Pipeline internals

### 9.1 Stages
```
[1] normalize_input()   .apk / .xapk / .apks / folder → single .apk
[2] strategy            tiny|small→fast, medium→balanced, large|huge→careful, massive→paranoid
[3] AppDeepAnalyzer     30 d cache; packer→license→ads→iap→misc→security
[4] workspace           workspace/output/<sanitized_pkg>/
[5] SafetyGuard         system_cpu − own_tree_cpu; T=98% / RAM 85% / disk 10%
[6] decompile_apk()     7 d cache; robocopy /MT:32; existing workspace → incremental
                        /PURGE mirror (54.5k files: 12.4 s vs 159.5 s full copy)
[7] execute_modes()     ThreadPool + submit_with_context + path_hints
[8] recompile_apk()     jobs=min(16, max(4, cpu×2)); resource-decode retry on fail;
                        verify ZIP+manifest+dex
[9] sign_apk()          testkey→uber-apk-signer; platform/media/shared→apksigner
[10] install_apk()      ADB auto-uninstall on signature mismatch
```

### 9.2 Trace ID (`core/trace_context.py`)
Contextvar-based. `with trace_context() as tid` sets `ContextVar`; `get_trace_id()`
returns `tid` or `"-"`; `prefix_with_trace(msg)` → `[tid:xxx] msg`.
**ThreadPool gotcha**: `ContextVar` is per-thread — workers do NOT see caller's
context by default. Use `submit_with_context(executor, fn, *args)` (from
`trace_context.py`) which does `ctx = contextvars.copy_context()` in the calling
thread then `executor.submit(ctx.run, fn, *args)`.

Env: `LP_TRACE_ID=<hex>` override, `LP_TRACE_DISABLE=1` disable.

`TraceFilter` (stdlib `logging.Filter`) injects `record.trace_id`;
`pipeline_helpers.setup_logging` attaches it with formatter
`"%(asctime)s | %(levelname)-8s | [%(trace_id)s] | %(name)s | %(message)s"`.

### 9.3 Caches

| Cache | TTL | Invalidation |
|---|---|---|
| APK analysis | 30 d | `_ANALYZER_CACHE_VERSION` bump |
| Decompiled | 7 d | source APK MD5 |
| `FileContentCache` | in-memory | `flush()` after patch phase |

**Never junction** — NTFS junctions let patch phase write through to cache.
Raw copy via robocopy is the only safe mechanism.

`_ANALYZER_CACHE_VERSION` history (in `analyzer.py`): v1 base, v2 root strict,
v3 root confidence, v4 share dex strings (reverted), v5 classes+methods,
v6 fast path strings, v7 ASCII regex security, v8 ASCII regex license/iap/packer,
v9 reconstruct `packer_info` on cache hit, v10 packer v4 window analysis.

### 9.4 path_hints prefilter (perf)
| Patcher | hints | Reduction |
|---|---|---|
| License | `license`, `licensing`, `lvl`, `validator`, `vending`, `purchase`, `billing`, `iap`, `premium`, `amazon`, `samsung`, `store` + `pro` token/CamelCase regex | 52,830 → 1,907 (84 MB PairIP APK) |
| Signature | `security`, `signature` | 52,845 → 722 |
| IAP | `billing`, `iap`, `purchase`, `unity` | 52,845 → 1,848 |

`pro` is not a substring hint: `$proxy`/provider classes made 5,134 of 6,308
license candidates. `_PATH_PATTERNS` matches token `pro`/`ProX` instead, so
`ProManager` still scans while `Proxy` does not. `IAPDexPatcher` scans all
files but rejects blacklist-only paths (2,350 of 52,830 on the test APK)
**before** reading.

Fallback FULL if 0 match (obfuscated APK), logged as
`[i] [{label}] Path prefilter 0 match — FULL scan N files`.

### 9.5 SafetyGuard (v2)
`system_cpu = psutil.cpu_percent()`, `own_tree_cpu = sum over baseline PIDs +
descendants`, `external = system − own_tree`. Prevents Defender scans from
triggering "you are overloading the system". Threshold breach → halve apktool
jobs (`throttle_factor`). `reset_after_ok_checks=3` → restore. After
`prompt_after_n_violations=5` → GUI dialog, or CLI fallback per
`cli_mode_action` (`mute`/`continue`/`abort`). Continue raises threshold `+5%`.
`cli_abort_reasons` (default `[ram]`) always hard-aborts in CLI mode regardless
of `cli_mode_action` — sustained RAM pressure must never mute/resume full load.
`main` re-checks `abort_flag` after recompile, before signing. Config under
`auto_tune.safety`.

### 9.6 Persistence schemas

**`PatchMetrics`** (`core/metrics.py`):
```python
apk_name, mode, success, duration_sec, patches_applied, error,
stage (default "pipeline"), timestamp (auto), trace_id
```
Atomic write via `tempfile.mkstemp` + `os.replace`. `_MAX_ENTRIES=500`.
`get_summary()` → `{total, success_rate, by_mode, by_stage, recent_errors}`.

**`PatchHistory`** (`core/patch_history.py`):
```python
{timestamp, apk, mode, success, output, patches: [...], trace_id}
```
`_MAX_ENTRIES=100`, newest-first via `get_history()` returns reversed. Constructor
accepts 6 alias kwargs (`history_file`, `file`, `path`, `storage_file`,
`history_dir`+`filename`, positional).

### 9.7 Modes registry
`core/mode_registry.MODE_MAP` + `PluginManager.get_all_modes()` merge. Modes
with same `group` → sequential; no group → parallel. Prefix `multi:` in mode
string → strip prefix then split `,`.

### 9.8 Performance audit (2026-11)

Machine: 4 logical CPUs, 7.9 GB RAM, Windows Defender first-touch scans.

| Change | Before | After | Notes |
|---|---|---|---|
| Cache load into existing workspace | 159.5 s delete + copy | 12.4 s `/PURGE` mirror | 54,508 files; E2E steady state 112.1 s → 2.7 s |
| License path filter | 6,308 files | 1,907 files | 5,134 removed by `pro` boundary fix; E2E 363.8 s → 78.8 s |
| IAP blacklist paths | read then reject | reject before read | 2,350 / 52,830 files; E2E scan 417.9 s → 144.8 s |
| IAP scan workers (4 CPUs) | 8 | 32 | 8.5 ms → 5.4 ms per cold file |
| Recompile jobs | 4 (323.3 s / 280.4 s) | 8 (249.4 s / 236.3 s) | pristine builds, no `build/` reuse; E2E 359.8 s → 278.3 s |
| GUI startup import | 1,493 ms | 574 ms | warm `import run_gui`, 3 runs each; CLI `import main` 573 → 549 ms (noise) |
| Ads URL / string transform | 3.95 s / 1.19 s | 0.55 s / 0.18 s | 3,000 files; 69 → 2 URL chunks, 16 → 1 string chunk; same output digest |
| Full test suite | 1,230 s (1,884 pass) | 280.3 s (1,886 pass) | module-scoped real-APK analyzer fixture; cache tests still scan |
| Full E2E `license:auto,iap:dex` | 998.3 s | 469.7 s | reused patched workspace; stale-workspace run 847.7 s |

E2E contract unchanged: 53 pattern keys, 43 files patched, 52,845 scanned,
0 skipped, 84.8 MB output signed `[v2, v3]`. The stale-workspace run paid a
full 132.3 s recopy; the steady-state run mirrored 54,482 files in 2.7 s.

Parallel smali reads were evaluated and **not shipped**: cold first-touch reads
on 3,000 files dropped 24.9 → 7.2 ms/file with 8 threads, but after decompile
or cache load the tree is warm (0.4–1.2 ms/file), `SignaturePatcher` stayed at
10.28 → 10.23 s, and `SigIntegrity` regressed 3.42 → 10.78 s. The license
stage's 78.8 s E2E time is contention with the concurrent 52,845-file IAP
scan, not per-file read cost. `BasePatcher.patch_files()` remains sequential.

`apktool b` writes a `build/` directory inside the decompiled tree. Benchmark
from a copy, never from the cache; `/PURGE` removes it from reused workspaces
so every pipeline build is a clean build.

---

## 10. UI contracts (from tests)

Signal-only decoupling. Widgets emit; `AppController` routes; `MainWindow` owns
lifecycle.

### 10.1 Signal table

| Widget | Signals |
|---|---|
| `APKDetailWidget` | `patch_action_requested(str)`, `rebuild_requested()`, `menu_of_patches_requested()` |
| `AppController` | `analysis_ready(dict)`, `log_message(str)`, `status_message(str)`, `progress_update(int,int)`, `progress_hide()`, `show_detail_page()`, `step_update(str,int)`, `safety_prompt_requested(str,dict,int,object)` |
| `RebuildTreeDialog` | `rebuild_requested(str)` — CSV mode string |
| `MenuOfPatchesDialog` | `action_requested(str)` |
| `MenuOfPatchesTreeDialog` | `action_requested(str)` — same |
| `LicensePatchDialog` | `patch_requested(str)` — `license:<mode>` |
| `AdsPatchDialog` | `patch_requested(str)` — `ads:<mode>` |
| `AppListWidget` | `app_context_menu_requested(pkg, name, colors, findings)` |
| `ToolboxMenu` | `patch_requested(str,dict)`, `clone_requested()`, `iap_manager_requested()`, `download_patch_requested()`, `system_tool_requested(str)` |

### 10.2 Dialog contracts
- `RebuildTreeDialog.get_key_type() → str`, `get_forced_package_id() → int|None`
  (127 → None).
- `PermissionPickerDialog.get_selected_permissions() → list[str]` (full perm
  names). Selection bridged via `LP_PERMS_TO_REMOVE` env var (CSV).
- `CloneDialog.get_new_package()`, `get_new_name()`; package regex
  `^[a-zA-Z][a-zA-Z0-9._]*$` (allows `_` and `.`), must differ from original.
- `ResignDialog.get_key_type() ∈ {testkey, platform, media, shared}`.
- `IAPManagerDialog` operates on `iap_manager.get_saved_purchases()`,
  `delete_purchase(id)`, `auto_repeat(pkg, product)`.

### 10.3 Special-mode routing (`AppController._on_rebuild_submit`)
- Exactly 1 special mode + 0 normal → `_dispatch_special_mode`.
- Special + normal → warn, run normal.
- N > 1 special → warn, dispatch first only.
- `_SPECIAL_MODES = {change_perms, resign, clone}`.

### 10.4 Layout rules
- Sidebar 3 pages (apps/detail/tools) via `QStackedWidget`.
- `QSplitter` vertical: content (stretch 4) + log panel (stretch 1);
  Ctrl+J collapse → sizes `[total−40, 40]`, expand → `[75%, 25%]`.
- Font base 15 px; log panel uses `Cascadia Code`/`Consolas` 12 px.
- Color map: green=License, blue=Ads, yellow=Custom, purple=System boot,
  orange=System app, red=Protected/packed, white=Clean.
- Drag-drop accepts `.apk/.xapk/.apks` only.

### 10.5 Shortcuts
`Ctrl+O` browse, `Ctrl+D` download, `Ctrl+W` workspace, `Ctrl+L` clear log,
`Ctrl+T` toolbox, `Ctrl+J` toggle log, `F5` reload, `Esc` back, `Ctrl+F` search.

### 10.6 Permission picker categories
`_PERMISSION_DB` keyed by short name (last segment). Categories:
`dangerous | special | normal | signature | other`. Classifier:
1. exact full name 2. short name 3. progressive suffix 4. fallback heuristic
(`.permission.` in full → normal; `com.*`/`net.*` → normal; else other).
Warn when selecting `INTERNET` or `BILLING` (breaks app). Presets: Dangerous,
Normal+Signature, All, None.

### 10.7 Exception hook
`install_gui_exception_hook(log_path, show_dialog)` — idempotent via
`sys._lp_exception_hook_installed`. Writes `logs/crash_<ts>.log` with
timestamp/Python version/platform + traceback. Skips `KeyboardInterrupt`.
Calls `sys.__excepthook__` at end (stderr traceback still works). Guarded so
hook itself never raises.

---

## 11. i18n (`core/i18n.py`)

- Files: `assets/i18n/{vi,en}.json`, **nested dicts only** (dots split by
  `_lookup`; flat keys with dots in the name will NOT resolve — this bug was
  fixed once; keep nested).
- Fallback chain: current lang → `en` → **key itself** (`t("foo.bar") == "foo.bar"`
  if missing; no crash).
- Format: `t("k", **fmt)` uses `.format(**fmt)`; on `KeyError`/`ValueError`
  returns raw string (so `{invalid` never crashes).
- Env `LP_LANG` sets default (default `vi`); `set_language()` runtime-switchable.
- `available_languages()` lists JSON files present, fallback `[vi,en]`.
- `_lookup` returns `None` for non-string values (int/dict treated as missing →
  fallback).
- Thread-safe via `RLock`; translations lazily loaded per lang.

Current schema (`assets/i18n/*.json`): `main_window, sidebar, toolbar, status,
log_panel, detail, switches, dialog.{common,resign,clone,patch_config,wizard}`.

New UI string → add key to **both** `vi.json` and `en.json` (nested) + use
`t()` in code. `test_i18n_dialog_coverage.py::test_vi_en_have_same_key_set`
enforces parity.

---

## 12. Bundletool (`core/bundletool_utils.py` v2)

`aab_to_apk(aab, output_dir=None, *, mode="universal", device_id=None,
keystore=None, ks_pass=None, ks_key_alias=None, log_callback=print)`.

- `mode ∈ {universal, default, system, persistent, instant}`; universal = single APK.
- `device_id` → `--device-id=<serial>` (bundletool needs connected device).
- Signing → `--ks=… --ks-pass=pass:… --ks-key-alias=…` (omit when None).
- APK entry priority: `universal.apk` → `standalones/*.apk` → `splits/base-master.apk`.
- `extract_apks_to_folder(apks_path, out_folder)` — bulk extract, flattens paths.
- `list_apks_entries(apks_path)` — diagnostic, returns entries.

Invalid `mode` → return `None` + `[!] [Bundletool] Invalid mode` log. Missing jar
→ `None`. All subprocess wrapped with 600 s timeout and `BadZipFile`/`OSError`
guards.

---

## 13. Testing patterns (learned in-session)

- **`qtbot.waitSignal(...).args` is a `list`, not tuple** — compare against list.
- **`MultiSignalBlocker`** (from `waitSignals`) is not iterable; use a plain
  `log_message.connect(list.append)` + `qtbot.waitUntil(lambda: len(list) >= n)`.
- **`QLabel.isVisible()` is False for offscreen widgets not yet shown** — use
  `isHidden()` instead in tests.
- **`QMessageBox.StandardButton.Yes == 16384`, not 1** — mock returns enum, and
  assertions compare to `StandardButton.Yes` / `DialogCode.Accepted`.
- **`item.sizeHint()` may be less than `minimumHeight()`** — assert `minimumHeight()`
  for layout guarantees, `sizeHint().height() >= 50` as sanity.
- **`patch_files` return value does not fail when `patch 0 files`** — callers
  must check packer info.
- **`smali.jar` returncode can be 0 while producing no dex** — the compile-real
  test asserts `dex_out.exists()` after rc==0.
- **`ContextVar` propagation to ThreadPool** requires `submit_with_context`;
  asserting `captured == ["tr123456"]` inside worker is the canonical test.
- **Atomic write**: verify no `*.tmp` remains after `record()` / `add_record()`.
- **Cache round-trip**: assert full scan + cache hit returns same `packer_info`
  (`test_e2e_analyzer_real_apk.py::TestAnalyzerCacheE2E`).

---

## 14. Anti-patterns / gotchas (ordered by pain)

1. **Junction cache** — patch writes leak into cache; next run reads dirty dex.
   Use robocopy.
2. **`DEX()` on real APK** — 5–8 s/dex × 9 dex = death. Use ASCII regex
   (`rb"[\x20-\x7e]{4,}"`), fallback androguard only for <1 KB test mocks.
3. **Hardcoded smali labels** — duplicate-label crash on multi-target hooks;
   always `__IDX__`.
4. **`.registers 0` constructors** — `Invalid register: v-1` at `smali.jar`.
5. **Flat JSON i18n keys with dots** — `_lookup` splits on dots; keep nested.
6. **`PatchHistory(path=...)` vs `history_dir=`** — six legacy aliases exist;
   positional or `history_file=` are the clean forms.
7. **Silent success on packed APK** — check `analyzer.packer_info.patchable`
   before declaring success.
8. **ADB install split APKs** — `adb install` refuses; merge via
   `merge_split_apks` first.
9. **`--use-aapt2`** — required for adaptive icons / modern fonts; retry once.
10. **`INSTALL_FAILED_UPDATE_INCOMPATIBLE`** — signature mismatch after testkey
    re-sign; auto-uninstall → user data loss, warn on system apps.
11. **i18n key missing** — silent: `t("k") == "k"`; `test_i18n_dialog_coverage.py`
    catches it.
12. **Cache stale after detection logic change** — bump
    `_ANALYZER_CACHE_VERSION`.
13. **`QMessageBox` in worker thread** — must run on GUI thread; wrap via
    signals.
14. **`waitSignal` timeout when signal is emitted before the `with`** — emit
    after; use `assertNotEmitted(wait=100)` for negative assertions.
15. **`pyproject.toml` version drift** — `uv.lock` must match; regenerate with
    `uv lock`.

---

## 15. Module map

| Capability | Key file |
|---|---|
| License auto/extreme/reverse | `patcher/license_patcher.py`, `patcher/license_extreme.py` |
| IAP DEX | `patcher/iap_dex_patcher.py` |
| AIDL gen/inject | `core/aidl_proxy_generator.py`, `patcher/aidl_proxy_patcher.py` |
| Signature static/integrity | `patcher/signature_patcher.py`, `patcher/signature_integrity_patcher.py` |
| Signature fake archive | `patcher/signature_fake_archive_patcher.py` |
| Ads blocklist + manifest | `patcher/ads_blocklist.py`, `patcher/ad_remover.py` |
| Custom patch / hex patch | `patcher/custom_patch.py`, `patcher/hex_pattern_patcher.py` |
| Xposed module generator | `core/xposed_generator.py` |
| Packer primary / bytecode | `scanner/checks/packer_check.py`, `scanner/checks/packer_bytecode.py` |
| Analyzer (cache v10) | `scanner/analyzer.py` |
| Permission removal | `patcher/permission_changer.py` + `ui/permission_picker_dialog.py` |
| Resign / clone | `patcher/resign_patcher.py`, `patcher/app_cloner.py` |
| Watermark | `patcher/watermarker.py` |
| Pipeline / CLI | `main.py`, `core/pipeline_executor.py`, `core/pipeline_helpers.py` |
| Trace ID | `core/trace_context.py` |
| Metrics / history | `core/metrics.py`, `core/patch_history.py` |
| Bundletool | `core/bundletool_utils.py` |
| i18n | `core/i18n.py`, `assets/i18n/{vi,en}.json` |
| GUI | `ui/*`, `core/i18n.py` |

**Test entry points**: `test_xposed_generator_compile_real.py` (real smali),
`test_e2e_analyzer_real_apk.py` (Test.apk, PairIP), `test_trace_persistence.py`,
`test_i18n_dialog_coverage.py`, `test_ui_*.py` (24+ files).

---

## 16. External references

- `Freezdy413485/LP-DeCodes` — LP 12.10.4 decompiled (`AdsBlockList.txt`, XSupport
  hooks, `patch.txt` examples).
- `Freezdy413485/LP-GUI` — GUI research, 4-layer, color map.
- `developer.android.com/google/play/licensing` — LVL reference.
- AOSP `PackageManager.java`, `PackageParser.java`, `ApkSignatureVerifier.java`,
  `SigningDetails.java`, `PackageManagerServiceUtils.java` — signature semantics.
- Google `IInAppBillingService.aidl` — 8 billing actions.
- `github.com/rednaga/APKiD` — packer signature database (reference only).
- `github.com/LSPosed/LSPosed` — Xposed for Android 8.1+.
- `github.com/JesusFreke/smali` — assembler (matches `tools/bin/smali.jar` CLI:
  `smali assemble -a <api> -o <out.dex> <dir>`).

---

**End of KNOW.md (v5)**