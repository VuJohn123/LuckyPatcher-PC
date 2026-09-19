"""
Xposed module generator — sinh mã nguồn Xposed module cho các patch mode.

Thay vì rebuild APK, generate module hook runtime:
  - IAP bypass: hook BillingClient.onPurchasesUpdated
  - License bypass: hook LicenseCheckerCallback.dontAllow → gọi allow() + suppress
  - Signature bypass: hook PackageManager.getPackageInfo (skeleton)

Output structure:
    <output_dir>/xposed_module/
        ├── AndroidManifest.xml
        ├── assets/xposed_init
        ├── smali/com/lppc/xposed/hooks/
        │   ├── XposedEntry.smali
        │   ├── IAPHook.smali
        │   ├── IAPHook$1.smali          ← inner XC_MethodHook
        │   ├── LicenseHook.smali
        │   ├── LicenseHook$1.smali      ← inner XC_MethodHook
        │   ├── SignatureHook.smali
        │   └── SignatureHook$1.smali    ← inner XC_MethodHook
        ├── res/values/arrays.xml
        └── README.md

User cần compile smali → dex → zip thành Xposed module + install qua Magisk/LSPosed.

References:
  - FuckIAB (IAP hook implementation patterns)
  - Patcher-You (material Xposed alternative)
  - Freezdy413485/LP-DeCodes (LP 12.10.4 assets)
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_XPOSED_INIT_PACKAGE = "com.lppc.xposed.hooks.XposedEntry"
_XPOSED_MIN_VERSION = 82

# Map hook key → class name (tránh dùng str.capitalize() vì "iap" → "Iap")
_HOOK_CLASS_NAMES: dict[str, str] = {
    "iap": "IAPHook",
    "license": "LicenseHook",
    "signature": "SignatureHook",
}


# ============================================================
# DATA CLASSES
# ============================================================
@dataclass
class XposedModuleConfig:
    """Cấu hình cho 1 Xposed module."""
    package_name: str = "com.lppc.xposed.generated"
    app_name: str = "LP-PC Xposed Patch"
    version_name: str = "1.0.0"
    version_code: int = 1
    min_xposed_version: int = _XPOSED_MIN_VERSION
    target_package: str = ""   # Empty = hook all apps
    hooks: list[str] = field(default_factory=list)
    author: str = "LP-PC Suite"


@dataclass
class GeneratedModule:
    """Result của generator."""
    output_dir: str
    manifest_path: str
    entry_smali_path: str
    hooks_generated: list[str] = field(default_factory=list)
    inner_classes_generated: list[str] = field(default_factory=list)
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)


# ============================================================
# SMALI TEMPLATES — ENTRY
# ============================================================
_XPOSED_ENTRY_SMALI = r""".class public Lcom/lppc/xposed/hooks/XposedEntry;
.super Ljava/lang/Object;
.source "XposedEntry.java"

# interfaces
.implements Lde/robv/android/xposed/IXposedHookLoadPackage;
.implements Lde/robv/android/xposed/IXposedHookZygoteInit;


# direct methods
.method public constructor <init>()V
    .registers 0
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V
    return-void
.end method


# virtual methods
.method public handleLoadPackage(Lde/robv/android/xposed/callbacks/XC_LoadPackage$LoadPackageParam;)V
    .registers 6

    iget-object v0, p1, Lde/robv/android/xposed/callbacks/XC_LoadPackage$LoadPackageParam;->classLoader:Ljava/lang/ClassLoader;

# __INIT_HOOKS_CALLS__

    return-void
.end method


.method public initZygote(Lde/robv/android/xposed/IXposedHookZygoteInit$StartupParam;)V
    .registers 1
    return-void
.end method
"""


# ============================================================
# SMALI TEMPLATES — HOOK CLASSES
# ============================================================
_IAP_HOOK_SMALI = r""".class public Lcom/lppc/xposed/hooks/IAPHook;
.super Ljava/lang/Object;
.source "IAPHook.java"


# static fields
.field private static final TAG:Ljava/lang/String; = "LP-PC-IAPHook"


# direct methods
.method public constructor <init>()V
    .registers 0
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V
    return-void
.end method


