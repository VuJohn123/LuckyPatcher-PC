"""Test core/device_bridge.py — ADB bridge."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from core.device_bridge import (
    _adb_available,
    _do_install,
    _extract_package_from_apk,
    check_root,
    install_apk,
    list_devices,
    setup_reverse_port,
    uninstall_app,
)


# ============================================================
# _adb_available
# ============================================================
class TestAdbAvailable:
    def test_true_when_in_path(self):
        with patch("core.device_bridge.shutil.which",
                   return_value="/usr/bin/adb"):
            assert _adb_available() is True

    def test_false_when_not_in_path(self):
        with patch("core.device_bridge.shutil.which",
                   return_value=None):
            assert _adb_available() is False


# ============================================================
# _extract_package_from_apk
# ============================================================
class TestExtractPackage:
    def test_via_androguard(self):
        with patch("androguard.core.apk.APK") as MockAPK:
            MockAPK.return_value.get_package.return_value = (
                "com.example.app"
            )
            pkg = _extract_package_from_apk("/fake.apk")
        assert pkg == "com.example.app"

    def test_aapt_fallback(self):
        with patch("androguard.core.apk.APK",
                   side_effect=Exception("no androguard")), \
             patch("core.device_bridge.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="package: name='com.example.fb' versionCode='1'",
                returncode=0, stderr="",
            )
            pkg = _extract_package_from_apk("/fake.apk")
        assert pkg == "com.example.fb"

    def test_aapt_no_match_returns_none(self):
        with patch("androguard.core.apk.APK",
                   side_effect=Exception("no androguard")), \
             patch("core.device_bridge.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="garbage", returncode=0, stderr="",
            )
            pkg = _extract_package_from_apk("/fake.apk")
        assert pkg is None

    def test_all_fail_returns_none(self):
        with patch("androguard.core.apk.APK",
                   side_effect=Exception("no androguard")), \
             patch("core.device_bridge.subprocess.run",
                   side_effect=OSError("no aapt")):
            pkg = _extract_package_from_apk("/fake.apk")
        assert pkg is None


# ============================================================
# _do_install
# ============================================================
class TestDoInstall:
    def test_success(self):
        with patch("core.device_bridge.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Success\n", stderr=""
            )
            _do_install("/tmp/app.apk", 60)  # No raise

    def test_failure_rc_nonzero(self):
        with patch("core.device_bridge.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="INSTALL_FAILED",
            )
            with pytest.raises(RuntimeError, match="ADB install failed"):
                _do_install("/tmp/app.apk", 60)

    def test_no_success_in_stdout(self):
        with patch("core.device_bridge.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="weird output", stderr=""
            )
            with pytest.raises(RuntimeError):
                _do_install("/tmp/app.apk", 60)

    def test_timeout(self):
        with patch("core.device_bridge.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("adb", 60)):
            with pytest.raises(RuntimeError, match="timeout"):
                _do_install("/tmp/app.apk", 60)


# ============================================================
# install_apk
# ============================================================
class TestInstallApk:
    def test_no_adb_raises(self, monkeypatch):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: False)
        with pytest.raises(RuntimeError, match="adb không có"):
            install_apk("/tmp/x.apk")

    def test_success(self, monkeypatch):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: True)
        with patch("core.device_bridge._do_install") as mock_do:
            result = install_apk("/tmp/x.apk")
        assert result is True
        mock_do.assert_called_once()

    def test_failure_propagates(self, monkeypatch):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: True)
        with patch("core.device_bridge._do_install",
                   side_effect=RuntimeError("some other error")):
            with pytest.raises(RuntimeError, match="some other"):
                install_apk("/tmp/x.apk")

    def test_auto_uninstall_on_signature_mismatch(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: True)
        monkeypatch.setattr("core.device_bridge._extract_package_from_apk",
                           lambda p: "com.example.app")

        apk = tmp_path / "app.apk"
        apk.write_bytes(b"fake")

        install_calls = {"n": 0}

        def _run(cmd, **kwargs):
            if "install" in cmd:
                install_calls["n"] += 1
                if install_calls["n"] == 1:
                    return MagicMock(
                        returncode=1, stdout="",
                        stderr="INSTALL_FAILED_UPDATE_INCOMPATIBLE",
                    )
                return MagicMock(
                    returncode=0, stdout="Success\n", stderr=""
                )
            if "uninstall" in cmd:
                return MagicMock(returncode=0, stdout="Success\n",
                                 stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("core.device_bridge.subprocess.run",
                   side_effect=_run):
            result = install_apk(str(apk))

        assert result is True
        assert install_calls["n"] == 2  # install fail → retry OK

    def test_mismatch_but_no_pkg_extracted_raises(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: True)
        monkeypatch.setattr("core.device_bridge._extract_package_from_apk",
                           lambda p: None)

        apk = tmp_path / "app.apk"
        apk.write_bytes(b"fake")

        with patch("core.device_bridge.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="",
                stderr="INSTALL_FAILED_UPDATE_INCOMPATIBLE",
            )
            with pytest.raises(RuntimeError, match="Không extract"):
                install_apk(str(apk))

    def test_no_auto_uninstall_when_disabled(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: True)

        apk = tmp_path / "app.apk"
        apk.write_bytes(b"fake")

        with patch("core.device_bridge.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="",
                stderr="INSTALL_FAILED_UPDATE_INCOMPATIBLE",
            )
            with pytest.raises(RuntimeError):
                install_apk(str(apk),
                            auto_uninstall_on_mismatch=False)


# ============================================================
# uninstall_app
# ============================================================
class TestUninstallApp:
    def test_no_adb_returns_false(self, monkeypatch):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: False)
        assert uninstall_app("com.example.app") is False

    def test_success(self, monkeypatch):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: True)
        with patch("core.device_bridge.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert uninstall_app("com.example.app") is True

    def test_subprocess_error_returns_false(self, monkeypatch):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: True)
        with patch("core.device_bridge.subprocess.run",
                   side_effect=subprocess.SubprocessError("adb crash")):
            assert uninstall_app("com.example.app") is False


# ============================================================
# setup_reverse_port
# ============================================================
class TestSetupReversePort:
    def test_no_adb_returns_false(self, monkeypatch):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: False)
        assert setup_reverse_port(8888, 8888) is False

    def test_success(self, monkeypatch):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: True)
        with patch("core.device_bridge.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert setup_reverse_port(8888, 8888) is True

    def test_rc_nonzero_returns_false(self, monkeypatch):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: True)
        with patch("core.device_bridge.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert setup_reverse_port(8888, 8888) is False

    def test_subprocess_error_returns_false(self, monkeypatch):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: True)
        with patch("core.device_bridge.subprocess.run",
                   side_effect=subprocess.SubprocessError("adb crash")):
            assert setup_reverse_port(8888, 8888) is False


# ============================================================
# check_root
# ============================================================
class TestCheckRoot:
    def test_no_adb_returns_false(self, monkeypatch):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: False)
        assert check_root() is False

    def test_root_uid0(self, monkeypatch):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: True)
        with patch("core.device_bridge.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="uid=0(root) gid=0(root) groups=0(root)\n",
                returncode=0,
            )
            assert check_root() is True

    def test_non_root(self, monkeypatch):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: True)
        with patch("core.device_bridge.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="uid=2000(shell)\n", returncode=0,
            )
            assert check_root() is False

    def test_subprocess_error_returns_false(self, monkeypatch):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: True)
        with patch("core.device_bridge.subprocess.run",
                   side_effect=subprocess.SubprocessError("crash")):
            assert check_root() is False


# ============================================================
# list_devices
# ============================================================
class TestListDevices:
    def test_no_adb_returns_empty(self, monkeypatch):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: False)
        assert list_devices() == []

    def test_parses_devices(self, monkeypatch):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: True)
        stdout = (
            "List of devices attached\n"
            "1234abcd\tdevice\n"
            "5678efgh\tdevice\n"
        )
        with patch("core.device_bridge.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
            devices = list_devices()
        assert devices == ["1234abcd", "5678efgh"]

    def test_skips_offline(self, monkeypatch):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: True)
        stdout = (
            "List of devices attached\n"
            "1234abcd\tdevice\n"
            "5678efgh\toffline\n"
        )
        with patch("core.device_bridge.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=stdout, returncode=0)
            devices = list_devices()
        assert devices == ["1234abcd"]

    def test_empty_list(self, monkeypatch):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: True)
        with patch("core.device_bridge.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="List of devices attached\n", returncode=0,
            )
            assert list_devices() == []

    def test_subprocess_error_returns_empty(self, monkeypatch):
        monkeypatch.setattr("core.device_bridge._adb_available",
                           lambda: True)
        with patch("core.device_bridge.subprocess.run",
                   side_effect=subprocess.SubprocessError("crash")):
            assert list_devices() == []