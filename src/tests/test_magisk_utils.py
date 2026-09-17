"""Test patcher/magisk_utils.py."""
import os
import zipfile

import pytest

from patcher.magisk_utils import create_magisk_module


def test_create_module_basic(tmp_path):
    out = str(tmp_path / "module.zip")
    result = create_magisk_module("/nonexistent.jar", out)
    assert result == out
    assert os.path.exists(out)


def test_create_module_structure(tmp_path):
    out = str(tmp_path / "module.zip")
    create_magisk_module("/nonexistent.jar", out)

    with zipfile.ZipFile(out, "r") as z:
        names = z.namelist()
    assert "module.prop" in names
    assert "post-fs-data.sh" in names


def test_create_module_with_jar(tmp_path):
    jar = tmp_path / "services.jar"
    jar.write_bytes(b"fake-jar-content")
    out = str(tmp_path / "module.zip")

    create_magisk_module(str(jar), out)

    with zipfile.ZipFile(out, "r") as z:
        names = z.namelist()
    assert "system/framework/services.jar" in names


def test_create_module_prop_content(tmp_path):
    out = str(tmp_path / "module.zip")
    create_magisk_module("/nonexistent.jar", out)

    with zipfile.ZipFile(out, "r") as z:
        prop = z.read("module.prop").decode()
    assert "id=lp_pc_signature_patch" in prop
    assert "name=LP-PC Signature Patch" in prop


def test_create_module_script_content(tmp_path):
    out = str(tmp_path / "module.zip")
    create_magisk_module("/nonexistent.jar", out)

    with zipfile.ZipFile(out, "r") as z:
        script = z.read("post-fs-data.sh").decode()
    assert "#!/system/bin/sh" in script
    assert "mount -o bind" in script


def test_create_module_output_exists(tmp_path):
    out = str(tmp_path / "module.zip")
    result = create_magisk_module("/nonexistent.jar", out)
    assert result is not None
    assert os.path.getsize(result) > 0