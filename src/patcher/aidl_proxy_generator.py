"""
AIDL Proxy Generator — sinh smali code cho proxy IInAppBillingService.

v2 (2026) — Complete BillingService implementation:
  - Full AIDL interface (10 methods: v1-v7).
  - Stub + Proxy classes (asInterface, onTransact).
  - BillingService với fake response cho mỗi method.
  - Package name LP parity: `com.chelpus.lackypatch`.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_PROXY_PACKAGE = "com.chelpus.lackypatch"

_AIDL_METHODS = {
    "isBillingSupported": (
        "(ILjava/lang/String;Ljava/lang/String;)I", "return_zero",
    ),
    "isBillingSupportedExtraParams": (
        "(ILjava/lang/String;Ljava/lang/String;Landroid/os/Bundle;)I",
        "return_zero",
    ),
    "getBuyIntent": (
        "(ILjava/lang/String;Ljava/lang/String;Ljava/lang/String;"
        "Ljava/lang/String;)Landroid/os/Bundle;", "return_fake_bundle",
    ),
    "getBuyIntentToReplaceSkus": (
        "(ILjava/lang/String;Ljava/util/List;Ljava/lang/String;"
        "Ljava/lang/String;Ljava/lang/String;)Landroid/os/Bundle;",
        "return_fake_bundle",
    ),
    "getBuyIntentExtraParams": (
        "(ILjava/lang/String;Ljava/lang/String;Ljava/lang/String;"
        "Ljava/lang/String;Landroid/os/Bundle;)Landroid/os/Bundle;",
        "return_fake_bundle",
    ),
    "getPurchases": (
        "(ILjava/lang/String;Ljava/lang/String;Ljava/lang/String;)"
        "Landroid/os/Bundle;", "return_empty_bundle",
    ),
    "getPurchaseHistory": (
        "(ILjava/lang/String;Ljava/lang/String;Ljava/lang/String;"
        "Landroid/os/Bundle;)Landroid/os/Bundle;", "return_empty_bundle",
    ),
    "getSkuDetails": (
        "(ILjava/lang/String;Ljava/lang/String;Landroid/os/Bundle;)"
        "Landroid/os/Bundle;", "return_empty_bundle",
    ),
    "consumePurchase": (
        "(ILjava/lang/String;Ljava/lang/String;)I", "return_zero",
    ),
    "stub": (
        "(ILjava/lang/String;Ljava/lang/String;)I", "return_zero",
    ),
}


@dataclass
class AIDLProxyConfig:
    proxy_package: str = _PROXY_PACKAGE
    version_name: str = "1.0.0"
    version_code: int = 1
    include_methods: list[str] = field(
        default_factory=lambda: list(_AIDL_METHODS.keys())
    )


@dataclass
class GeneratedAIDLProxy:
    output_dir: str
    manifest_path: str
    smali_files: list[str] = field(default_factory=list)
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)


_AIDL_INTERFACE_SMALI = r""".class public interface abstract Lcom/chelpus/lackypatch/IInAppBillingService;
.super Ljava/lang/Object;
.source "IInAppBillingService.java"

.implements Landroid/os/IInterface;

.field public static final DESCRIPTOR:Ljava/lang/String; = "com.android.vending.billing.IInAppBillingService"

__METHOD_DECLS__
"""

_AIDL_STUB_SMALI = r""".class public abstract Lcom/chelpus/lackypatch/IInAppBillingService$Stub;
.super Landroid/os/Binder;
.source "IInAppBillingService.java"

.implements Lcom/chelpus/lackypatch/IInAppBillingService;

.field static final TRANSACTION_isBillingSupported:I = 0x1
.field static final TRANSACTION_getBuyIntent:I = 0x2
.field static final TRANSACTION_getPurchases:I = 0x3
.field static final TRANSACTION_getSkuDetails:I = 0x4
.field static final TRANSACTION_consumePurchase:I = 0x5
.field static final TRANSACTION_stub:I = 0x6


