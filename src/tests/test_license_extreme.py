"""Test license extreme — 5 modes."""
import os
import tempfile

from patcher.license_extreme import LicenseExtremePatcher


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _sample_with_license_invoke():
    return (
        ".class public LA;\n"
        ".method public static foo()V\n"
        "    invoke-static {}, "
        "Lcom/google/android/vending/licensing/LicenseChecker;->"
        "checkAccess()V\n"
        "    return-void\n"
        ".end method\n"
    )


def test_patch_extreme_removes_invoke():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, _sample_with_license_invoke())
        patcher = LicenseExtremePatcher(tmp, log_callback=lambda *_: None)
        count = patcher.patch_extreme()
        assert count == 1
        with open(smali) as f:
            content = f.read()
        assert "LicenseChecker" not in content


def test_reverse_auto_same_as_extreme():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, _sample_with_license_invoke())
        patcher = LicenseExtremePatcher(tmp, log_callback=lambda *_: None)
        assert patcher.patch_reverse_auto() == 1


def test_amazon_mode_no_crash():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, (
            ".class public LA;\n"
            ".method public static amazonAllow()Z\n"
            "    .locals 1\n"
            "    const/4 v0, 0x0\n"
            "    return v0\n"
            ".end method\n"
        ))
        patcher = LicenseExtremePatcher(tmp, log_callback=lambda *_: None)
        count = patcher.patch_amazon_market()
        assert isinstance(count, int)


def test_samsung_mode_no_crash():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, (
            ".class public LA;\n"
            ".method public static samsungVerify()Z\n"
            "    .locals 1\n"
            "    const/4 v0, 0x0\n"
            "    return v0\n"
            ".end method\n"
        ))
        patcher = LicenseExtremePatcher(tmp, log_callback=lambda *_: None)
        count = patcher.patch_samsung_apps()
        assert isinstance(count, int)


def test_patch_interface():
    """Interface patch() phải hoạt động."""
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, _sample_with_license_invoke())
        patcher = LicenseExtremePatcher(tmp, log_callback=lambda *_: None)
        # patch() gọi patch_extreme() bên trong
        assert patcher.patch() == 1


def test_empty_dir():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "smali"))
        patcher = LicenseExtremePatcher(tmp, log_callback=lambda *_: None)
        assert patcher.patch_extreme() == 0