"""Test device bridge với subprocess mocked."""
from unittest.mock import patch, MagicMock

from core.device_bridge import (
    check_root,
    install_apk,
    list_devices,
    setup_reverse_port,
)


@patch("core.device_bridge.shutil.which", return_value=None)
def test_adb_not_available(_):
    assert list_devices() == []
    assert check_root() is False


@patch("core.device_bridge.shutil.which", return_value="/usr/bin/adb")
@patch("core.device_bridge.subprocess.run")
def test_install_apk_success(mock_run, _):
    mock_run.return_value = MagicMock(returncode=0, stdout="Success")
    assert install_apk("/tmp/app.apk") is True


@patch("core.device_bridge.shutil.which", return_value="/usr/bin/adb")
@patch("core.device_bridge.subprocess.run")
def test_install_apk_failure(mock_run, _):
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="err")
    try:
        install_apk("/tmp/app.apk")
        assert False, "Expected RuntimeError"
    except RuntimeError:
        pass


@patch("core.device_bridge.shutil.which", return_value="/usr/bin/adb")
@patch("core.device_bridge.subprocess.run")
def test_check_root_true(mock_run, _):
    mock_run.return_value = MagicMock(returncode=0, stdout="uid=0(root)")
    assert check_root() is True


@patch("core.device_bridge.shutil.which", return_value="/usr/bin/adb")
@patch("core.device_bridge.subprocess.run")
def test_setup_reverse_port_success(mock_run, _):
    mock_run.return_value = MagicMock(returncode=0)
    assert setup_reverse_port(8888, 8888) is True


@patch("core.device_bridge.shutil.which", return_value="/usr/bin/adb")
@patch("core.device_bridge.subprocess.run")
def test_list_devices(mock_run, _):
    mock_run.return_value = MagicMock(
        stdout="List of devices attached\nemulator-5554\tdevice\n"
    )
    assert list_devices() == ["emulator-5554"]