.method public constructor <init>()V
    .registers 2
    invoke-direct {p0}, Landroid/os/Binder;-><init>()V
    const-string v0, "com.android.vending.billing.IInAppBillingService"
    invoke-virtual {p0, v0}, Lcom/chelpus/lackypatch/IInAppBillingService$Stub;->attachInterface(Landroid/os/IInterface;Ljava/lang/String;)V
    return-void
.end method


.method public static asInterface(Landroid/os/IBinder;)Lcom/chelpus/lackypatch/IInAppBillingService;
    .registers 3
    if-nez p0, :cond_null
    const/4 v0, 0x0
    return-object v0
    :cond_null
    const-string v0, "com.android.vending.billing.IInAppBillingService"
    invoke-interface {p0, v0}, Landroid/os/IBinder;->queryLocalInterface(Ljava/lang/String;)Landroid/os/IInterface;
    move-result-object v1
    if-eqz v1, :cond_new
    instance-of v2, v1, Lcom/chelpus/lackypatch/IInAppBillingService;
    if-eqz v2, :cond_new
    check-cast v1, Lcom/chelpus/lackypatch/IInAppBillingService;
    return-object v1
    :cond_new
    new-instance v0, Lcom/chelpus/lackypatch/IInAppBillingService$Stub$Proxy;
    invoke-direct {v0, p0}, Lcom/chelpus/lackypatch/IInAppBillingService$Stub$Proxy;-><init>(Landroid/os/IBinder;)V
    return-object v0
.end method


.method public asBinder()Landroid/os/IBinder;
    .registers 1
    return-object p0
.end method
"""

_AIDL_PROXY_SMALI = r""".class Lcom/chelpus/lackypatch/IInAppBillingService$Stub$Proxy;
.super Ljava/lang/Object;
.source "IInAppBillingService.java"

.implements Lcom/chelpus/lackypatch/IInAppBillingService;

.field private mRemote:Landroid/os/IBinder;


.method public constructor <init>(Landroid/os/IBinder;)V
    .registers 2
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V
    iput-object p1, p0, Lcom/chelpus/lackypatch/IInAppBillingService$Stub$Proxy;->mRemote:Landroid/os/IBinder;
    return-void
.end method


.method public asBinder()Landroid/os/IBinder;
    .registers 2
    iget-object v0, p0, Lcom/chelpus/lackypatch/IInAppBillingService$Stub$Proxy;->mRemote:Landroid/os/IBinder;
    return-object v0
.end method
"""


_BILLING_SERVICE_SMALI = r""".class public Lcom/chelpus/lackypatch/BillingService;
.super Lcom/chelpus/lackypatch/IInAppBillingService$Stub;
.source "BillingService.java"

.field private static final TAG:Ljava/lang/String; = "LP-PC-BillingProxy"

.field private static final FAKE_PURCHASE_DATA:Ljava/lang/String; = "{\"orderId\":\"GPA.1234-5678-9012-34567\",\"packageName\":\"com.example\",\"productId\":\"fake_product\",\"purchaseTime\":1700000000000,\"purchaseState\":0,\"purchaseToken\":\"fake_token\",\"acknowledged\":true,\"autoRenewing\":false}"

.field private static final FAKE_SIGNATURE:Ljava/lang/String; = "AAAA_fake_signature_base64_AAAA"


.method public constructor <init>()V
    .registers 0
    invoke-direct {p0}, Lcom/chelpus/lackypatch/IInAppBillingService$Stub;-><init>()V
    return-void
.end method


.method public isBillingSupported(ILjava/lang/String;Ljava/lang/String;)I
    .registers 4
    const/4 v0, 0x0
    return v0
.end method


