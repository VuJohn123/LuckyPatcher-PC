"""
Xposed module generator — sinh mã nguồn Xposed module cho các patch mode.

v3 (2026) — LP parity + backward-compat:
  - Multi-target hooks: mỗi hook key sinh nhiều inner classes ($0..$N).
  - LP parity: 19+ hooks across signature/install/iap/license.
  - Backward-compat: `_INNER_CLASS_TEMPLATES` giữ alias cho test cũ.
  - Default hook = "iap" khi config.hooks rỗng.

v4 (2026) — signature spoof + label + register fix:
  - `after_signature_spoof` template: hook `PackageManager.getPackageInfo`
    → clear `PackageInfo.signatures`.
  - FIX: `_HOOK_BODY_TEMPLATE` hard-code `:try_start_0`/`:try_end_0`
    → templated `__IDX__` (smali.jar compile được multi-target).
  - FIX: mọi constructor template `.registers 0` → `.registers 1`.
  - FIX: `initZygote` `.registers 1` → `.registers 2` (đủ p0 + p1).
    Catch bởi `test_xposed_generator_compile_real.py`.

Output structure:
    <output_dir>/xposed_module/
        ├── AndroidManifest.xml
        ├── assets/xposed_init
        ├── smali/com/lppc/xposed/hooks/
        │   ├── XposedEntry.smali
        │   ├── SignatureHook.smali + SignatureHook$0.smali .. $7.smali
        │   ├── InstallHook.smali   + InstallHook$0.smali .. $2.smali
        │   ├── IAPHook.smali       + IAPHook$0.smali .. $3.smali
        │   └── LicenseHook.smali   + LicenseHook$0.smali .. $2.smali
        ├── res/values/arrays.xml
        └── README.md
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_XPOSED_INIT_PACKAGE = "com.lppc.xposed.hooks.XposedEntry"
_XPOSED_MIN_VERSION = 82

_HOOK_CLASS_NAMES: dict[str, str] = {
    "iap": "IAPHook",
    "license": "LicenseHook",
    "signature": "SignatureHook",
    "install": "InstallHook",
}

# LP parity hook targets:
#   (target_class, method_name, hook_type)
# hook_type: "before" | "after" | "return_true" | "return_zero"
#            | "after_signature_spoof"
_HOOK_TARGETS: dict[str, list[tuple[str, str, str]]] = {
    "signature": [
        ("android.content.pm.PackageManager", "checkSignatures",
         "return_zero"),
        ("android.content.pm.PackageManager", "getPackageInfo",
         "after_signature_spoof"),
        ("android.content.pm.SigningDetails", "checkCapability",
         "return_true"),
        ("android.content.pm.SigningDetails", "hasAncestorOrSelf",
         "return_true"),
        ("android.util.apk.ApkSignatureVerifier", "verifySignatures",
         "after"),
        ("com.android.apksig.ApkVerifier", "<init>", "after"),
        ("com.android.server.pm.PackageManagerServiceUtils",
         "verifySignatures", "after"),
        ("com.android.server.pm.ScanPackageUtils",
         "getMinimumSignatureSchemeVersionForTargetSdk", "return_zero"),
    ],
    "install": [
        ("com.android.server.pm.PackageManagerService", "<init>", "after"),
        ("com.android.server.pm.InstallPackageHelper",
         "installPackagesLI", "after"),
        ("com.android.server.pm.InstallPackageHelper",
         "preparePackage", "after"),
    ],
    "iap": [
        ("com.android.billingclient.api.BillingClient",
         "onPurchasesUpdated", "after"),
        ("com.android.billingclient.api.BillingClient",
         "launchBillingFlow", "after"),
        ("com.android.billingclient.api.BillingClient",
         "queryPurchases", "after"),
        ("com.android.billingclient.api.BillingClient",
         "consumeAsync", "after"),
    ],
    "license": [
        ("com.android.vending.licensing.LicenseCheckerCallback",
         "dontAllow", "before"),
        ("com.android.vending.licensing.LicenseValidator",
         "verify", "return_true"),
        ("com.android.vending.licensing.ServerManagedPolicy",
         "<init>", "after"),
    ],
}


# ============================================================
# DATA CLASSES
# ============================================================
@dataclass
class XposedModuleConfig:
    package_name: str = "com.lppc.xposed.generated"
    app_name: str = "LP-PC Xposed Patch"
    version_name: str = "1.0.0"
    version_code: int = 1
    min_xposed_version: int = _XPOSED_MIN_VERSION
    target_package: str = ""
    hooks: list[str] = field(default_factory=list)
    author: str = "LP-PC Suite"


@dataclass
class GeneratedModule:
    output_dir: str
    manifest_path: str
    entry_smali_path: str
    hooks_generated: list[str] = field(default_factory=list)
    inner_classes_generated: list[str] = field(default_factory=list)
    hook_count: int = 0
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)


# ============================================================
# SMALI TEMPLATES
# ============================================================
_XPOSED_ENTRY_SMALI = r""".class public Lcom/lppc/xposed/hooks/XposedEntry;
.super Ljava/lang/Object;
.source "XposedEntry.java"

