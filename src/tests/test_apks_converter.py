"""Test .apks converter — 4 layouts."""
import io
import os
import tempfile
import zipfile

import pytest

from core.apks_converter import (
    APKSConversionError,
    convert_apks_to_apk,
    is_apks,
    is_bundle_zip,
)


def _make_zip(path: str, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)


def _fake_apk_bytes() -> bytes:
    """
    Valid ZIP bytes đóng vai APK — để test merge có thể mở bằng
    zipfile.ZipFile(). Nội dung giả không quan trọng, chỉ cần ZIP valid.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("AndroidManifest.xml", b"<manifest/>")
        z.writestr("classes.dex", b"dex-content-placeholder")
    return buf.getvalue()


def _fake_split_bytes(marker: bytes) -> bytes:
    """Split ZIP giả — chứa 1 file unique để test merge không trùng."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"split-{marker.decode()}.txt", marker)
    return buf.getvalue()


# ============================================================
# is_apks / is_bundle_zip
# ============================================================
def test_is_apks_rejects_missing():
    assert not is_apks("/nonexistent.apks")


def test_is_apks_rejects_non_zip(tmp_path):
    p = tmp_path / "fake.apks"
    p.write_bytes(b"not a zip")
    assert not is_apks(str(p))


def test_is_apks_requires_toc_pb(tmp_path):
    p = tmp_path / "test.apks"
    _make_zip(str(p), {"some.txt": b"data"})
    assert not is_apks(str(p))


def test_is_apks_detects_bundletool(tmp_path):
    p = tmp_path / "test.apks"
    _make_zip(str(p), {
        "toc.pb": b"proto",
        "universal.apk": _fake_apk_bytes(),
    })
    assert is_apks(str(p))


def test_is_bundle_zip_detects_any_apk(tmp_path):
    p = tmp_path / "bundle.zip"
    _make_zip(str(p), {"base.apk": _fake_apk_bytes()})
    assert is_bundle_zip(str(p))


# ============================================================
# Convert layouts
# ============================================================
def test_convert_universal(tmp_path):
    p = tmp_path / "test.apks"
    _make_zip(str(p), {
        "toc.pb": b"proto",
        "universal.apk": _fake_apk_bytes(),
    })
    out = convert_apks_to_apk(str(p), log_callback=lambda *_: None)
    assert os.path.exists(out)
    assert out.endswith(".apk")


def test_convert_standalones(tmp_path):
    p = tmp_path / "test.apks"
    _make_zip(str(p), {
        "toc.pb": b"proto",
        "standalones/standalone-arm64_v8a.apk": _fake_apk_bytes(),
        "standalones/standalone-armeabi.apk": _fake_split_bytes(b"arm"),
    })
    out = convert_apks_to_apk(str(p), log_callback=lambda *_: None)
    assert os.path.exists(out)
    # Output phải là valid ZIP
    with zipfile.ZipFile(out, "r") as z:
        names = z.namelist()
    assert "AndroidManifest.xml" in names


def test_convert_root_splits_apkcube(tmp_path):
    """APKPure apkcube layout: base.apk + split_config.*.apk ở root."""
    p = tmp_path / "apkcube.apks"
    _make_zip(str(p), {
        "base.apk": _fake_apk_bytes(),
        "split_config.arm64_v8a.apk": _fake_split_bytes(b"arm64"),
        "split_config.xxhdpi.apk": _fake_split_bytes(b"xxhdpi"),
    })
    out = convert_apks_to_apk(str(p), log_callback=lambda *_: None)
    assert os.path.exists(out)
    # Output phải merge cả base + splits
    with zipfile.ZipFile(out, "r") as z:
        names = z.namelist()
    assert "AndroidManifest.xml" in names
    assert "split-arm64.txt" in names
    assert "split-xxhdpi.txt" in names


def test_convert_rejects_no_apk(tmp_path):
    p = tmp_path / "bad.apks"
    _make_zip(str(p), {"toc.pb": b"proto", "readme.txt": b"nothing"})
    with pytest.raises(APKSConversionError):
        convert_apks_to_apk(str(p), log_callback=lambda *_: None)


def test_convert_rejects_nonexistent():
    with pytest.raises(APKSConversionError):
        convert_apks_to_apk(
            "/nonexistent.apks", log_callback=lambda *_: None
        )


def test_convert_zip_slip_blocked(tmp_path):
    p = tmp_path / "evil.apks"
    _make_zip(str(p), {
        "toc.pb": b"proto",
        "../../etc/passwd": b"malicious",
    })
    with pytest.raises(APKSConversionError):
        convert_apks_to_apk(str(p), log_callback=lambda *_: None)