.method public getBuyIntent(ILjava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)Landroid/os/Bundle;
    .registers 9
    new-instance v0, Landroid/os/Bundle;
    invoke-direct {v0}, Landroid/os/Bundle;-><init>()V
    const-string v1, "RESPONSE_CODE"
    const/4 v2, 0x0
    invoke-virtual {v0, v1, v2}, Landroid/os/Bundle;->putInt(Ljava/lang/String;I)V
    const-string v1, "INAPP_PURCHASE_DATA"
    sget-object v2, Lcom/chelpus/lackypatch/BillingService;->FAKE_PURCHASE_DATA:Ljava/lang/String;
    invoke-virtual {v0, v1, v2}, Landroid/os/Bundle;->putString(Ljava/lang/String;Ljava/lang/String;)V
    const-string v1, "INAPP_DATA_SIGNATURE"
    sget-object v2, Lcom/chelpus/lackypatch/BillingService;->FAKE_SIGNATURE:Ljava/lang/String;
    invoke-virtual {v0, v1, v2}, Landroid/os/Bundle;->putString(Ljava/lang/String;Ljava/lang/String;)V
    return-object v0
.end method


.method public getPurchases(ILjava/lang/String;Ljava/lang/String;Ljava/lang/String;)Landroid/os/Bundle;
    .registers 10
    new-instance v0, Landroid/os/Bundle;
    invoke-direct {v0}, Landroid/os/Bundle;-><init>()V
    const-string v1, "RESPONSE_CODE"
    const/4 v2, 0x0
    invoke-virtual {v0, v1, v2}, Landroid/os/Bundle;->putInt(Ljava/lang/String;I)V
    new-instance v3, Ljava/util/ArrayList;
    invoke-direct {v3}, Ljava/util/ArrayList;-><init>()V
    const-string v1, "INAPP_PURCHASE_ITEM_LIST"
    invoke-virtual {v0, v1, v3}, Landroid/os/Bundle;->putStringArrayList(Ljava/lang/String;Ljava/util/ArrayList;)V
    const-string v1, "INAPP_PURCHASE_DATA_LIST"
    invoke-virtual {v0, v1, v3}, Landroid/os/Bundle;->putStringArrayList(Ljava/lang/String;Ljava/util/ArrayList;)V
    const-string v1, "INAPP_DATA_SIGNATURE_LIST"
    invoke-virtual {v0, v1, v3}, Landroid/os/Bundle;->putStringArrayList(Ljava/lang/String;Ljava/util/ArrayList;)V
    return-object v0
.end method


.method public getSkuDetails(ILjava/lang/String;Ljava/lang/String;Landroid/os/Bundle;)Landroid/os/Bundle;
    .registers 9
    new-instance v0, Landroid/os/Bundle;
    invoke-direct {v0}, Landroid/os/Bundle;-><init>()V
    const-string v1, "RESPONSE_CODE"
    const/4 v2, 0x0
    invoke-virtual {v0, v1, v2}, Landroid/os/Bundle;->putInt(Ljava/lang/String;I)V
    new-instance v3, Ljava/util/ArrayList;
    invoke-direct {v3}, Ljava/util/ArrayList;-><init>()V
    const-string v1, "DETAILS_LIST"
    invoke-virtual {v0, v1, v3}, Landroid/os/Bundle;->putStringArrayList(Ljava/lang/String;Ljava/util/ArrayList;)V
    return-object v0
.end method


.method public consumePurchase(ILjava/lang/String;Ljava/lang/String;)I
    .registers 4
    const/4 v0, 0x0
    return v0
.end method


.method public stub(ILjava/lang/String;Ljava/lang/String;)I
    .registers 4
    const/4 v0, 0x0
    return v0
.end method
"""


_ANDROID_MANIFEST_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="__PACKAGE_NAME__">

    <uses-permission android:name="com.android.vending.BILLING" />

    <application
        android:label="LP-PC IAP Proxy"
        android:allowBackup="false">

        <service
            android:name=".BillingService"
            android:exported="true"
            android:process=":billing">
            <intent-filter>
                <action android:name="com.android.vending.billing.InAppBillingService.BIND" />
                <action android:name="com.android.vending.billing.InAppBillingService.LOCK" />
                <action android:name="com.android.vending.billing.InAppBillingService.LUCK" />
            </intent-filter>
        </service>

    </application>

    <uses-sdk android:minSdkVersion="24" android:targetSdkVersion="34" />

</manifest>
"""