# public static methods
.method public static init(Ljava/lang/ClassLoader;)V
    .registers 4

    :try_start_0
    const-string v0, "com.android.billingclient.api.BillingClient"
    invoke-static {v0, p0}, Lde/robv/android/xposed/XposedHelpers;->findClass(Ljava/lang/String;Ljava/lang/ClassLoader;)Ljava/lang/Class;
    move-result-object v0

    if-eqz v0, :cond_done

    const-string v1, "onPurchasesUpdated"
    new-instance v2, Lcom/lppc/xposed/hooks/IAPHook$1;
    invoke-direct {v2}, Lcom/lppc/xposed/hooks/IAPHook$1;-><init>()V
    invoke-static {v0, v1, v2}, Lde/robv/android/xposed/XposedBridge;->hookAllMethods(Ljava/lang/Class;Ljava/lang/String;Lde/robv/android/xposed/XC_MethodHook;)Ljava/util/Set;

    :cond_done
    :try_end_0
    .catch Ljava/lang/Throwable; {:try_start_0 .. :try_end_0} :catch_0

    goto :goto_done

    :catch_0
    move-exception v0

    :goto_done
    return-void
.end method
"""

_LICENSE_HOOK_SMALI = r""".class public Lcom/lppc/xposed/hooks/LicenseHook;
.super Ljava/lang/Object;
.source "LicenseHook.java"


# static fields
.field private static final TAG:Ljava/lang/String; = "LP-PC-LicenseHook"


# direct methods
.method public constructor <init>()V
    .registers 0
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V
    return-void
.end method


# public static methods
.method public static init(Ljava/lang/ClassLoader;)V
    .registers 4

    :try_start_0
    const-string v0, "com.android.vending.licensing.LicenseCheckerCallback"
    invoke-static {v0, p0}, Lde/robv/android/xposed/XposedHelpers;->findClass(Ljava/lang/String;Ljava/lang/ClassLoader;)Ljava/lang/Class;
    move-result-object v0

    if-eqz v0, :cond_done

    const-string v1, "dontAllow"
    new-instance v2, Lcom/lppc/xposed/hooks/LicenseHook$1;
    invoke-direct {v2}, Lcom/lppc/xposed/hooks/LicenseHook$1;-><init>()V
    invoke-static {v0, v1, v2}, Lde/robv/android/xposed/XposedBridge;->hookAllMethods(Ljava/lang/Class;Ljava/lang/String;Lde/robv/android/xposed/XC_MethodHook;)Ljava/util/Set;

    :cond_done
    :try_end_0
    .catch Ljava/lang/Throwable; {:try_start_0 .. :try_end_0} :catch_0

    goto :goto_done

    :catch_0
    move-exception v0

    :goto_done
    return-void
.end method
"""

_SIGNATURE_HOOK_SMALI = r""".class public Lcom/lppc/xposed/hooks/SignatureHook;
.super Ljava/lang/Object;
.source "SignatureHook.java"


# static fields
.field private static final TAG:Ljava/lang/String; = "LP-PC-SignatureHook"


# direct methods
.method public constructor <init>()V
    .registers 0
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V
    return-void
.end method


# public static methods
.method public static init(Ljava/lang/ClassLoader;)V
    .registers 4

    :try_start_0
    const-string v0, "android.content.pm.PackageManager"
    invoke-static {v0, p0}, Lde/robv/android/xposed/XposedHelpers;->findClass(Ljava/lang/String;Ljava/lang/ClassLoader;)Ljava/lang/Class;
    move-result-object v0

    if-eqz v0, :cond_done

    const-string v1, "getPackageInfo"
    new-instance v2, Lcom/lppc/xposed/hooks/SignatureHook$1;
    invoke-direct {v2}, Lcom/lppc/xposed/hooks/SignatureHook$1;-><init>()V
    invoke-static {v0, v1, v2}, Lde/robv/android/xposed/XposedBridge;->hookAllMethods(Ljava/lang/Class;Ljava/lang/String;Lde/robv/android/xposed/XC_MethodHook;)Ljava/util/Set;

    :cond_done
    :try_end_0
    .catch Ljava/lang/Throwable; {:try_start_0 .. :try_end_0} :catch_0

    goto :goto_done

    :catch_0
    move-exception v0

    :goto_done
    return-void
.end method
"""


# ============================================================
# SMALI TEMPLATES — INNER CLASSES ($1 extends XC_MethodHook)
# ============================================================
_IAP_HOOK_INNER_SMALI = r""".class public Lcom/lppc/xposed/hooks/IAPHook$1;
.super Lde/robv/android/xposed/XC_MethodHook;
.source "IAPHook.java"


# direct methods
.method public constructor <init>()V
    .registers 0
    invoke-direct {p0}, Lde/robv/android/xposed/XC_MethodHook;-><init>()V
    return-void
.end method


# virtual methods
.method protected afterHookedMethod(Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;)V
    .registers 4

    const-string v0, "LP-PC-IAPHook"
    const-string v1, "onPurchasesUpdated hooked"
    invoke-static {v0, v1}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I

    return-void
