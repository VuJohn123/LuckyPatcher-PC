"""Test signature verify patcher."""
import os
import tempfile

from patcher.signature_patcher import SignatureVerifyPatcher


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_patch_check_signature():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, (
            ".class public LA;\n"
            ".method public static checkSignature()Z\n"
            "    .registers 2\n"
            "    const/4 v0, 0x0\n"
            "    return v0\n"
            ".end method\n"
        ))
        patcher = SignatureVerifyPatcher(tmp, log_callback=lambda *_: None)
        count = patcher.patch()
        assert count >= 1
        with open(smali) as f:
            content = f.read()
        assert "const/4 v0, 0x1" in content


def test_skip_unrelated_method():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, (
            ".class public LA;\n"
            ".method public static foo()Z\n"
            "    .registers 2\n"
            "    const/4 v0, 0x0\n"
            "    return v0\n"
            ".end method\n"
        ))
        patcher = SignatureVerifyPatcher(tmp, log_callback=lambda *_: None)
        assert patcher.patch() == 0


def test_patch_verify_purchase():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, (
            ".class public LA;\n"
            ".method public static verifyPurchase()Z\n"
            "    .registers 2\n"
            "    const/4 v0, 0x0\n"
            "    return v0\n"
            ".end method\n"
        ))
        patcher = SignatureVerifyPatcher(tmp, log_callback=lambda *_: None)
        assert patcher.patch() >= 1


def test_patch_method_without_registers_skipped():
    """Method không có .registers → skip để tránh corrupt."""
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _write(smali, (
            ".class public LA;\n"
            ".method public static checkSignature()Z\n"
            "    const/4 v0, 0x0\n"
            "    return v0\n"
            ".end method\n"
        ))
        patcher = SignatureVerifyPatcher(tmp, log_callback=lambda *_: None)
        # REGEX_SIGNATURE_METHOD yêu cầu .registers
        # → method này không match, count = 0
        assert patcher.patch() == 0


def test_empty_dir():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "smali"))
        patcher = SignatureVerifyPatcher(tmp, log_callback=lambda *_: None)
        assert patcher.patch() == 0