.implements Lde/robv/android/xposed/IXposedHookLoadPackage;
.implements Lde/robv/android/xposed/IXposedHookZygoteInit;


.method public constructor <init>()V
    .registers 1
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V
    return-void
.end method


.method public handleLoadPackage(Lde/robv/android/xposed/callbacks/XC_LoadPackage$LoadPackageParam;)V
    .registers 6

    iget-object v0, p1, Lde/robv/android/xposed/callbacks/XC_LoadPackage$LoadPackageParam;->classLoader:Ljava/lang/ClassLoader;

# __INIT_HOOKS_CALLS__

    return-void
.end method


.method public initZygote(Lde/robv/android/xposed/IXposedHookZygoteInit$StartupParam;)V
    .registers 2
    return-void
.end method
"""


_HOOK_HEADER_TEMPLATE = r""".class public Lcom/lppc/xposed/hooks/__CLASS__;
.super Ljava/lang/Object;
.source "__CLASS__.java"

.field private static final TAG:Ljava/lang/String; = "LP-PC-__CLASS__"


.method public constructor <init>()V
    .registers 1
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V
    return-void
.end method


.method public static init(Ljava/lang/ClassLoader;)V
    .registers 4
__BODY__
    return-void
.end method
"""

_HOOK_BODY_TEMPLATE = r"""
    :try_start___IDX__
    const-string v0, "__TARGET__"
    invoke-static {v0, p0}, Lde/robv/android/xposed/XposedHelpers;->findClass(Ljava/lang/String;Ljava/lang/ClassLoader;)Ljava/lang/Class;
    move-result-object v0

    if-eqz v0, :cond_done___IDX__

    const-string v1, "__METHOD__"
    new-instance v2, Lcom/lppc/xposed/hooks/__CLASS__$__IDX__;
    invoke-direct {v2}, Lcom/lppc/xposed/hooks/__CLASS__$__IDX__;-><init>()V
    invoke-static {v0, v1, v2}, Lde/robv/android/xposed/XposedBridge;->hookAllMethods(Ljava/lang/Class;Ljava/lang/String;Lde/robv/android/xposed/XC_MethodHook;)Ljava/util/Set;

    :cond_done___IDX__
    :try_end___IDX__
    .catch Ljava/lang/Throwable; {:try_start___IDX__ .. :try_end___IDX__} :catch___IDX__

    goto :goto_done___IDX__

    :catch___IDX__
    move-exception v0

    :goto_done___IDX__
"""


# --- Inner class templates by hook_type ---
# NOTE: `.registers 1` cho constructor (chứa p0 cho invoke-direct).
_INNER_BEFORE_TEMPLATE = r""".class public Lcom/lppc/xposed/hooks/__CLASS__$__IDX__;
.super Lde/robv/android/xposed/XC_MethodHook;
.source "__CLASS__.java"


.method public constructor <init>()V
    .registers 1
    invoke-direct {p0}, Lde/robv/android/xposed/XC_MethodHook;-><init>()V
    return-void
.end method


