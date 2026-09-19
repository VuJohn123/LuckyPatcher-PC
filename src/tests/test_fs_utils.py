"""Test core/fs_utils.py — junction, robocopy, safe_copytree."""
import os
from unittest.mock import MagicMock, patch

import pytest

from core.fs_utils import (
    _COPY_FAIL_TOLERANCE,
    has_robocopy,
    is_link_to,
    remove_dst,
    robocopy_copy,
    safe_copytree,
    try_link,
)


# ============================================================
# remove_dst
# ============================================================
class TestRemoveDst:
    def test_nonexistent_noop(self, tmp_path):
        remove_dst(str(tmp_path / "nope"))
        # No exception, no side effect

    def test_removes_file(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        remove_dst(str(f))
        assert not f.exists()

    def test_removes_empty_dir(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        remove_dst(str(d))
        assert not d.exists()

    def test_removes_nonempty_dir(self, tmp_path):
        d = tmp_path / "full"
        d.mkdir()
        (d / "a.txt").write_text("a")
        (d / "b.txt").write_text("b")
        remove_dst(str(d))
        assert not d.exists()

    def test_removes_symlink(self, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        (target / "x.txt").write_text("x")
        link = tmp_path / "link"
        try:
            os.symlink(str(target), str(link))
        except (OSError, NotImplementedError):
            pytest.skip("Symlink not supported")
        remove_dst(str(link))
        assert not link.exists()
        assert target.exists()  # Target unchanged


# ============================================================
# is_link_to
# ============================================================
class TestIsLinkTo:
    def test_same_path(self, tmp_path):
        d = tmp_path / "dir"
        d.mkdir()
        assert is_link_to(str(d), str(d)) is True

    def test_different_paths(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        assert is_link_to(str(a), str(b)) is False

    def test_nonexistent_returns_false(self, tmp_path):
        assert is_link_to(
            str(tmp_path / "nonexistent"),
            str(tmp_path / "also"),
        ) is False


# ============================================================
# try_link
# ============================================================
class TestTryLink:
    def test_link_or_copy_fallback(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "f.txt").write_text("data")
        dst = tmp_path / "dst"

        # On any platform, either link or fails gracefully
        result = try_link(str(src), str(dst))
        assert isinstance(result, bool)

    def test_returns_false_when_subprocess_fails(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        dst = tmp_path / "dst"

        if os.name != "nt":
            pytest.skip("Windows-specific path")

        with patch(
            "core.fs_utils.subprocess.run",
            side_effect=OSError("mklink unavailable"),
        ):
            assert try_link(str(src), str(dst)) is False

    def test_returns_false_when_mklink_rc_nonzero(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        dst = tmp_path / "dst"

        if os.name != "nt":
            pytest.skip("Windows-specific path")

        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch(
            "core.fs_utils.subprocess.run",
            return_value=mock_result,
        ):
            assert try_link(str(src), str(dst)) is False


# ============================================================
# has_robocopy
# ============================================================
class TestHasRobocopy:
    def test_returns_bool(self):
        result = has_robocopy()
        assert isinstance(result, bool)

    def test_false_on_non_windows(self):
        if os.name == "nt":
            pytest.skip("Not applicable on Windows")
        assert has_robocopy() is False


# ============================================================
# robocopy_copy
# ============================================================
class TestRobocopyCopy:
    def test_returns_false_on_non_windows(self, tmp_path):
        if os.name == "nt":
            pytest.skip("Non-Windows check")
        assert robocopy_copy(
            str(tmp_path), str(tmp_path / "dst"),
            log_callback=lambda *_: None,
        ) is False

    def test_returns_false_when_not_available(self, tmp_path):
        with patch("core.fs_utils.has_robocopy", return_value=False):
            assert robocopy_copy(
                str(tmp_path), str(tmp_path / "dst"),
                log_callback=lambda *_: None,
            ) is False

    def test_success_rc_0(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("x")
        dst = tmp_path / "dst"
        dst.mkdir()
        (dst / "a.txt").write_text("x")

        mock_result = MagicMock()
        mock_result.returncode = 1  # robocopy rc=1 = success (1 file copied)
        mock_result.stdout = ""

        with patch("core.fs_utils.has_robocopy", return_value=True), \
             patch("core.fs_utils.subprocess.run",
                   return_value=mock_result):
            result = robocopy_copy(
                str(src), str(dst),
                log_callback=lambda *_: None,
            )
        assert result is True

    def test_error_rc_8(self, tmp_path):
        logs = []
        src = tmp_path / "src"
        src.mkdir()
        dst = tmp_path / "dst"
        dst.mkdir()

        mock_result = MagicMock()
        mock_result.returncode = 8
        mock_result.stdout = "ERROR"

        with patch("core.fs_utils.has_robocopy", return_value=True), \
             patch("core.fs_utils.subprocess.run",
                   return_value=mock_result):
            result = robocopy_copy(
                str(src), str(dst),
                log_callback=logs.append,
            )
        assert result is True  # handled (fail logged)
        assert any("rc=8" in str(l) for l in logs)

    def test_timeout(self, tmp_path):
        import subprocess
        logs = []
        src = tmp_path / "src"
        src.mkdir()
        dst = tmp_path / "dst"

        with patch("core.fs_utils.has_robocopy", return_value=True), \
             patch("core.fs_utils.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("robocopy", 1800)):
            result = robocopy_copy(
                str(src), str(dst),
                log_callback=logs.append,
            )
        assert result is True
        assert any("timeout" in l.lower() for l in logs)


# ============================================================
# safe_copytree
# ============================================================
class TestSafeCopytree:
    def _make_src(self, tmp_path, n_files=3):
        src = tmp_path / "src"
        src.mkdir()
        for i in range(n_files):
            (src / f"f{i}.txt").write_text(f"content{i}")
        return src

    def test_mode_write_copies(self, tmp_path):
        src = self._make_src(tmp_path, 3)
        dst = tmp_path / "dst"
        ok = safe_copytree(
            str(src), str(dst),
            log_callback=lambda *_: None,
            mode="write",
        )
        assert ok is True
        assert (dst / "f0.txt").read_text() == "content0"
        assert (dst / "f2.txt").read_text() == "content2"

    def test_mode_copy_no_junction(self, tmp_path):
        """mode='copy' → không tạo junction (dù có thể)."""
        src = self._make_src(tmp_path, 2)
        dst = tmp_path / "dst"

        with patch("core.fs_utils.try_link") as mock_link:
            mock_link.return_value = True
            ok = safe_copytree(
                str(src), str(dst),
                log_callback=lambda *_: None,
                mode="copy",
            )
        assert ok is True
        # try_link KHÔNG được gọi cho mode="copy"
        mock_link.assert_not_called()
        assert (dst / "f0.txt").exists()

    def test_mode_read_already_linked(self, tmp_path):
        src = self._make_src(tmp_path, 1)
        dst = src  # same path

        logs = []
        ok = safe_copytree(
            str(src), str(dst),
            log_callback=logs.append,
            mode="read",
        )
        assert ok is True
        assert any("Already linked" in l for l in logs)

    def test_mode_read_uses_junction_when_possible(self, tmp_path):
        src = self._make_src(tmp_path, 1)
        dst = tmp_path / "dst"

        with patch("core.fs_utils.is_link_to", return_value=False), \
             patch("core.fs_utils.try_link", return_value=True):
            logs = []
            ok = safe_copytree(
                str(src), str(dst),
                log_callback=logs.append,
                mode="read",
            )
        assert ok is True
        assert any("Linked" in l for l in logs)

    def test_mode_read_falls_back_to_copy(self, tmp_path):
        src = self._make_src(tmp_path, 2)
        dst = tmp_path / "dst"

        with patch("core.fs_utils.try_link", return_value=False):
            ok = safe_copytree(
                str(src), str(dst),
                log_callback=lambda *_: None,
                mode="read",
            )
        assert ok is True
        assert (dst / "f0.txt").exists()

    def test_disk_check_skip(self, tmp_path):
        """Disk < min_pct → skip, return False."""
        src = self._make_src(tmp_path, 1)
        dst = tmp_path / "dst"

        usage_mock = MagicMock()
        usage_mock.free = 100
        usage_mock.total = 1_000_000_000  # 0.00001% free

        with patch("core.fs_utils.shutil.disk_usage",
                   return_value=usage_mock):
            logs = []
            ok = safe_copytree(
                str(src), str(dst),
                log_callback=logs.append,
                mode="write",
            )
        assert ok is False
        assert any("Disk còn" in l for l in logs)

    def test_fail_tolerance_raise(self, tmp_path):
        """Nếu > fail_tolerance file lỗi → RuntimeError."""
        src = self._make_src(tmp_path, 4)
        dst = tmp_path / "dst"

        # Mock copy2 to fail for most files
        def _fail_copy(s, t, *a, **kw):
            raise OSError("copy fail")

        with patch("core.fs_utils.shutil.copy2", side_effect=_fail_copy):
            with pytest.raises(RuntimeError) as exc_info:
                safe_copytree(
                    str(src), str(dst),
                    log_callback=lambda *_: None,
                    mode="write",
                )
            assert "fail ratio" in str(exc_info.value)

    def test_samefile_tolerated(self, tmp_path):
        """SameFileError không tính vào fail."""
        src = self._make_src(tmp_path, 2)
        dst = tmp_path / "dst"

        import shutil as _sh
        with patch("core.fs_utils.shutil.copy2",
                   side_effect=_sh.SameFileError("same")):
            ok = safe_copytree(
                str(src), str(dst),
                log_callback=lambda *_: None,
                mode="write",
            )
        # All SameFileError → treated as success
        assert ok is True

    def test_empty_src(self, tmp_path):
        src = tmp_path / "empty"
        src.mkdir()
        dst = tmp_path / "dst"
        ok = safe_copytree(
            str(src), str(dst),
            log_callback=lambda *_: None,
            mode="write",
        )
        assert ok is True


# ============================================================
# Constants
# ============================================================
def test_copy_fail_tolerance_is_float():
    assert isinstance(_COPY_FAIL_TOLERANCE, float)
    assert 0 < _COPY_FAIL_TOLERANCE < 1