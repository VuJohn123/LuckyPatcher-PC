"""Test IAP patcher nhận diện Unity + wrapper patterns."""
import os
import tempfile

from patcher.iap_dex_patcher import IAPDexPatcher


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_unity_initiate_purchase_patched():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(
            tmp, "smali", "com", "unity", "purchasing",
            "UnityPurchasing.smali"
        )
        _write(smali, (
            ".class public Lcom/unity/purchasing/UnityPurchasing;\n"
            ".method public static InitiatePurchase()V\n"
            "    .locals 1\n"
            "    invoke-static {}, Lcom/x;->do()V\n"
            "    return-void\n"
            ".end method\n"
        ))
        patcher = IAPDexPatcher(tmp, log_callback=lambda *_: None)
        count = patcher.patch()
        assert count >= 1


def test_wrapper_class_iap_manager_patched():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(
            tmp, "smali", "com", "example", "IAPManager.smali"
        )
        _write(smali, (
            ".class public Lcom/example/IAPManager;\n"
            ".method public static buyProduct()V\n"
            "    invoke-static {}, Lcom/x;->go()V\n"
            "    return-void\n"
            ".end method\n"
        ))
        patcher = IAPDexPatcher(tmp, log_callback=lambda *_: None)
        assert patcher.patch() >= 1


def test_analytics_class_skipped():
    """Analytics class không nên bị patch dù có method tên giống."""
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(
            tmp, "smali", "com", "example", "AnalyticsTracker.smali"
        )
        _write(smali, (
            ".class public Lcom/example/AnalyticsTracker;\n"
            ".method public static onPurchase()V\n"
            "    invoke-static {}, Lcom/x;->log()V\n"
            "    return-void\n"
            ".end method\n"
        ))
        patcher = IAPDexPatcher(tmp, log_callback=lambda *_: None)
        assert patcher.patch() == 0


def test_unrelated_class_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(
            tmp, "smali", "com", "example", "MainActivity.smali"
        )
        _write(smali, (
            ".class public Lcom/example/MainActivity;\n"
            ".method public static onCreate()V\n"
            "    return-void\n"
            ".end method\n"
        ))
        patcher = IAPDexPatcher(tmp, log_callback=lambda *_: None)
        assert patcher.patch() == 0


def test_billing_client_class_patched():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(
            tmp, "smali", "com", "android", "billingclient", "api",
            "BillingClient.smali"
        )
        _write(smali, (
            ".class public Lcom/android/billingclient/api/BillingClient;\n"
            ".method public static launchBillingFlow()V\n"
            "    invoke-static {}, Lcom/x;->go()V\n"
            "    return-void\n"
            ".end method\n"
        ))
        patcher = IAPDexPatcher(tmp, log_callback=lambda *_: None)
        assert patcher.patch() >= 1


def test_bundle_method_returns_response_code():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(
            tmp, "smali", "com", "android", "billingclient", "api",
            "BillingClient.smali"
        )
        _write(smali, (
            ".class public Lcom/android/billingclient/api/BillingClient;\n"
            ".method public static getBuyIntent()Landroid/os/Bundle;\n"
            "    .locals 1\n"
            "    const/4 v0, 0x0\n"
            "    return-object v0\n"
            ".end method\n"
        ))
        patcher = IAPDexPatcher(tmp, log_callback=lambda *_: None)
        assert patcher.patch() >= 1
        with open(smali) as f:
            content = f.read()
        assert "RESPONSE_CODE" in content