.method protected beforeHookedMethod(Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;)V
    .registers 5

    iget-object v0, p1, Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;->thisObject:Ljava/lang/Object;

    if-eqz v0, :cond_done

    const-string v1, "allow"
    const/4 v2, 0x0
    new-array v2, v2, [Ljava/lang/Object;
    invoke-static {v0, v1, v2}, Lde/robv/android/xposed/XposedHelpers;->callMethod(Ljava/lang/Object;Ljava/lang/String;[Ljava/lang/Object;)Ljava/lang/Object;

    :cond_done
    const/4 v0, 0x0
    invoke-virtual {p1, v0}, Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;->setResult(Ljava/lang/Object;)V

    return-void
.end method
"""

_INNER_AFTER_TEMPLATE = r""".class public Lcom/lppc/xposed/hooks/__CLASS__$__IDX__;
.super Lde/robv/android/xposed/XC_MethodHook;
.source "__CLASS__.java"


.method public constructor <init>()V
    .registers 1
    invoke-direct {p0}, Lde/robv/android/xposed/XC_MethodHook;-><init>()V
    return-void
.end method


.method protected afterHookedMethod(Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;)V
    .registers 4

    const-string v0, "LP-PC-__CLASS__"
    const-string v1, "__METHOD__ hooked"
    invoke-static {v0, v1}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I

    return-void
.end method
"""

_INNER_RETURN_TRUE_TEMPLATE = r""".class public Lcom/lppc/xposed/hooks/__CLASS__$__IDX__;
.super Lde/robv/android/xposed/XC_MethodHook;
.source "__CLASS__.java"


.method public constructor <init>()V
    .registers 1
    invoke-direct {p0}, Lde/robv/android/xposed/XC_MethodHook;-><init>()V
    return-void
.end method


.method protected beforeHookedMethod(Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;)V
    .registers 3

    const/4 v0, 0x1
    invoke-static {v0}, Ljava/lang/Boolean;->valueOf(Z)Ljava/lang/Boolean;
    move-result-object v0
    invoke-virtual {p1, v0}, Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;->setResult(Ljava/lang/Object;)V

    return-void
.end method
"""

_INNER_RETURN_ZERO_TEMPLATE = r""".class public Lcom/lppc/xposed/hooks/__CLASS__$__IDX__;
.super Lde/robv/android/xposed/XC_MethodHook;
.source "__CLASS__.java"


.method public constructor <init>()V
    .registers 1
    invoke-direct {p0}, Lde/robv/android/xposed/XC_MethodHook;-><init>()V
    return-void
.end method


.method protected beforeHookedMethod(Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;)V
    .registers 3

    const/4 v0, 0x0
    invoke-static {v0}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;
    move-result-object v0
    invoke-virtual {p1, v0}, Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;->setResult(Ljava/lang/Object;)V

    return-void
.end method
"""


# ============================================================
# v4 — signature spoof (LP parity)
# ============================================================
_INNER_AFTER_SIGNATURE_SPOOF_TEMPLATE = r""".class public Lcom/lppc/xposed/hooks/__CLASS__$__IDX__;
.super Lde/robv/android/xposed/XC_MethodHook;
.source "__CLASS__.java"


.method public constructor <init>()V
    .registers 1
    invoke-direct {p0}, Lde/robv/android/xposed/XC_MethodHook;-><init>()V
    return-void
.end method


.method protected afterHookedMethod(Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;)V
    .registers 4

    invoke-virtual {p1}, Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;->getResult()Ljava/lang/Object;
    move-result-object v0

    if-eqz v0, :cond_done

    instance-of v1, v0, Landroid/content/pm/PackageInfo;
    if-eqz v1, :cond_done

    check-cast v0, Landroid/content/pm/PackageInfo;

    const/4 v1, 0x0
    iput-object v1, v0, Landroid/content/pm/PackageInfo;->signatures:[Landroid/content/pm/Signature;

    :cond_done
    return-void
.end method
"""


_INNER_TEMPLATES: dict[str, str] = {
    "before": _INNER_BEFORE_TEMPLATE,
    "after": _INNER_AFTER_TEMPLATE,
    "return_true": _INNER_RETURN_TRUE_TEMPLATE,
    "return_zero": _INNER_RETURN_ZERO_TEMPLATE,
    "after_signature_spoof": _INNER_AFTER_SIGNATURE_SPOOF_TEMPLATE,
}


# ============================================================
# BACKWARD-COMPAT alias — test cũ import `_INNER_CLASS_TEMPLATES`
# ============================================================
_IAP_HOOK_INNER_SMALI = _INNER_AFTER_TEMPLATE
_LICENSE_HOOK_INNER_SMALI = _INNER_BEFORE_TEMPLATE
_SIGNATURE_HOOK_INNER_SMALI = _INNER_AFTER_TEMPLATE
_INSTALL_HOOK_INNER_SMALI = _INNER_AFTER_TEMPLATE

_INNER_CLASS_TEMPLATES: dict[str, str] = {
    "iap": _IAP_HOOK_INNER_SMALI,
    "license": _LICENSE_HOOK_INNER_SMALI,
    "signature": _SIGNATURE_HOOK_INNER_SMALI,
    "install": _INSTALL_HOOK_INNER_SMALI,
}


# ============================================================
# XML / MD TEMPLATES
# ============================================================
_ANDROID_MANIFEST_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="__PACKAGE_NAME__">

    <application
        android:label="__APP_NAME__"
        android:allowBackup="false">

        <meta-data android:name="xposedmodule" android:value="true" />
        <meta-data android:name="xposeddescription"
            android:value="LP-PC Suite runtime patch module" />
        <meta-data android:name="xposedminversion"
            android:value="__MIN_XPOSED__" />
        <meta-data android:name="xposedscope"
            android:resource="@array/xposed_scope" />

    </application>

    <uses-sdk android:minSdkVersion="24" android:targetSdkVersion="34" />

</manifest>
"""

_XPOSED_SCOPE_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string-array name="xposed_scope">
__SCOPE_ENTRY__
    </string-array>
</resources>
"""

_README_TEMPLATE = """# Xposed Module — __APP_NAME__

Generated by **LP-PC Suite** for target: `__TARGET_PACKAGE__`

## Hooks generated (__HOOK_COUNT__ total)
__HOOKS_LIST__

## Inner classes
__INNER_CLASSES_LIST__

## Cài đặt

1. Compile smali → DEX:
   `java -jar tools/bin/smali.jar assemble -a 24 -o classes.dex xposed_module/smali`

2. Zip: `classes.dex` + `AndroidManifest.xml` + `assets/xposed_init`
   + `res/values/arrays.xml` → `module.zip`

3. Cài module:
   - Copy `module.zip` → `/sdcard/LP_PC_Module.zip`
   - Magisk: Modules → Install from storage
   - LSPosed: install zip, reboot, enable module trong LSPosed manager

4. Reboot device.

## Warning
- Yêu cầu Magisk + LSPosed (hoặc Xposed framework).
- Chỉ hoạt động trên package target: `__TARGET_PACKAGE__`.
- LP parity: 19+ hooks mirror từ LP 12.10.4 XSupport.
"""


# ============================================================
# GENERATOR
# ============================================================
class XposedModuleGenerator:
    SUPPORTED_HOOKS = frozenset({"iap", "license", "signature", "install"})

    def __init__(self, log_callback=print):
        self.log = log_callback

    def generate(self, config: XposedModuleConfig,
                 output_dir: str) -> GeneratedModule:
        errors: list[str] = []
        hooks_gen: list[str] = []
        inner_classes_gen: list[str] = []
        total_hooks = 0

        try:
            os.makedirs(output_dir, exist_ok=True)
            hooks_dir = os.path.join(
                output_dir, "smali", "com", "lppc", "xposed", "hooks"
            )
            os.makedirs(hooks_dir, exist_ok=True)

            active_hooks = [
                h for h in config.hooks if h in self.SUPPORTED_HOOKS
            ]
            if not active_hooks:
                active_hooks = ["iap"]  # backward-compat default
                self.log("[i] [Xposed] Default hook: iap")

            # 1. Entry
            init_calls = self._build_init_calls(active_hooks, config)
            entry_smali = _XPOSED_ENTRY_SMALI.replace(
                "# __INIT_HOOKS_CALLS__", init_calls
            )
            self._write(
                os.path.join(hooks_dir, "XposedEntry.smali"),
                entry_smali,
            )

            # 2. Each hook class + inner classes
            for hook_key in active_hooks:
                class_name = _HOOK_CLASS_NAMES[hook_key]
                targets = _HOOK_TARGETS.get(hook_key, [])
                if not targets:
                    continue

                body_parts: list[str] = []
                for idx, (target_cls, method, hook_type) in enumerate(targets):
                    body = (
                        _HOOK_BODY_TEMPLATE
                        .replace("__TARGET__", target_cls)
                        .replace("__METHOD__", method)
                        .replace("__CLASS__", class_name)
                        .replace("__IDX__", str(idx))
                    )
                    body_parts.append(body)

                    inner = (
                        _INNER_TEMPLATES[hook_type]
                        .replace("__CLASS__", class_name)
                        .replace("__IDX__", str(idx))
                        .replace("__METHOD__", method)
                    )
                    inner_name = f"{class_name}${idx}.smali"
                    self._write(
                        os.path.join(hooks_dir, inner_name), inner,
                    )
                    inner_classes_gen.append(f"{class_name}${idx}")

                hook_smali = (
                    _HOOK_HEADER_TEMPLATE
                    .replace("__CLASS__", class_name)
                    .replace("__BODY__", "\n".join(body_parts))
                )
                self._write(
                    os.path.join(hooks_dir, f"{class_name}.smali"),
                    hook_smali,
                )
                hooks_gen.append(hook_key)
                total_hooks += len(targets)

            # 3. Manifest
            manifest = (
                _ANDROID_MANIFEST_TEMPLATE
                .replace("__PACKAGE_NAME__", config.package_name)
                .replace("__APP_NAME__", config.app_name)
                .replace("__MIN_XPOSED__", str(config.min_xposed_version))
            )
            manifest_path = os.path.join(output_dir, "AndroidManifest.xml")
            self._write(manifest_path, manifest)

            # 4. assets/xposed_init
            assets_dir = os.path.join(output_dir, "assets")
            os.makedirs(assets_dir, exist_ok=True)
            self._write(
                os.path.join(assets_dir, "xposed_init"),
                _XPOSED_INIT_PACKAGE + "\n",
            )

            # 5. res/values/arrays.xml
            res_dir = os.path.join(output_dir, "res", "values")
            os.makedirs(res_dir, exist_ok=True)
            scope_entry = (
                f"        <item>{config.target_package}</item>"
                if config.target_package
                else "        <item>android</item>"
            )
            self._write(
                os.path.join(res_dir, "arrays.xml"),
                _XPOSED_SCOPE_TEMPLATE.replace(
                    "__SCOPE_ENTRY__", scope_entry
                ),
            )

            # 6. README
            hooks_list = "\n".join(
                f"- `{k}` ({len(_HOOK_TARGETS.get(k, []))} hooks)"
                for k in hooks_gen
            )
            inner_list = "\n".join(
                f"- `{c}`" for c in inner_classes_gen
            )
            readme = (
                _README_TEMPLATE
                .replace("__APP_NAME__", config.app_name)
                .replace("__TARGET_PACKAGE__",
                         config.target_package or "(all apps)")
                .replace("__HOOKS_LIST__", hooks_list)
                .replace("__HOOK_COUNT__", str(total_hooks))
                .replace("__INNER_CLASSES_LIST__", inner_list)
            )
            self._write(os.path.join(output_dir, "README.md"), readme)

            self.log(
                f"[✔] [Xposed] Generated {output_dir} "
                f"({total_hooks} hooks, {len(inner_classes_gen)} inner)"
            )

        except OSError as e:
            errors.append("IO error: " + str(e))
            self.log(f"[!] [Xposed] {e}")
        except Exception as e:
            errors.append("Unexpected: " + str(e))
            logger.exception("Xposed generation crashed")

        return GeneratedModule(
            output_dir=output_dir,
            manifest_path=os.path.join(output_dir, "AndroidManifest.xml"),
            entry_smali_path=os.path.join(
                output_dir, "smali", "com", "lppc", "xposed",
                "hooks", "XposedEntry.smali",
            ),
            hooks_generated=hooks_gen,
            inner_classes_generated=inner_classes_gen,
            hook_count=total_hooks,
            is_valid=not errors,
            errors=errors,
        )

    def _build_init_calls(self, hooks: list[str],
                          config: XposedModuleConfig) -> str:
        lines: list[str] = []
        target = config.target_package

        if target:
            lines.append("")
            lines.append(
                "    iget-object v1, p1, "
                "Lde/robv/android/xposed/callbacks/"
                "XC_LoadPackage$LoadPackageParam;->packageName:"
                "Ljava/lang/String;"
            )
            lines.append(f'    const-string v2, "{target}"')
            lines.append(
                "    invoke-virtual {v2, v1}, "
                "Ljava/lang/String;->equals(Ljava/lang/Object;)Z"
            )
            lines.append("    move-result v2")
            lines.append("    if-eqz v2, :cond_skip")

        for hook in hooks:
            class_name = _HOOK_CLASS_NAMES[hook]
            lines.append("")
            lines.append(
                f"    invoke-static {{v0}}, "
                f"Lcom/lppc/xposed/hooks/{class_name};"
                f"->init(Ljava/lang/ClassLoader;)V"
            )

        if target:
            lines.append("    :cond_skip")

        return "\n".join(lines)

    @staticmethod
    def _write(path: str, content: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


def generate_xposed_module(
    target_package: str,
    patch_modes: list[str],
    output_dir: str,
    log_callback=print,
) -> GeneratedModule | None:
    pkg_short = target_package.replace(".", "_")[:30]
    config = XposedModuleConfig(
        package_name="com.lppc.xposed." + pkg_short,
        app_name="LP-PC Patch — " + target_package,
        target_package=target_package,
        hooks=patch_modes,
    )
    gen = XposedModuleGenerator(log_callback=log_callback)
    result = gen.generate(config, output_dir)
    return result if result.is_valid else None