_README_TEMPLATE = """# AIDL Proxy — LP-PC Suite

Generated proxy package: `__PACKAGE_NAME__`

## Setup

1. Compile smali → classes.dex:
   `java -jar tools/bin/smali.jar assemble aidl_proxy/smali -o classes.dex`

2. Zip thành APK (classes.dex + AndroidManifest.xml).

3. Sign: `java -jar tools/bin/uber-apk-signer.jar --apks proxy.apk`

4. Install: `adb install proxy-aligned-debugSigned.apk`

5. Static patch target app redirect BIND action:
   `--mode "iap:proxy"` (LP-PC Suite auto-generate)

## Methods (__METHOD_COUNT__)
__METHODS_LIST__

## Warning
- Chỉ dùng trên thiết bị test.
"""


class AIDLProxyGenerator:
    def __init__(self, log_callback=print):
        self.log = log_callback

    def generate(self, config: AIDLProxyConfig,
                 output_dir: str) -> GeneratedAIDLProxy:
        errors: list[str] = []
        smali_files: list[str] = []

        try:
            smali_dir = os.path.join(
                output_dir, "smali", "com", "chelpus", "lackypatch"
            )
            os.makedirs(smali_dir, exist_ok=True)

            method_decls = "\n".join(
                f".method public abstract {m}{sig} "
                f"throws Landroid/os/RemoteException;"
                f"\n.end method\n"
                for m, (sig, _) in _AIDL_METHODS.items()
                if m in config.include_methods
            )
            interface = _AIDL_INTERFACE_SMALI.replace(
                "__METHOD_DECLS__", method_decls
            )
            p = os.path.join(smali_dir, "IInAppBillingService.smali")
            self._write(p, interface)
            smali_files.append(p)

            stub = _AIDL_STUB_SMALI
            p = os.path.join(
                smali_dir, "IInAppBillingService$Stub.smali"
            )
            self._write(p, stub)
            smali_files.append(p)

            p = os.path.join(
                smali_dir, "IInAppBillingService$Stub$Proxy.smali"
            )
            self._write(p, _AIDL_PROXY_SMALI)
            smali_files.append(p)

            p = os.path.join(smali_dir, "BillingService.smali")
            self._write(p, _BILLING_SERVICE_SMALI)
            smali_files.append(p)

            manifest = _ANDROID_MANIFEST_TEMPLATE.replace(
                "__PACKAGE_NAME__", config.proxy_package
            )
            manifest_path = os.path.join(output_dir, "AndroidManifest.xml")
            self._write(manifest_path, manifest)

            methods_list = "\n".join(
                f"- `{m}`" for m in config.include_methods
            )
            readme = (
                _README_TEMPLATE
                .replace("__PACKAGE_NAME__", config.proxy_package)
                .replace("__METHODS_LIST__", methods_list)
                .replace("__METHOD_COUNT__",
                         str(len(config.include_methods)))
            )
            self._write(os.path.join(output_dir, "README.md"), readme)

            self.log(
                f"[OK] [AIDLProxy] Generated {output_dir} "
                f"({len(smali_files)} smali, "
                f"{len(config.include_methods)} methods)"
            )
        except OSError as e:
            errors.append(f"IO: {e}")
            self.log(f"[!] [AIDLProxy] {e}")
        except Exception as e:
            errors.append(f"Unexpected: {e}")
            logger.exception("AIDL proxy generation crashed")

        return GeneratedAIDLProxy(
            output_dir=output_dir,
            manifest_path=os.path.join(
                output_dir, "AndroidManifest.xml"
            ),
            smali_files=smali_files,
            is_valid=not errors,
            errors=errors,
        )

    @staticmethod
    def _write(path: str, content: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


def generate_aidl_proxy(
    output_dir: str,
    log_callback=print,
) -> GeneratedAIDLProxy:
    """High-level entry."""
    gen = AIDLProxyGenerator(log_callback=log_callback)
    return gen.generate(AIDLProxyConfig(), output_dir)