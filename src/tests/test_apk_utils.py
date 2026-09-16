"""Test APK utils — hash, cache dir, decompile, recompile, sign, merge."""
import os
import subprocess
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from core.apk_utils import (
    get_apk_hash,
    get_cache_dir,
    get_tool_path,
    merge_split_apks,
    recompile_apk,
    sign_apk,
)


# ============================================================
# get_apk_hash
# ============================================================
def test_apk_hash_deterministic(tmp_path):
    f = tmp_path / "test.apk"
    f.write_bytes(b"content")
    h1 = get_apk_hash(str(f))
    h2 = get_apk_hash(str(f))
    assert h1 == h2


def test_apk_hash_changes_with_content(tmp_path):
    f1 = tmp_path / "a.apk"
    f2 = tmp_path / "b.apk"
    f1.write_bytes(b"content1")
    f2.write_bytes(b"content2")
    assert get_apk_hash(str(f1)) != get_apk_hash(str(f2))


# ============================================================
# get_cache_dir
# ============================================================
def test_get_cache_dir_creates(tmp_path):
    apk = tmp_path / "test.apk"
    apk.write_bytes(b"fake")
    cache = get_cache_dir(str(apk), base_cache_dir=str(tmp_path / "cache"))
    assert os.path.exists(cache)


def test_get_cache_dir_same_hash_same_dir(tmp_path):
    apk = tmp_path / "test.apk"
    apk.write_bytes(b"same-content")
    base = str(tmp_path / "cache")

    cache1 = get_cache_dir(str(apk), base)
    cache2 = get_cache_dir(str(apk), base)
    assert cache1 == cache2


# ============================================================
# get_tool_path
# ============================================================
def test_get_tool_path_legacy(tmp_path, monkeypatch):
    """Fallback về tools/<name> nếu tools/bin/<name> không có."""
    monkeypatch.setattr("core.apk_utils.TOOLS_DIR", str(tmp_path))
    # bin/ không tồn tại → trả về legacy path
    path = get_tool_path("apktool.jar")
    assert "apktool.jar" in path
    assert "bin" not in path


def test_get_tool_path_new_layout(tmp_path, monkeypatch):
    """tools/bin/<name> tồn tại → ưu tiên."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "apktool.jar").write_bytes(b"fake")
    monkeypatch.setattr("core.apk_utils.TOOLS_DIR", str(tmp_path))

    path = get_tool_path("apktool.jar")
    assert "bin" in path


# ============================================================
# merge_split_apks
# ============================================================
def test_merge_split_apks_simple(tmp_path):
    src = tmp_path / "splits"
    src.mkdir()

    with zipfile.ZipFile(src / "base.apk", "w") as z:
        z.writestr("AndroidManifest.xml", b"base")
        z.writestr("common.txt", b"common")

    with zipfile.ZipFile(src / "split_config.apk", "w") as z:
        z.writestr("config.txt", b"config")
        z.writestr("common.txt", b"should-not-overwrite")

    out = tmp_path / "merged.apk"
    merge_split_apks(str(src), str(out), lambda *_: None)

    with zipfile.ZipFile(out, "r") as z:
        names = z.namelist()
        assert "AndroidManifest.xml" in names
        assert "config.txt" in names
        # Base wins
        assert z.read("common.txt") == b"common"


def test_merge_split_apks_no_apk(tmp_path):
    src = tmp_path / "splits"
    src.mkdir()
    with pytest.raises(ValueError, match="Không có APK"):
        merge_split_apks(
            str(src), str(tmp_path / "out.apk"), lambda *_: None
        )


def test_merge_split_apks_skips_bad_split(tmp_path):
    src = tmp_path / "splits"
    src.mkdir()

    with zipfile.ZipFile(src / "base.apk", "w") as z:
        z.writestr("main.xml", b"base")

    (src / "bad_split.apk").write_bytes(b"not a valid zip")

    logs = []
    out = tmp_path / "merged.apk"
    merge_split_apks(str(src), str(out), logs.append)

    with zipfile.ZipFile(out, "r") as z:
        assert "main.xml" in z.namelist()
    assert any("Bỏ qua split lỗi" in l for l in logs)


# ============================================================
# recompile_apk
# ============================================================
def test_recompile_apk_success_first_attempt(tmp_path):
    mock_proc = MagicMock(returncode=0, stdout="ok", stderr="")
    with patch(
        "core.apk_utils.subprocess.run", return_value=mock_proc
    ):
        result = recompile_apk(
            str(tmp_path), str(tmp_path / "out.apk"),
            log_callback=lambda *_: None,
        )
        assert result.endswith("out.apk")


def test_recompile_apk_retry_with_aapt2(tmp_path):
    """First attempt fail → retry với --use-aapt2."""
    fail = MagicMock(returncode=1, stdout="", stderr="fail")
    success = MagicMock(returncode=0, stdout="ok", stderr="")

    with patch(
        "core.apk_utils.subprocess.run",
        side_effect=[fail, success],
    ) as mock_run:
        recompile_apk(
            str(tmp_path), str(tmp_path / "out.apk"),
            log_callback=lambda *_: None,
        )
        # Verify call 2 có --use-aapt2
        second_call_args = mock_run.call_args_list[1][0][0]
        assert "--use-aapt2" in second_call_args


def test_recompile_apk_all_fail(tmp_path):
    fail = MagicMock(returncode=1, stdout="", stderr="fail")
    with patch(
        "core.apk_utils.subprocess.run", return_value=fail
    ):
        with pytest.raises(RuntimeError, match="Recompile failed"):
            recompile_apk(
                str(tmp_path), str(tmp_path / "out.apk"),
                log_callback=lambda *_: None,
                max_retries=1,
            )


def test_recompile_apk_forced_package_id(tmp_path):
    mock_proc = MagicMock(returncode=0, stdout="", stderr="")
    with patch(
        "core.apk_utils.subprocess.run", return_value=mock_proc
    ) as mock_run:
        recompile_apk(
            str(tmp_path), str(tmp_path / "out.apk"),
            forced_package_id=42,
            log_callback=lambda *_: None,
        )
        cmd = mock_run.call_args[0][0]
        assert "--forced-package-id" in cmd
        assert "42" in cmd


# ============================================================
# sign_apk
# ============================================================
def test_sign_apk_testkey_success(tmp_path):
    mock_proc = MagicMock(returncode=0, stdout="ok", stderr="")
    with patch(
        "core.apk_utils.subprocess.run", return_value=mock_proc
    ):
        result = sign_apk(
            str(tmp_path / "app.apk"),
            key_type="testkey",
            log_callback=lambda *_: None,
        )
        assert "signed" in result or "apk" in result


def test_sign_apk_testkey_failure(tmp_path):
    mock_proc = MagicMock(returncode=1, stdout="", stderr="sign failed")
    with patch(
        "core.apk_utils.subprocess.run", return_value=mock_proc
    ):
        with pytest.raises(RuntimeError, match="Signing failed"):
            sign_apk(
                str(tmp_path / "app.apk"),
                key_type="testkey",
                log_callback=lambda *_: None,
            )


def test_sign_apk_platform_delegates(tmp_path):
    with patch(
        "core.sign_with_key.APKSigner.sign_apk",
        return_value="/output/signed.apk",
    ):
        result = sign_apk(
            str(tmp_path / "app.apk"),
            key_type="platform",
            log_callback=lambda *_: None,
        )
        assert result == "/output/signed.apk"