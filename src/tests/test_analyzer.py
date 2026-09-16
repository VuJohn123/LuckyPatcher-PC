"""Test AppDeepAnalyzer — full analyzer với mock APK + DEX."""
import os
import tempfile
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from scanner.analyzer import AppDeepAnalyzer


def _make_apk_file(tmp_path):
    """Tạo APK ZIP tối thiểu có classes.dex."""
    apk = tmp_path / "test.apk"
    with zipfile.ZipFile(apk, "w") as z:
        z.writestr("AndroidManifest.xml", b"<manifest/>")
        z.writestr("classes.dex", b"\x00" * 20)
    return str(apk)


def _make_mock_apk():
    """Mock APK instance trả về metadata cơ bản."""
    m = MagicMock()
    m.get_package.return_value = "com.example.app"
    m.get_app_name.return_value = "Example App"
    m.get_androidversion_name.return_value = "1.2.3"
    m.get_permissions.return_value = []
    m.get_activities.return_value = []
    m.get_services.return_value = []
    m.get_receivers.return_value = []
    m.get_providers.return_value = []
    return m


# ============================================================
# Constructor + analyze cache
# ============================================================
def test_analyzer_constructor(tmp_path):
    apk = _make_apk_file(tmp_path)
    with patch("scanner.analyzer.APK", return_value=_make_mock_apk()):
        a = AppDeepAnalyzer(apk)
        assert a.apk_path == apk
        assert a.findings == []
        assert a.available_patches == []


def test_analyze_uses_cache(tmp_path):
    apk = _make_apk_file(tmp_path)
    cached = {
        "findings": [{"type": "cached", "action": "x"}],
        "colors": ["red"],
        "summary": {},
    }

    with patch("scanner.analyzer.APK", return_value=_make_mock_apk()), \
         patch.object(
             AppDeepAnalyzer, "_check_watermark"
         ), \
         patch("scanner.analyzer.APKCache") as mock_cache:
        mock_cache.return_value.get_cached_analysis.return_value = cached
        a = AppDeepAnalyzer(apk)
        result = a.analyze()
        assert result == cached["findings"]
        assert a.available_patches == ["x"]


# ============================================================
# get_colors
# ============================================================
def test_get_colors_empty_returns_white(tmp_path):
    apk = _make_apk_file(tmp_path)
    with patch("scanner.analyzer.APK", return_value=_make_mock_apk()):
        a = AppDeepAnalyzer(apk)
        a.findings = []
        assert a.get_colors() == ["white"]


def test_get_colors_dedup(tmp_path):
    apk = _make_apk_file(tmp_path)
    with patch("scanner.analyzer.APK", return_value=_make_mock_apk()):
        a = AppDeepAnalyzer(apk)
        a.findings = [
            {"color": "green"}, {"color": "green"}, {"color": "blue"},
        ]
        colors = a.get_colors()
        assert set(colors) == {"green", "blue"}


# ============================================================
# get_summary
# ============================================================
def test_get_summary(tmp_path):
    apk = _make_apk_file(tmp_path)
    mock_apk = _make_mock_apk()
    with patch("scanner.analyzer.APK", return_value=mock_apk):
        a = AppDeepAnalyzer(apk)
        s = a.get_summary()
        assert s["app_name"] == "Example App"
        assert s["package"] == "com.example.app"
        assert s["version"] == "1.2.3"
        assert s["size"] > 0


def test_get_summary_apk_errors(tmp_path):
    apk = _make_apk_file(tmp_path)
    mock = MagicMock()
    mock.get_package.side_effect = Exception("no pkg")
    mock.get_app_name.side_effect = Exception("no name")
    mock.get_androidversion_name.side_effect = Exception("no ver")
    with patch("scanner.analyzer.APK", return_value=mock):
        a = AppDeepAnalyzer(apk)
        s = a.get_summary()
        assert s["package"] == ""
        assert s["app_name"]  # fallback to stem


# ============================================================
# _get_all_dex_bytes
# ============================================================
def test_get_all_dex_bytes(tmp_path):
    apk = tmp_path / "test.apk"
    with zipfile.ZipFile(apk, "w") as z:
        z.writestr("classes.dex", b"dex1")
        z.writestr("classes2.dex", b"dex2")
        z.writestr("resources.arsc", b"res")

    with patch("scanner.analyzer.APK", return_value=_make_mock_apk()):
        a = AppDeepAnalyzer(str(apk))
        dexs = a._get_all_dex_bytes()
        names = [n for n, _ in dexs]
        assert "classes.dex" in names
        assert "classes2.dex" in names
        assert "resources.arsc" not in names


def test_get_all_dex_bytes_bad_zip(tmp_path):
    apk = tmp_path / "bad.apk"
    apk.write_bytes(b"not a zip")
    with patch("scanner.analyzer.APK", return_value=_make_mock_apk()):
        a = AppDeepAnalyzer(str(apk))
        assert a._get_all_dex_bytes() == []


# ============================================================
# _check_watermark
# ============================================================
def test_check_watermark_no_marker(tmp_path):
    apk = _make_apk_file(tmp_path)
    with patch("scanner.analyzer.APK", return_value=_make_mock_apk()), \
         patch(
             "scanner.analyzer.Watermarker.check_watermark",
             return_value=None,
         ):
        a = AppDeepAnalyzer(apk)
        a._check_watermark()
        assert a.findings == []