.end method
"""

_LICENSE_HOOK_INNER_SMALI = r""".class public Lcom/lppc/xposed/hooks/LicenseHook$1;
.super Lde/robv/android/xposed/XC_MethodHook;
.source "LicenseHook.java"


# direct methods
.method public constructor <init>()V
    .registers 0
    invoke-direct {p0}, Lde/robv/android/xposed/XC_MethodHook;-><init>()V
    return-void
.end method


# virtual methods
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

_SIGNATURE_HOOK_INNER_SMALI = r""".class public Lcom/lppc/xposed/hooks/SignatureHook$1;
.super Lde/robv/android/xposed/XC_MethodHook;
.source "SignatureHook.java"


# direct methods
.method public constructor <init>()V
    .registers 0
    invoke-direct {p0}, Lde/robv/android/xposed/XC_MethodHook;-><init>()V
    return-void
.end method


# virtual methods
.method protected afterHookedMethod(Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;)V
    .registers 4

    const-string v0, "LP-PC-SignatureHook"
    const-string v1, "getPackageInfo hooked"
    invoke-static {v0, v1}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I

    return-void
.end method
"""

_INNER_CLASS_TEMPLATES: dict[str, str] = {
    "iap": _IAP_HOOK_INNER_SMALI,
    "license": _LICENSE_HOOK_INNER_SMALI,
    "signature": _SIGNATURE_HOOK_INNER_SMALI,
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

        <meta-data
            android:name="xposedmodule"
            android:value="true" />
        <meta-data
            android:name="xposeddescription"
            android:value="LP-PC Suite runtime patch module" />
        <meta-data
            android:name="xposedminversion"
            android:value="__MIN_XPOSED__" />
        <meta-data
            android:name="xposedscope"
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

## Hooks
__HOOKS_LIST__

## Inner classes
__INNER_CLASSES_LIST__

## Cài đặt

1. Compile toàn bộ smali → DEX:
   `java -jar tools/bin/smali.jar assemble xposed_module/smali -o classes.dex`

2. Zip: `classes.dex` + `AndroidManifest.xml` + `assets/xposed_init`
   + `res/values/arrays.xml` → `module.zip`

3. Cài module:
   - Copy `module.zip` → `/sdcard/LP_PC_Module.zip`
   - Magisk: Modules → Install from storage
   - Hoặc LSPosed: install zip, reboot, enable module trong LSPosed manager

4. Reboot device.

## Warning
- Yêu cầu Magisk + LSPosed (hoặc Xposed framework).
- Chỉ hoạt động trên package target: `__TARGET_PACKAGE__`.
- Verify hook thực tế nếu app có anti-tamper.
"""


# ============================================================
# GENERATOR
# ============================================================
class XposedModuleGenerator:
    """Generate Xposed module từ patch modes."""

    SUPPORTED_HOOKS = frozenset({"iap", "license", "signature"})

    def __init__(self, log_callback=print):
        self.log = log_callback

    def generate(
        self,
        config: XposedModuleConfig,
        output_dir: str,
    ) -> GeneratedModule:
        errors: list[str] = []
        hooks_gen: list[str] = []
        inner_classes_gen: list[str] = []

        try:
            os.makedirs(output_dir, exist_ok=True)
            hooks_dir = os.path.join(
                output_dir, "smali", "com", "lppc", "xposed", "hooks"
            )
            os.makedirs(hooks_dir, exist_ok=True)

            # Filter hooks
            active_hooks = [
                h for h in config.hooks if h in self.SUPPORTED_HOOKS
            ]
            if not active_hooks:
                active_hooks = ["iap"]
                self.log(
                    "[i] [Xposed] Không có hook hợp lệ — default iap"
                )

            # 1. Entry class
            init_calls = self._build_init_calls(active_hooks, config)
            entry_smali = _XPOSED_ENTRY_SMALI.replace(
                "# __INIT_HOOKS_CALLS__", init_calls
            )
            entry_path = os.path.join(hooks_dir, "XposedEntry.smali")
            self._write(entry_path, entry_smali)

            # 2. Individual hooks + inner classes
            if "iap" in active_hooks:
                self._write(
                    os.path.join(hooks_dir, "IAPHook.smali"),
                    _IAP_HOOK_SMALI,
                )
                self._write(
                    os.path.join(hooks_dir, "IAPHook$1.smali"),
                    _INNER_CLASS_TEMPLATES["iap"],
                )
                hooks_gen.append("iap")
                inner_classes_gen.append("IAPHook$1")

            if "license" in active_hooks:
                self._write(
                    os.path.join(hooks_dir, "LicenseHook.smali"),
                    _LICENSE_HOOK_SMALI,
                )
                self._write(
                    os.path.join(hooks_dir, "LicenseHook$1.smali"),
                    _INNER_CLASS_TEMPLATES["license"],
                )
                hooks_gen.append("license")
                inner_classes_gen.append("LicenseHook$1")

            if "signature" in active_hooks:
                self._write(
                    os.path.join(hooks_dir, "SignatureHook.smali"),
                    _SIGNATURE_HOOK_SMALI,
                )
                self._write(
                    os.path.join(hooks_dir, "SignatureHook$1.smali"),
                    _INNER_CLASS_TEMPLATES["signature"],
                )
                hooks_gen.append("signature")
                inner_classes_gen.append("SignatureHook$1")

            # 3. AndroidManifest.xml
            manifest_content = (
                _ANDROID_MANIFEST_TEMPLATE
                .replace("__PACKAGE_NAME__", config.package_name)
                .replace("__APP_NAME__", config.app_name)
                .replace(
                    "__MIN_XPOSED__",
                    str(config.min_xposed_version),
                )
            )
            manifest_path = os.path.join(output_dir, "AndroidManifest.xml")
            self._write(manifest_path, manifest_content)

            # 4. assets/xposed_init
            assets_dir = os.path.join(output_dir, "assets")
            os.makedirs(assets_dir, exist_ok=True)
            init_path = os.path.join(assets_dir, "xposed_init")
            self._write(init_path, _XPOSED_INIT_PACKAGE + "\n")

            # 5. res/values/arrays.xml
            res_dir = os.path.join(output_dir, "res", "values")
            os.makedirs(res_dir, exist_ok=True)
            scope_entry = (
                "        <item>" + config.target_package + "</item>"
                if config.target_package
                else "        <item>android</item>"
            )
            scope_content = _XPOSED_SCOPE_TEMPLATE.replace(
                "__SCOPE_ENTRY__", scope_entry
            )
            self._write(
                os.path.join(res_dir, "arrays.xml"), scope_content,
            )

            # 6. README
            hooks_list = "\n".join(
                "- `" + h + "`" for h in hooks_gen
            )
            inner_list = "\n".join(
                "- `" + c + "`" for c in inner_classes_gen
            )
            readme = (
                _README_TEMPLATE
                .replace("__APP_NAME__", config.app_name)
                .replace(
                    "__TARGET_PACKAGE__",
                    config.target_package or "(all apps)",
                )
                .replace("__HOOKS_LIST__", hooks_list)
                .replace("__INNER_CLASSES_LIST__", inner_list)
            )
            self._write(os.path.join(output_dir, "README.md"), readme)

            self.log(
                "[✔] [Xposed] Generated module: "
                + output_dir + " (hooks=" + str(hooks_gen) + ")"
            )

        except OSError as e:
            errors.append("IO error: " + str(e))
            self.log("[!] [Xposed] " + str(e))
        except Exception as e:
            errors.append("Unexpected: " + str(e))
            logger.exception("Xposed generation crashed")
            self.log("[!] [Xposed] Unexpected: " + str(e))

        return GeneratedModule(
            output_dir=output_dir,
            manifest_path=os.path.join(output_dir, "AndroidManifest.xml"),
            entry_smali_path=os.path.join(
                output_dir, "smali", "com", "lppc", "xposed",
                "hooks", "XposedEntry.smali"
            ),
            hooks_generated=hooks_gen,
            inner_classes_generated=inner_classes_gen,
            is_valid=not errors,
            errors=errors,
        )

    def _build_init_calls(
        self,
        hooks: list[str],
        config: XposedModuleConfig,
    ) -> str:
        """
        Build smali code gọi từng hook init.

        Register usage (entry method .registers 6):
            v0 = classLoader (loaded by entry template)
            v1 = packageName (temp)
            v2 = target string / bool result (temp)
            v3 = unused
            v4 = p0 (this)
            v5 = p1 (LoadPackageParam)
        """
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
            lines.append(
                '    const-string v2, "' + target + '"'
            )
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
                "    invoke-static {v0}, "
                "Lcom/lppc/xposed/hooks/"
                + class_name + ";->init(Ljava/lang/ClassLoader;)V"
            )

        if target:
            lines.append("    :cond_skip")

        return "\n".join(lines)

    @staticmethod
    def _write(path: str, content: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


# ============================================================
# HIGH-LEVEL ENTRY
# ============================================================
def generate_xposed_module(
    target_package: str,
    patch_modes: list[str],
    output_dir: str,
    log_callback=print,
) -> GeneratedModule | None:
    """
    High-level: generate Xposed module từ patch modes.

    Args:
        target_package: package name của app cần hook
        patch_modes: list modes (vd ["iap", "license", "signature"])
        output_dir: dir để ghi module

    Return GeneratedModule hoặc None nếu fail.
    """
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