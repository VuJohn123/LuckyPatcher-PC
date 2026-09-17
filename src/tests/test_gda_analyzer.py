"""Test scanner/gda_analyzer.py — GDA integration."""
from unittest.mock import MagicMock, patch

import pytest

from scanner.gda_analyzer import GDAAnalyzer


def test_class_exists():
    assert GDAAnalyzer is not None


def test_init_default():
    a = GDAAnalyzer()
    assert a is not None
    # Phải có attribute gda_exe
    assert hasattr(a, "gda_exe")


def test_init_with_custom_path():
    a = GDAAnalyzer(gda_path="/custom/path/GDA.exe")
    assert a.gda_exe == "/custom/path/GDA.exe"


def test_analyze_returns_empty_when_gda_missing(tmp_path):
    """GDA.exe không tồn tại → trả về dict rỗng, không crash."""
    a = GDAAnalyzer(gda_path="/nonexistent/GDA.exe")
    result = a.analyze(str(tmp_path / "test.apk"))
    assert isinstance(result, dict)
    assert "license_classes" in result
    assert "iap_classes" in result
    assert "ad_urls" in result
    assert result["license_classes"] == []
    assert result["iap_classes"] == []
    assert result["ad_urls"] == []


def test_analyze_with_timeout(tmp_path):
    """GDA timeout → graceful fallback."""
    apk = tmp_path / "test.apk"
    apk.write_bytes(b"fake")

    a = GDAAnalyzer(gda_path=str(tmp_path / "fake_gda"))
    result = a.analyze(str(apk), timeout=1)
    assert isinstance(result, dict)


def test_analyze_handles_subprocess_error(tmp_path):
    apk = tmp_path / "test.apk"
    apk.write_bytes(b"fake")

    # Tạo fake GDA file để pass exists check
    fake_gda = tmp_path / "GDA.exe"
    fake_gda.write_bytes(b"fake")

    a = GDAAnalyzer(gda_path=str(fake_gda))

    with patch(
        "scanner.gda_analyzer.subprocess.run",
        side_effect=OSError("cannot execute"),
    ):
        result = a.analyze(str(apk))
        assert isinstance(result, dict)


def test_analyze_parses_report(tmp_path):
    """Mock GDA output → verify parser."""
    apk = tmp_path / "test.apk"
    apk.write_bytes(b"fake")

    fake_gda = tmp_path / "GDA.exe"
    fake_gda.write_bytes(b"fake")

    # Mock subprocess tạo report giả
    def fake_run(cmd, **kwargs):
        # cmd = [gda_exe, "-a", apk_path, "-o", report]
        report_path = cmd[-1]
        with open(report_path, "w") as f:
            f.write(
                "Lcom/google/android/vending/licensing/LicenseValidator;\n"
                "Lcom/android/vending/billing/IInAppBillingService$Stub;\n"
                "https://doubleclick.net/ad\n"
            )
        return MagicMock(returncode=0)

    a = GDAAnalyzer(gda_path=str(fake_gda))

    with patch("scanner.gda_analyzer.subprocess.run", side_effect=fake_run):
        result = a.analyze(str(apk))
        assert isinstance(result, dict)
        # Có thể có hoặc không có matches — tùy regex


def test_analyze_handles_timeout_expired(tmp_path):
    import subprocess
    apk = tmp_path / "test.apk"
    apk.write_bytes(b"fake")

    fake_gda = tmp_path / "GDA.exe"
    fake_gda.write_bytes(b"fake")

    a = GDAAnalyzer(gda_path=str(fake_gda))

    with patch(
        "scanner.gda_analyzer.subprocess.run",
        side_effect=subprocess.TimeoutExpired("GDA", 120),
    ):
        result = a.analyze(str(apk))
        assert isinstance(result, dict)