"""Test core/archive_utils.py — 7z + Python zip fallback."""
import io
import os
import subprocess
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from core.archive_utils import (
    _DISK_LOW_PCT,
    _DISK_MEDIUM_PCT,
    archive_via_7z,
    archive_via_python,
    choose_7z_args,
    extract_via_7z,
    extract_via_python,
    find_7zip,
    run_7z_with_progress,
)


# ============================================================
# find_7zip
# ============================================================
class TestFind7zip:
    def test_returns_str_or_none(self):
        result = find_7zip()
        assert result is None or isinstance(result, str)

    def test_finds_bundled(self, tmp_path):
        bundled = tmp_path / "tools" / "bin" / "7z.exe"
        bundled.parent.mkdir(parents=True)
        bundled.write_bytes(b"fake")

        with patch("core.archive_utils._TOOLS_DIR",
                   str(tmp_path / "tools")):
            result = find_7zip()
        assert result is not None
        assert "7z.exe" in result

    def test_returns_none_when_no_7z(self, tmp_path):
        with patch("core.archive_utils._TOOLS_DIR", str(tmp_path)), \
             patch("core.archive_utils.shutil.which", return_value=None), \
             patch("os.path.exists", return_value=False):
            result = find_7zip()
        assert result is None


# ============================================================
# choose_7z_args
# ============================================================
class TestChoose7zArgs:
    def test_high_disk_returns_copy(self):
        usage = MagicMock()
        usage.free = 60 * 1024 * 1024 * 1024
        usage.total = 100 * 1024 * 1024 * 1024

        with patch("core.archive_utils.shutil.disk_usage",
                   return_value=usage):
            args, mode = choose_7z_args()
        assert mode == "copy"
        assert "-mx=0" in args

    def test_medium_disk_returns_mx1(self):
        usage = MagicMock()
        usage.free = 30 * 1024 * 1024 * 1024
        usage.total = 100 * 1024 * 1024 * 1024

        with patch("core.archive_utils.shutil.disk_usage",
                   return_value=usage):
            args, mode = choose_7z_args()
        assert mode == "mx1"
        assert "-mx=1" in args

    def test_low_disk_returns_mx3(self):
        usage = MagicMock()
        usage.free = 10 * 1024 * 1024 * 1024
        usage.total = 100 * 1024 * 1024 * 1024

        with patch("core.archive_utils.shutil.disk_usage",
                   return_value=usage):
            args, mode = choose_7z_args()
        assert mode == "mx3"
        assert "-mx=3" in args

    def test_disk_usage_error_falls_back(self):
        with patch("core.archive_utils.shutil.disk_usage",
                   side_effect=OSError("no disk info")):
            args, mode = choose_7z_args()
        assert mode in ("copy", "mx1", "mx3")

    def test_args_include_format_and_threads(self):
        usage = MagicMock()
        usage.free = 30 * 1024 * 1024 * 1024
        usage.total = 100 * 1024 * 1024 * 1024
        with patch("core.archive_utils.shutil.disk_usage",
                   return_value=usage):
            args, _ = choose_7z_args()
        assert "-t7z" in args
        assert "-mmt" in args
        assert "-y" in args


# ============================================================
# run_7z_with_progress
# ============================================================
def _make_fake_7z_proc(stdout_chunks: list[bytes], rc: int = 0):
    """
    Tạo fake Popen với stdout là file-like object (BytesIO).
    7z code dùng `proc.stdout.read(256)` → cần file-like, không phải iter.
    """
    proc = MagicMock()
    proc.pid = 12345
    # BytesIO cung cấp read() đúng như subprocess.PIPE
    proc.stdout = io.BytesIO(b"".join(stdout_chunks))
    proc.wait.return_value = rc
    proc.kill = MagicMock()
    return proc


class TestRun7zWithProgress:
    def test_popen_oserror_returns_minus1(self):
        logs = []
        with patch(
            "core.archive_utils.subprocess.Popen",
            side_effect=OSError("no 7z"),
        ):
            rc = run_7z_with_progress(
                ["7z", "a"], logs.append, "Label", timeout_sec=5,
            )
        assert rc == -1
        assert any("không chạy" in l for l in logs)

    def test_success_rc_0(self):
        logs = []
        # 7z output có \r hoặc \n phân cách; BytesIO cho phép read(256)
        proc = _make_fake_7z_proc(
            [b" 50%\r", b"100%\n", b""],
            rc=0,
        )

        with patch(
            "core.archive_utils.subprocess.Popen",
            return_value=proc,
        ):
            rc = run_7z_with_progress(
                ["7z", "a", "-bsp1"], logs.append, "Label",
                timeout_sec=5,
            )
        assert rc == 0

    def test_progress_percent_parsed(self):
        logs = []
        proc = _make_fake_7z_proc(
            [
                b"   0%\r",
                b"  50% data.bin\r",
                b" 100% data.bin\r",
                b"",
            ],
            rc=0,
        )

        with patch(
            "core.archive_utils.subprocess.Popen",
            return_value=proc,
        ):
            run_7z_with_progress(
                ["7z"], logs.append, "Label", timeout_sec=5,
            )

        # Phải có ít nhất 1 log chứa %
        assert any("%" in l for l in logs)


