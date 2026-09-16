"""Test SignatureFakeArchivePatcher."""
import os
import tempfile

from patcher.signature_fake_archive_patcher import SignatureFakeArchivePatcher


def _w(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_patch_zip_entry_check():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "A.smali")
        _w(smali, (
            ".class public LA;\n"
            ".method public static checkZipEntry()Z\n"
            "    .locals 1\n"
            "    const/4 v0, 0x0\n"
            "    return v0\n"
            ".end method\n"
            "    const-string v0, \"ZipEntry\"\n"
        ))
        p = SignatureFakeArchivePatcher(tmp, log_callback=lambda *_: None)
        assert p.patch() >= 1


def test_no_zip_keyword_skips():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "B.smali")
        _w(smali, (
            ".class public LB;\n"
            ".method public static foo()V\n"
            "    return-void\n"
            ".end method\n"
        ))
        p = SignatureFakeArchivePatcher(tmp, log_callback=lambda *_: None)
        assert p.patch() == 0


def test_getentry_keyword():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "C.smali")
        _w(smali, (
            ".class public LC;\n"
            ".method public static validateApk()Z\n"
            "    .locals 1\n"
            "    const/4 v0, 0x0\n"
            "    return v0\n"
            ".end method\n"
            "    const-string v0, \"getEntry\"\n"
        ))
        p = SignatureFakeArchivePatcher(tmp, log_callback=lambda *_: None)
        p.patch()  # không crash


def test_empty_dir():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "smali"))
        p = SignatureFakeArchivePatcher(tmp, log_callback=lambda *_: None)
        assert p.patch() == 0