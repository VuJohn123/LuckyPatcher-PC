"""Test patcher/fast_apk_patcher.py."""
import os
import zipfile

import pytest

from patcher.fast_apk_patcher import FastAPKPatcher


def _make_apk(tmp_path, files: dict[str, bytes]) -> str:
    apk = tmp_path / "test.apk"
    with zipfile.ZipFile(apk, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return str(apk)


def test_init(tmp_path):
    apk = _make_apk(tmp_path, {"AndroidManifest.xml": b"<manifest/>"})
    p = FastAPKPatcher(apk)
    assert p.apk_path == apk


def test_patch_zip_entry_default_output(tmp_path):
    apk = _make_apk(tmp_path, {"test.txt": b"hello world"})
    p = FastAPKPatcher(apk)
    result = p.patch_zip_entry(
        "test.txt", "hello", "goodbye"
    )
    assert result is not None
    assert os.path.exists(result)

    # Verify content changed
    with zipfile.ZipFile(result, "r") as z:
        assert z.read("test.txt") == b"goodbye world"


def test_patch_zip_entry_custom_output(tmp_path):
    apk = _make_apk(tmp_path, {"test.txt": b"original"})
    out = str(tmp_path / "custom.apk")
    p = FastAPKPatcher(apk)
    result = p.patch_zip_entry("test.txt", "original", "modified", out)
    assert result == out


def test_patch_zip_entry_nonexistent_entry(tmp_path):
    """Entry không tồn tại → không crash, output giống input."""
    apk = _make_apk(tmp_path, {"real.txt": b"data"})
    p = FastAPKPatcher(apk)
    out = str(tmp_path / "out.apk")
    result = p.patch_zip_entry("fake.txt", "x", "y", out)
    assert result == out


def test_patch_zip_entry_bad_apk(tmp_path):
    bad = tmp_path / "bad.apk"
    bad.write_bytes(b"not a zip")
    p = FastAPKPatcher(str(bad))
    result = p.patch_zip_entry("test.txt", "a", "b")
    assert result is None


def test_patch_returns_zero(tmp_path):
    """Interface stub."""
    apk = _make_apk(tmp_path, {"test.txt": b"x"})
    p = FastAPKPatcher(apk)
    assert p.patch() == 0