"""Test SignatureIntegrityPatcher — vô hiệu hóa integrity check."""
import os
import tempfile

from patcher.signature_integrity_patcher import SignatureIntegrityPatcher


def _w(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_patch_integrity_check_with_messagedigest():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _w(smali, (
            ".class public LA;\n"
            ".method public static checkIntegrity()Z\n"
            "    .locals 2\n"
            "    invoke-static {}, "
            "Ljava/security/MessageDigest;->getInstance()"
            "Ljava/security/MessageDigest;\n"
            "    const/4 v0, 0x0\n"
            "    return v0\n"
            ".end method\n"
        ))
        p = SignatureIntegrityPatcher(tmp, log_callback=lambda *_: None)
        assert p.patch() >= 1
        with open(smali) as f:
            content = f.read()
        assert "const/4 v0, 0x1" in content


def test_patch_verify_hash():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "B.smali")
        _w(smali, (
            ".class public LB;\n"
            ".method public static verifyHash()Z\n"
            "    .locals 1\n"
            "    const/4 v0, 0x0\n"
            "    return v0\n"
            ".end method\n"
        ))
        p = SignatureIntegrityPatcher(tmp, log_callback=lambda *_: None)
        # File không có MessageDigest/Signature → skip
        assert p.patch() == 0


def test_skip_unrelated_boolean_method():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "C.smali")
        _w(smali, (
            ".class public LC;\n"
            ".method public static isEnabled()Z\n"
            "    .locals 1\n"
            "    const/4 v0, 0x0\n"
            "    return v0\n"
            ".end method\n"
            "    const-string v0, \"Signature\"\n"
        ))
        p = SignatureIntegrityPatcher(tmp, log_callback=lambda *_: None)
        # Không có method tên integrity/verify/check/hash/digest → skip
        p.patch()  # không crash


def test_empty_dir():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "smali"))
        p = SignatureIntegrityPatcher(tmp, log_callback=lambda *_: None)
        assert p.patch() == 0


def test_multiple_integrity_methods():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "D.smali")
        _w(smali, (
            ".class public LD;\n"
            ".method public static checkIntegrity()Z\n"
            "    .locals 1\n"
            "    const/4 v0, 0x0\n"
            "    return v0\n"
            ".end method\n"
            ".method public static verifyDigest()Z\n"
            "    .locals 1\n"
            "    const/4 v0, 0x0\n"
            "    return v0\n"
            ".end method\n"
            "    const-string v0, \"MessageDigest\"\n"
        ))
        p = SignatureIntegrityPatcher(tmp, log_callback=lambda *_: None)
        count = p.patch()
        assert count >= 1