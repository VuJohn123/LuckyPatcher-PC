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


def test_bundle_method_sets_string_array_list():
    """Clients read INAPP_PURCHASE_DATA_LIST with getStringArrayList()."""
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
        assert patcher.patch() >= 1
        with open(smali) as f:
            content = f.read()
        assert (
            "putStringArrayList(Ljava/lang/String;"
            "Ljava/util/ArrayList;)V"
        ) in content
        assert "new-instance v2, Ljava/util/ArrayList;" in content
        assert "INAPP_PURCHASE_DATA_LIST" in content


def test_skips_abstract_and_native_methods():
    """Regression: rewritten abstract/native methods break apktool."""
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, (
            ".class public abstract LA;\n"
            ".method public abstract queryPurchases()V\n"
            ".end method\n"
            ".method public native getBuyIntent()Landroid/os/Bundle;\n"
            ".end method\n"
        ))
        patcher = IAPDexPatcher(tmp, log_callback=lambda *_: None)
        assert patcher.patch() == 0
        with open(smali) as f:
            content = f.read()
        assert ".method public abstract queryPurchases()V\n.end method" in content
        assert "native getBuyIntent()Landroid/os/Bundle;\n.end method" in content
        assert ".locals" not in content


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


def test_parallel_scan_preserves_results_and_counts():
    with tempfile.TemporaryDirectory() as tmp:
        candidates = []
        for i in range(12):
            path = os.path.join(tmp, "smali", f"C{i}.smali")
            _write(path, (
                f".class public LC{i};\n"
                ".method public static launchBillingFlow()V\n"
                "    invoke-static {}, Lcom/x;->launchBillingFlow()V\n"
                ".end method\n"
            ))
            candidates.append(path)
        for i in range(30):
            _write(os.path.join(tmp, "smali", f"U{i}.smali"), (
                ".class public LU;\n"
                ".method public static foo()V\n"
                "    return-void\n"
                ".end method\n"
            ))

        patcher = IAPDexPatcher(tmp, log_callback=lambda *_: None)
        report = patcher.patch_with_report()

        assert report["total_patched"] == 12
        assert report["scanned_files"] == 42
        assert report["skipped_files"] == 0
        for path in candidates:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            assert ".locals 0" in content
            assert content.count("return-void") == 1


def test_scan_skips_blacklisted_paths_before_read():
    class CountingPatcher(IAPDexPatcher):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.read_paths: list[str] = []

        def _read(self, path: str) -> str:
            self.read_paths.append(path)
            return super()._read(path)

    method = (
        ".class public Lcom/x/NAME;\n"
        ".method public static launchBillingFlow()V\n"
        "    invoke-static {}, Lcom/x;->launchBillingFlow()V\n"
        ".end method\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        tracker = os.path.join(
            tmp, "smali", "com", "x", "analytics", "Tracker.smali",
        )
        _write(tracker, method.replace("NAME", "Tracker"))
        billing = os.path.join(
            tmp, "smali", "com", "x", "billing", "Billing.smali",
        )
        _write(billing, method.replace("NAME", "Billing"))

        patcher = CountingPatcher(tmp, log_callback=lambda *_: None)
        report = patcher.patch_with_report()

        assert report["total_patched"] == 1
        assert report["scanned_files"] == 2
        assert billing in patcher.read_paths
        assert tracker not in patcher.read_paths


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
