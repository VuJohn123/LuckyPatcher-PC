"""Test installed_apps — ADB wrapper."""
import subprocess
from unittest.mock import MagicMock, patch

from scanner.installed_apps import (
    _adb_available,
    _PKG_RE,
    get_installed_apps,
)


# ============================================================
# _adb_available
# ============================================================
def test_adb_available_true():
    with patch("scanner.installed_apps.shutil.which", return_value="/bin/adb"):
        assert _adb_available() is True


def test_adb_available_false():
    with patch("scanner.installed_apps.shutil.which", return_value=None):
        assert _adb_available() is False


# ============================================================
# _PKG_RE regex
# ============================================================
def test_pkg_regex_extracts():
    text = "package:com.example.app\npackage:com.other.app"
    matches = _PKG_RE.findall(text)
    assert matches == ["com.example.app", "com.other.app"]


# ============================================================
# get_installed_apps
# ============================================================
def test_get_installed_apps_no_adb():
    with patch(
        "scanner.installed_apps.shutil.which", return_value=None
    ):
        result = get_installed_apps()
        assert result == []


def test_get_installed_apps_success():
    mock_proc = MagicMock(
        returncode=0,
        stdout="package:com.example.app\npackage:com.foo.bar",
    )
    with patch(
        "scanner.installed_apps.shutil.which", return_value="/bin/adb"
    ), patch(
        "scanner.installed_apps.subprocess.run", return_value=mock_proc
    ):
        apps = get_installed_apps()
        assert len(apps) == 2
        packages = [a["package"] for a in apps]
        assert "com.example.app" in packages
        assert "com.foo.bar" in packages


def test_get_installed_apps_empty_output():
    mock_proc = MagicMock(returncode=0, stdout="")
    with patch(
        "scanner.installed_apps.shutil.which", return_value="/bin/adb"
    ), patch(
        "scanner.installed_apps.subprocess.run", return_value=mock_proc
    ):
        assert get_installed_apps() == []


def test_get_installed_apps_subprocess_error():
    with patch(
        "scanner.installed_apps.shutil.which", return_value="/bin/adb"
    ), patch(
        "scanner.installed_apps.subprocess.run",
        side_effect=subprocess.SubprocessError("adb crashed"),
    ):
        assert get_installed_apps() == []


def test_get_installed_apps_timeout():
    with patch(
        "scanner.installed_apps.shutil.which", return_value="/bin/adb"
    ), patch(
        "scanner.installed_apps.subprocess.run",
        side_effect=subprocess.TimeoutExpired("adb", 15),
    ):
        assert get_installed_apps() == []


def test_get_installed_apps_name_extraction():
    """Name = last part của package, capitalize."""
    mock_proc = MagicMock(
        returncode=0, stdout="package:com.example.myapp"
    )
    with patch(
        "scanner.installed_apps.shutil.which", return_value="/bin/adb"
    ), patch(
        "scanner.installed_apps.subprocess.run", return_value=mock_proc
    ):
        apps = get_installed_apps()
        assert apps[0]["name"] == "Myapp"