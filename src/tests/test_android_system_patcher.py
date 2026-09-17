"""Test patcher/android_system_patcher.py."""
import subprocess
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from patcher.android_system_patcher import AndroidSystemPatcher


# ============================================================
# Construction
# ============================================================
def test_init_default():
    p = AndroidSystemPatcher()
    assert p.adb == "adb"
    assert callable(p.log)


def test_init_custom_adb():
    p = AndroidSystemPatcher(adb="/custom/adb")
    assert p.adb == "/custom/adb"


# ============================================================
# check_root
# ============================================================
def test_check_root_true():
    p = AndroidSystemPatcher()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="uid=0(root) gid=0(root)"
        )
        assert p.check_root() is True


def test_check_root_false():
    p = AndroidSystemPatcher()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1, stdout="uid=2000(shell)"
        )
        assert p.check_root() is False


def test_check_root_subprocess_error():
    p = AndroidSystemPatcher()
    with patch(
        "subprocess.run",
        side_effect=subprocess.SubprocessError("adb not found"),
    ):
        assert p.check_root() is False


# ============================================================
# create_magisk_module
# ============================================================
def test_create_magisk_module_basic(tmp_path):
    out_zip = str(tmp_path / "module.zip")
    p = AndroidSystemPatcher()
    result = p.create_magisk_module(out_zip)
    assert result == out_zip
    assert (tmp_path / "module.zip").exists()

    # Verify structure
    with zipfile.ZipFile(out_zip, "r") as z:
        names = z.namelist()
    assert "module.prop" in names
    assert "post-fs-data.sh" in names


def test_create_magisk_module_with_services_jar(tmp_path):
    jar = tmp_path / "services.jar"
    jar.write_bytes(b"fake-jar")
    out_zip = str(tmp_path / "module.zip")

    p = AndroidSystemPatcher()
    p.create_magisk_module(out_zip, str(jar))

    with zipfile.ZipFile(out_zip, "r") as z:
        names = z.namelist()
    assert "system/framework/services.jar" in names


def test_create_magisk_module_nonexistent_jar(tmp_path):
    """services_jar path không tồn tại → bỏ qua, không crash."""
    out_zip = str(tmp_path / "module.zip")
    p = AndroidSystemPatcher()
    result = p.create_magisk_module(out_zip, "/nonexistent.jar")
    assert result == out_zip


def test_create_magisk_module_prop_content(tmp_path):
    out_zip = str(tmp_path / "module.zip")
    p = AndroidSystemPatcher()
    p.create_magisk_module(out_zip)

    with zipfile.ZipFile(out_zip, "r") as z:
        prop = z.read("module.prop").decode()
    assert "id=lp_pc_signature_patch" in prop


# ============================================================
# push_and_flash
# ============================================================
def test_push_and_flash_success(tmp_path):
    module = tmp_path / "m.zip"
    module.write_bytes(b"fake")

    p = AndroidSystemPatcher()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert p.push_and_flash(str(module)) is True


def test_push_and_flash_failure(tmp_path):
    module = tmp_path / "m.zip"
    module.write_bytes(b"fake")

    p = AndroidSystemPatcher()
    with patch(
        "subprocess.run",
        side_effect=subprocess.SubprocessError("adb push failed"),
    ):
        assert p.push_and_flash(str(module)) is False


# ============================================================
# apply_patches
# ============================================================
def test_apply_patches_no_root():
    p = AndroidSystemPatcher()
    with patch.object(p, "check_root", return_value=False):
        assert p.apply_patches({}) is False


def test_apply_patches_pull_fail():
    p = AndroidSystemPatcher()
    with patch.object(p, "check_root", return_value=True), \
         patch(
             "subprocess.run",
             side_effect=subprocess.SubprocessError("pull failed"),
         ):
        assert p.apply_patches({}) is False


def test_apply_patches_no_smali_tools(tmp_path):
    """Không có baksmali/smali → tạo module rỗng."""
    p = AndroidSystemPatcher()
    p.tools_dir = str(tmp_path)  # Rỗng

    with patch.object(p, "check_root", return_value=True), \
         patch("subprocess.run") as mock_run, \
         patch.object(p, "push_and_flash", return_value=True):
        mock_run.return_value = MagicMock(returncode=0)
        result = p.apply_patches({})
        assert result is True


# ============================================================
# test_patch
# ============================================================
def test_test_patch_success():
    p = AndroidSystemPatcher()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="package:com.example\npackage:com.foo"
        )
        assert p.test_patch() is True


def test_test_patch_failure():
    p = AndroidSystemPatcher()
    with patch(
        "subprocess.run",
        side_effect=subprocess.SubprocessError("adb not found"),
    ):
        assert p.test_patch() is False