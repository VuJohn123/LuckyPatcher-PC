"""Test watermarker — add + check."""
import os
import tempfile
import zipfile

from patcher.watermarker import Watermarker


def test_add_and_check_watermark(tmp_path):
    # Tạo APK giả
    apk = tmp_path / "app.apk"
    with zipfile.ZipFile(apk, "w") as z:
        z.writestr("classes.dex", b"x")

    decompiled = tmp_path / "decompiled"
    decompiled.mkdir()
    (decompiled / "assets").mkdir()

    Watermarker.add_watermark(str(decompiled), ["license"], str(apk))

    # Verify marker file
    marker = decompiled / "assets" / "lp_pc_suite_marker.json"
    assert marker.exists()

    # Đóng gói APK mới với marker và check
    new_apk = tmp_path / "new.apk"
    with zipfile.ZipFile(new_apk, "w") as z:
        z.writestr("assets/lp_pc_suite_marker.json", marker.read_bytes())

    result = Watermarker.check_watermark(str(new_apk))
    assert result is not None
    assert result["patches"] == ["license"]


def test_check_watermark_missing(tmp_path):
    apk = tmp_path / "empty.apk"
    with zipfile.ZipFile(apk, "w") as z:
        z.writestr("classes.dex", b"x")
    assert Watermarker.check_watermark(str(apk)) is None