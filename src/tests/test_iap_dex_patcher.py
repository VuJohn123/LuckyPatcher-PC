"""Test IAP dex patcher — core IAP logic."""
import os
import tempfile
from unittest.mock import patch

from patcher.iap_dex_patcher import IAPDexPatcher


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_patch_void_method():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, (
            ".class public LA;\n"
            ".method public static launchBillingFlow()V\n"
            "    .locals 1\n"
            "    invoke-static {}, "
            "Lcom/android/billingclient/api/BillingClient;->"
            "launchBillingFlow()V\n"
            "    return-void\n"
            ".end method\n"
        ))
        patcher = IAPDexPatcher(tmp, log_callback=lambda *_: None)
        count = patcher.patch()
        assert count == 1
        with open(smali) as f:
            content = f.read()
        assert "launchBillingFlow" in content
        assert content.count("return-void") >= 1


def test_patch_bundle_method():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, (
            ".class public LA;\n"
            ".method public static getBuyIntent()Landroid/os/Bundle;\n"
            "    .locals 1\n"
            "    const/4 v0, 0x0\n"
            "    return-object v0\n"
            ".end method\n"
        ))
        patcher = IAPDexPatcher(tmp, log_callback=lambda *_: None)
        count = patcher.patch()
        assert count >= 1
        with open(smali) as f:
            content = f.read()
        assert "RESPONSE_CODE" in content


def test_patch_with_report():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, (
            ".class public LA;\n"
            ".method public static launchBillingFlow()V\n"
            "    invoke-static {}, "
            "Lcom/android/billingclient/api/BillingClient;->"
            "launchBillingFlow()V\n"
            ".end method\n"
        ))
        patcher = IAPDexPatcher(tmp, log_callback=lambda *_: None)
        report = patcher.patch_with_report()
        assert "total_patched" in report
        assert report["total_patched"] >= 1
        assert "patterns" in report


def test_no_patch_for_unrelated():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, (
            ".class public LA;\n"
            ".method public static foo()V\n"
            "    return-void\n"
            ".end method\n"
        ))
        patcher = IAPDexPatcher(tmp, log_callback=lambda *_: None)
        assert patcher.patch() == 0


def test_skip_long_path():
    """File path > 250 ký tự phải bị skip.

    Windows giới hạn CreateDirectoryW ~247 ký tự (sớm hơn MAX_PATH 260),
    nên không thể tạo file thật để test. Mock get_all_smali_files để
    trả về path dài → verify logic length-check của patcher.
    """
    with tempfile.TemporaryDirectory() as tmp:
        long_path = os.path.join(
            tmp, "smali",
            *[("x" * 40) for _ in range(7)],
            "A.smali",
        )
        assert len(long_path) > 250, f"Path chưa đủ dài: {len(long_path)}"

        with patch(
            "patcher.iap_dex_patcher.get_all_smali_files",
            return_value=[long_path],
        ):
            patcher = IAPDexPatcher(tmp, log_callback=lambda *_: None)
            assert patcher.patch() == 0


def test_unity_purchasing_detected():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, (
            ".class public LA;\n"
            ".method public static InitiatePurchase()V\n"
            "    invoke-static {}, Lcom/x;->InitiatePurchase()V\n"
            ".end method\n"
        ))
        patcher = IAPDexPatcher(tmp, log_callback=lambda *_: None)
        assert patcher.patch() >= 1