# ============================================================
# archive_via_7z
# ============================================================
class TestArchiveVia7z:
    def test_returns_false_when_no_7z(self, tmp_path):
        with patch("core.archive_utils.find_7zip", return_value=None):
            result = archive_via_7z(
                str(tmp_path),
                str(tmp_path / "out.7z"),
                lambda *_: None,
            )
        assert result is False

    def test_skips_when_disk_low(self, tmp_path):
        usage = MagicMock()
        usage.free = 10 * 1024 * 1024
        usage.total = 100 * 1024 * 1024 * 1024

        logs = []
        with patch("core.archive_utils.find_7zip",
                   return_value="C:/7z.exe"), \
             patch("core.archive_utils.shutil.disk_usage",
                   return_value=usage):
            result = archive_via_7z(
                str(tmp_path),
                str(tmp_path / "out.7z"),
                logs.append,
            )
        assert result is True
        assert any("Disk còn" in l for l in logs)

    def test_creates_archive(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("x")
        archive_path = tmp_path / "out.7z"

        usage = MagicMock()
        usage.free = 50 * 1024 * 1024 * 1024
        usage.total = 100 * 1024 * 1024 * 1024

        def _fake_run(cmd, log_callback, label, cwd=None,
                      timeout_sec=1800):
            # 7z a <args> <archive> . → simulate by writing tmp
            # cmd format: [7z, "a", "-t7z", ..., "<archive.tmp>", "."]
            for arg in cmd:
                if arg.endswith(".tmp"):
                    with open(arg, "wb") as f:
                        f.write(b"fake 7z content")
                    break
            return 0

        with patch("core.archive_utils.find_7zip",
                   return_value="C:/7z.exe"), \
             patch("core.archive_utils.shutil.disk_usage",
                   return_value=usage), \
             patch("core.archive_utils.run_7z_with_progress",
                   side_effect=_fake_run), \
             patch("core.archive_utils.choose_7z_args",
                   return_value=(["-t7z", "-mx=1", "-mmt", "-y"], "mx1")):
            logs = []
            result = archive_via_7z(
                str(src), str(archive_path), logs.append,
            )
        assert result is True
        assert archive_path.exists()
        assert any("Archive" in l for l in logs)


# ============================================================
# archive_via_python
# ============================================================
class TestArchiveViaPython:
    def test_creates_valid_zip(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("hello")
        (src / "sub").mkdir()
        (src / "sub" / "b.txt").write_text("world")

        archive_path = tmp_path / "out.zip"
        ok = archive_via_python(
            str(src), str(archive_path), lambda *_: None,
        )
        assert ok is True
        assert archive_path.exists()
        with zipfile.ZipFile(str(archive_path)) as z:
            names = z.namelist()
            assert "a.txt" in names
            # Windows path sep normalize
            assert any("b.txt" in n for n in names)

    def test_empty_src_returns_false(self, tmp_path):
        src = tmp_path / "empty"
        src.mkdir()
        ok = archive_via_python(
            str(src), str(tmp_path / "out.zip"), lambda *_: None,
        )
        assert ok is False

    def test_disk_low_returns_false(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("x")
        usage = MagicMock()
        usage.free = 10
        usage.total = 100_000_000_000

        with patch("core.archive_utils.shutil.disk_usage",
                   return_value=usage):
            ok = archive_via_python(
                str(src), str(tmp_path / "out.zip"), lambda *_: None,
            )
        assert ok is False


# ============================================================
# extract_via_python
# ============================================================
class TestExtractViaPython:
    def test_extracts_valid_zip(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "x.txt").write_text("data")
        (src / "y.txt").write_text("more")
        archive = tmp_path / "a.zip"
        archive_via_python(str(src), str(archive), lambda *_: None)

        dst = tmp_path / "extracted"
        ok = extract_via_python(str(archive), str(dst),
                                 lambda *_: None)
        assert ok is True
        assert (dst / "x.txt").read_text() == "data"
        assert (dst / "y.txt").read_text() == "more"

    def test_missing_archive_returns_false(self, tmp_path):
        ok = extract_via_python(
            str(tmp_path / "nope.zip"),
            str(tmp_path / "out"),
            lambda *_: None,
        )
        assert ok is False

    def test_corrupt_zip_returns_false(self, tmp_path):
        bad = tmp_path / "bad.zip"
        bad.write_bytes(b"not a zip")
        dst = tmp_path / "out"
        logs = []
        ok = extract_via_python(str(bad), str(dst), logs.append)
        assert ok is False
        assert any("fail" in l.lower() for l in logs)


# ============================================================
# extract_via_7z
# ============================================================
class TestExtractVia7z:
    def test_returns_false_when_no_7z(self, tmp_path):
        with patch("core.archive_utils.find_7zip", return_value=None):
            ok = extract_via_7z(
                str(tmp_path / "x.7z"),
                str(tmp_path / "out"),
                lambda *_: None,
            )
        assert ok is False

    def test_returns_false_when_archive_missing(self, tmp_path):
        with patch("core.archive_utils.find_7zip",
                   return_value="C:/7z.exe"):
            ok = extract_via_7z(
                str(tmp_path / "missing.7z"),
                str(tmp_path / "out"),
                lambda *_: None,
            )
        assert ok is False


# ============================================================
# Constants
# ============================================================
def test_disk_thresholds_ordered():
    assert _DISK_LOW_PCT < _DISK_MEDIUM_PCT
    assert 0 < _DISK_LOW_PCT < 100
    assert 0 < _DISK_MEDIUM_PCT < 100