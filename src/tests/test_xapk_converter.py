"""Unit tests cho xapk_converter — cover happy path + edge cases."""
import os
import tempfile
import zipfile

import pytest

from core.xapk_converter import (
    XAPKConversionError,
    convert_xapk_to_apk,
    is_xapk,
)


def _make_xapk(tmpdir: str, package: str = "com.test.app",
               with_split: bool = False) -> str:
    xapk_path = os.path.join(tmpdir, "test.xapk")

    base_buf = os.path.join(tmpdir, "_base.apk")
    with zipfile.ZipFile(base_buf, "w") as z:
        z.writestr("AndroidManifest.xml", f'<manifest package="{package}"/>')
        z.writestr("classes.dex", b"\x64\x65\x78\x0a")

    with zipfile.ZipFile(xapk_path, "w") as z:
        z.writestr("manifest.json", f'{{"package_name": "{package}"}}')
        z.write(base_buf, f"{package}.apk")
        if with_split:
            split_buf = os.path.join(tmpdir, "_split.apk")
            with zipfile.ZipFile(split_buf, "w") as sz:
                sz.writestr("config.arm64_v8a", b"split-data")
            z.write(split_buf, "config.arm64_v8a.apk")

    return xapk_path


# -------- is_xapk --------
def test_is_xapk_valid():
    with tempfile.TemporaryDirectory() as tmp:
        assert is_xapk(_make_xapk(tmp)) is True


def test_is_xapk_rejects_regular_zip():
    with tempfile.TemporaryDirectory() as tmp:
        fake = os.path.join(tmp, "fake.zip")
        with zipfile.ZipFile(fake, "w") as z:
            z.writestr("file.txt", "hello")
        assert is_xapk(fake) is False


def test_is_xapk_rejects_nonexistent():
    assert is_xapk("/path/does/not/exist.xapk") is False


def test_is_xapk_rejects_corrupt_zip():
    with tempfile.TemporaryDirectory() as tmp:
        fake = os.path.join(tmp, "corrupt.xapk")
        with open(fake, "wb") as f:
            f.write(b"not a zip file at all")
        assert is_xapk(fake) is False


# -------- convert --------
def test_convert_simple_xapk():
    with tempfile.TemporaryDirectory() as tmp:
        xapk = _make_xapk(tmp)
        apk = convert_xapk_to_apk(xapk, tmp, log_callback=lambda *_: None)
        assert os.path.exists(apk)
        assert apk.endswith(".apk")
        with zipfile.ZipFile(apk) as z:
            names = z.namelist()
            assert "AndroidManifest.xml" in names
            assert "classes.dex" in names


def test_convert_split_xapk_merges_all_parts():
    with tempfile.TemporaryDirectory() as tmp:
        xapk = _make_xapk(tmp, with_split=True)
        apk = convert_xapk_to_apk(xapk, tmp, log_callback=lambda *_: None)
        with zipfile.ZipFile(apk) as z:
            names = z.namelist()
            assert "AndroidManifest.xml" in names
            assert "config.arm64_v8a" in names


def test_convert_rejects_invalid_xapk():
    with tempfile.TemporaryDirectory() as tmp:
        fake = os.path.join(tmp, "fake.xapk")
        with zipfile.ZipFile(fake, "w") as z:
            z.writestr("random.txt", "nope")
        with pytest.raises(XAPKConversionError):
            convert_xapk_to_apk(fake, tmp, log_callback=lambda *_: None)


def test_convert_rejects_nonexistent():
    with pytest.raises(XAPKConversionError):
        convert_xapk_to_apk("/no/such/file.xapk", log_callback=lambda *_: None)


def test_path_traversal_blocked():
    """ZipSlip: entry ../ không được extract ra ngoài dest."""
    with tempfile.TemporaryDirectory() as tmp:
        evil = os.path.join(tmp, "evil.xapk")
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("manifest.json", '{"package_name": "x"}')
            z.writestr("base.apk", b"\x50\x4b\x03\x04")  # empty zip magic
            z.writestr("../../../etc/passwd", "pwned")
        with pytest.raises(XAPKConversionError):
            convert_xapk_to_apk(evil, tmp, log_callback=lambda *_: None)


def test_no_apk_inside_xapk():
    """manifest.json có nhưng không có .apk nào."""
    with tempfile.TemporaryDirectory() as tmp:
        bad = os.path.join(tmp, "empty.xapk")
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("manifest.json", '{"package_name": "x"}')
            z.writestr("readme.txt", "no apk here")
        with pytest.raises(XAPKConversionError):
            convert_xapk_to_apk(bad, tmp, log_callback=lambda *_: None)