"""Test regex-based patchers với smali/manifest tạm."""
import os
import tempfile

from patcher.ad_remover import AdRemover
from patcher.license_patcher import LicensePatcher
from patcher.permission_changer import PermissionChanger


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_ad_remover_removes_activity():
    with tempfile.TemporaryDirectory() as tmp:
        manifest = os.path.join(tmp, "AndroidManifest.xml")
        _write(manifest, (
            '<manifest>'
            '<application>'
            '<activity android:name="com.ads.AdActivity"/>'
            '<activity android:name="com.app.MainActivity"/>'
            '</application></manifest>'
        ))
        remover = AdRemover(tmp)
        removed = remover.remove_activities(["com.ads.AdActivity"])
        assert removed is True
        with open(manifest) as f:
            content = f.read()
        assert "AdActivity" not in content
        assert "MainActivity" in content


def test_permission_changer_removes():
    with tempfile.TemporaryDirectory() as tmp:
        manifest = os.path.join(tmp, "AndroidManifest.xml")
        _write(manifest, (
            '<manifest>'
            '<uses-permission android:name="android.permission.READ_SMS"/>'
            '<uses-permission android:name="android.permission.INTERNET"/>'
            '</manifest>'
        ))
        pc = PermissionChanger(tmp)
        assert pc.remove_permissions() is True
        with open(manifest) as f:
            content = f.read()
        assert "READ_SMS" not in content
        assert "INTERNET" in content


def test_license_patcher_patches_allow():
    """Test realistic: file smali phải chứa LicenseValidator context."""
    with tempfile.TemporaryDirectory() as tmp:
        # Path mô phỏng đúng package google licensing
        smali = os.path.join(
            tmp, "smali", "com", "google", "android", "vending",
            "licensing", "LicenseValidator.smali",
        )
        _write(smali, (
            ".class public Lcom/google/android/vending/licensing/LicenseValidator;\n"
            ".super Ljava/lang/Object;\n"
            "\n"
            ".method public static allow()Z\n"
            "    .locals 1\n"
            "    const/4 v0, 0x0\n"
            "    return v0\n"
            ".end method\n"
        ))
        patcher = LicensePatcher(tmp)
        count = patcher.patch_license_check()
        assert count == 1
        with open(smali) as f:
            content = f.read()
        assert "const/4 v0, 0x1" in content
        assert "const/4 v0, 0x0" not in content


def test_license_patcher_skips_unrelated_file():
    """File không có LicenseValidator/LicenseCheckerCallback phải bị skip."""
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "com", "test", "A.smali")
        _write(smali, (
            ".class public Lcom/test/A;\n"
            ".method public static allow()Z\n"
            "    .locals 1\n"
            "    const/4 v0, 0x0\n"
            "    return v0\n"
            ".end method\n"
        ))
        patcher = LicensePatcher(tmp)
        count = patcher.patch_license_check()
        assert count == 0