def test_check_watermark_with_marker(tmp_path):
    apk = _make_apk_file(tmp_path)
    with patch("scanner.analyzer.APK", return_value=_make_mock_apk()), \
         patch(
             "scanner.analyzer.Watermarker.check_watermark",
             return_value={
                 "timestamp": 1700000000,
                 "patches": ["license"],
             },
         ):
        a = AppDeepAnalyzer(apk)
        a._check_watermark()
        assert len(a.findings) == 1
        assert a.findings[0]["type"] == "watermark"


# ============================================================
# _check_custom_patch
# ============================================================
def test_check_custom_patch_empty_dir(tmp_path):
    apk = _make_apk_file(tmp_path)
    patches_dir = tmp_path / "patches"
    patches_dir.mkdir()

    with patch("scanner.analyzer.APK", return_value=_make_mock_apk()):
        a = AppDeepAnalyzer(apk, patches_dir=str(patches_dir))
        a._check_custom_patch()
        assert any(f["type"] == "no_custom_patch" for f in a.findings)


def test_check_custom_patch_with_files(tmp_path):
    apk = _make_apk_file(tmp_path)
    patches_dir = tmp_path / "patches"
    patches_dir.mkdir()
    (patches_dir / "test.txt").write_text("patch")
    (patches_dir / "test.lpzip").write_text("patch")

    with patch("scanner.analyzer.APK", return_value=_make_mock_apk()):
        a = AppDeepAnalyzer(apk, patches_dir=str(patches_dir))
        a._check_custom_patch()
        assert any(f["type"] == "custom_patch" for f in a.findings)
        assert "custom" in a.available_patches


# ============================================================
# _check_system_app
# ============================================================
def test_check_system_app_regular(tmp_path):
    apk = _make_apk_file(tmp_path)
    with patch("scanner.analyzer.APK", return_value=_make_mock_apk()):
        a = AppDeepAnalyzer(apk)
        a._check_system_app()
        # com.example.app không phải system → không finding
        assert all(
            f["type"] not in ("system", "system_boot")
            for f in a.findings
        )


def test_check_system_app_android_pkg(tmp_path):
    apk = _make_apk_file(tmp_path)
    mock = _make_mock_apk()
    mock.get_package.return_value = "com.android.systemui"
    mock.get_receivers.return_value = []
    with patch("scanner.analyzer.APK", return_value=mock):
        a = AppDeepAnalyzer(apk)
        a._check_system_app()
        assert any(f["type"] == "system" for f in a.findings)


def test_check_system_app_boot_receiver(tmp_path):
    apk = _make_apk_file(tmp_path)
    mock = _make_mock_apk()
    mock.get_package.return_value = "com.android.test"
    mock.get_receivers.return_value = [
        "com.x.BootReceiver BOOT_COMPLETED"
    ]
    with patch("scanner.analyzer.APK", return_value=mock):
        a = AppDeepAnalyzer(apk)
        a._check_system_app()
        assert any(f["type"] == "system_boot" for f in a.findings)


# ============================================================
# _check_dangerous_permissions
# ============================================================
def test_check_dangerous_permissions_found(tmp_path):
    apk = _make_apk_file(tmp_path)
    mock = _make_mock_apk()
    mock.get_permissions.return_value = [
        "android.permission.READ_SMS",
        "android.permission.CAMERA",
        "android.permission.INTERNET",
    ]
    with patch("scanner.analyzer.APK", return_value=mock):
        a = AppDeepAnalyzer(apk)
        a._check_dangerous_permissions()
        assert any(f["type"] == "permissions" for f in a.findings)


def test_check_dangerous_permissions_none(tmp_path):
    apk = _make_apk_file(tmp_path)
    mock = _make_mock_apk()
    mock.get_permissions.return_value = [
        "android.permission.INTERNET",
    ]
    with patch("scanner.analyzer.APK", return_value=mock):
        a = AppDeepAnalyzer(apk)
        a._check_dangerous_permissions()
        assert not any(f["type"] == "permissions" for f in a.findings)


def test_check_dangerous_permissions_apk_error(tmp_path):
    apk = _make_apk_file(tmp_path)
    mock = _make_mock_apk()
    mock.get_permissions.side_effect = Exception("broken")
    with patch("scanner.analyzer.APK", return_value=mock):
        a = AppDeepAnalyzer(apk)
        a._check_dangerous_permissions()  # Không crash
        assert a.findings == []


# ============================================================
# _count_components
# ============================================================
def test_count_components(tmp_path):
    apk = _make_apk_file(tmp_path)
    mock = _make_mock_apk()
    mock.get_activities.return_value = ["a", "b"]
    mock.get_services.return_value = ["s1"]
    mock.get_receivers.return_value = ["r1", "r2"]
    mock.get_providers.return_value = ["p1"]
    with patch("scanner.analyzer.APK", return_value=mock):
        a = AppDeepAnalyzer(apk)
        a._count_components()
        assert any(f["type"] == "components" for f in a.findings)
        desc = next(
            f["description"] for f in a.findings
            if f["type"] == "components"
        )
        assert "Activities: 2" in desc
        assert "Services: 1" in desc


def test_count_components_apk_error(tmp_path):
    apk = _make_apk_file(tmp_path)
    mock = _make_mock_apk()
    mock.get_activities.side_effect = Exception("broken")
    with patch("scanner.analyzer.APK", return_value=mock):
        a = AppDeepAnalyzer(apk)
        a._count_components()
        assert a.findings == []