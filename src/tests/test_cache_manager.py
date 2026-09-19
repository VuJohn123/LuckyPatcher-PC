"""Test core/cache_manager.py — cache dispatcher."""
import os
from unittest.mock import MagicMock, patch

import pytest

from core.cache_manager import (
    _CACHE_7Z_FILENAME,
    _CACHE_TAR_FILENAME,
    _CACHE_ZIP_FILENAME,
    cache_is_valid,
    cache_load,
    cache_mtime,
    cache_save,
    decide_cache_format,
    find_existing_archive,
    get_apk_hash,
    get_cache_dir,
    write_cache_marker,
)


# ============================================================
# get_apk_hash
# ============================================================
class TestGetApkHash:
    def test_deterministic(self, tmp_path):
        f = tmp_path / "a.apk"
        f.write_bytes(b"content")
        h1 = get_apk_hash(str(f))
        h2 = get_apk_hash(str(f))
        assert h1 == h2
        assert len(h1) == 32

    def test_changes_with_content(self, tmp_path):
        f1 = tmp_path / "a.apk"
        f1.write_bytes(b"content1")
        f2 = tmp_path / "b.apk"
        f2.write_bytes(b"content2")
        assert get_apk_hash(str(f1)) != get_apk_hash(str(f2))


# ============================================================
# get_cache_dir
# ============================================================
class TestGetCacheDir:
    def test_creates_dir(self, tmp_path):
        f = tmp_path / "x.apk"
        f.write_bytes(b"x")
        base = tmp_path / "cache"
        result = get_cache_dir(str(f), str(base))
        assert os.path.isdir(result)
        assert result.startswith(str(base))

    def test_same_hash_same_dir(self, tmp_path):
        f = tmp_path / "y.apk"
        f.write_bytes(b"y")
        base = tmp_path / "cache"
        r1 = get_cache_dir(str(f), str(base))
        r2 = get_cache_dir(str(f), str(base))
        assert r1 == r2


# ============================================================
# decide_cache_format
# ============================================================
class TestDecideCacheFormat:
    def test_raw_small_dir(self, tmp_path):
        for i in range(5):
            (tmp_path / f"f{i}.txt").write_text("x")
        assert decide_cache_format(str(tmp_path)) == "raw"

    def test_archive_by_file_count(self, tmp_path):
        for i in range(3100):
            (tmp_path / f"f{i}.txt").write_text("")
        assert decide_cache_format(str(tmp_path)) == "archive"

    def test_archive_by_size(self, tmp_path):
        big = tmp_path / "big.bin"
        big.write_bytes(b"0" * (60 * 1024 * 1024))
        assert decide_cache_format(str(tmp_path)) == "archive"

    def test_empty_dir_is_raw(self, tmp_path):
        assert decide_cache_format(str(tmp_path)) == "raw"


# ============================================================
# Discovery
# ============================================================
class TestFindExistingArchive:
    def test_finds_7z(self, tmp_path):
        (tmp_path / _CACHE_7Z_FILENAME).write_bytes(b"x")
        found = find_existing_archive(str(tmp_path))
        assert found is not None
        assert found.endswith(_CACHE_7Z_FILENAME)

    def test_finds_zip(self, tmp_path):
        (tmp_path / _CACHE_ZIP_FILENAME).write_bytes(b"x")
        found = find_existing_archive(str(tmp_path))
        assert found is not None
        assert found.endswith(_CACHE_ZIP_FILENAME)

    def test_finds_tar(self, tmp_path):
        (tmp_path / _CACHE_TAR_FILENAME).write_bytes(b"x")
        found = find_existing_archive(str(tmp_path))
        assert found is not None

    def test_prefers_7z_over_zip(self, tmp_path):
        (tmp_path / _CACHE_7Z_FILENAME).write_bytes(b"7z")
        (tmp_path / _CACHE_ZIP_FILENAME).write_bytes(b"zip")
        found = find_existing_archive(str(tmp_path))
        assert found.endswith(_CACHE_7Z_FILENAME)

    def test_none_when_empty(self, tmp_path):
        assert find_existing_archive(str(tmp_path)) is None


class TestCacheIsValid:
    def test_valid_with_archive(self, tmp_path):
        (tmp_path / _CACHE_7Z_FILENAME).write_bytes(b"x")
        assert cache_is_valid(str(tmp_path)) is True

    def test_valid_with_apktool_yml(self, tmp_path):
        (tmp_path / "apktool.yml").write_text("v: 3")
        assert cache_is_valid(str(tmp_path)) is True

    def test_invalid_empty(self, tmp_path):
        assert cache_is_valid(str(tmp_path)) is False

    def test_invalid_nonexistent(self, tmp_path):
        assert cache_is_valid(str(tmp_path / "nope")) is False


class TestCacheMtime:
    def test_archive_mtime(self, tmp_path):
        p = tmp_path / _CACHE_7Z_FILENAME
        p.write_bytes(b"x")
        mtime = cache_mtime(str(tmp_path))
        assert mtime > 0

    def test_yml_mtime(self, tmp_path):
        p = tmp_path / "apktool.yml"
        p.write_text("v: 3")
        mtime = cache_mtime(str(tmp_path))
        assert mtime > 0

    def test_zero_when_empty(self, tmp_path):
        assert cache_mtime(str(tmp_path)) == 0.0


class TestWriteCacheMarker:
    def test_creates_marker_file(self, tmp_path):
        write_cache_marker(str(tmp_path), "raw")
        marker = tmp_path / ".cache_format"
        assert marker.exists()
        assert marker.read_text() == "raw"

    def test_handles_oserror(self, tmp_path):
        ro = tmp_path / "ro"
        ro.mkdir()
        with patch("builtins.open", side_effect=OSError("denied")):
            write_cache_marker(str(ro), "raw")  # no raise


# ============================================================
# cache_save
# ============================================================
class TestCacheSave:
    def test_small_dir_uses_safe_copytree(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("x")
        cache = tmp_path / "cache"
        cache.mkdir()

        # Mock safe_copytree phải TẠO DIR (vì cache_save gọi remove_dst
        # trước khi copy → dir bị xóa). write_cache_marker sau đó cần
        # dir tồn tại để ghi file.
        def _mock_copy(src_dir, dst_dir, log_callback, **kwargs):
            os.makedirs(dst_dir, exist_ok=True)
            return True

        with patch(
            "core.cache_manager.safe_copytree",
            side_effect=_mock_copy,
        ) as mock_copy:
            ok = cache_save(str(src), str(cache), lambda *_: None)
        assert ok is True
        mock_copy.assert_called_once()
        # Marker được ghi (vì mock đã tạo dir)
        assert (cache / ".cache_format").exists()
        assert (cache / ".cache_format").read_text() == "raw"

    def test_large_dir_prefers_robocopy(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "big.bin").write_bytes(b"0" * (60 * 1024 * 1024))
        cache = tmp_path / "cache"
        cache.mkdir()

        with patch(
            "core.cache_manager.has_robocopy", return_value=True
        ), patch(
            "core.cache_manager.robocopy_copy", return_value=True
        ) as mock_rc:
            ok = cache_save(str(src), str(cache), lambda *_: None)
        assert ok is True
        mock_rc.assert_called_once()

    def test_falls_back_to_7z(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "big.bin").write_bytes(b"0" * (60 * 1024 * 1024))
        cache = tmp_path / "cache"
        cache.mkdir()

        def _fake_7z(src_dir, archive_path, log_callback,
                     label="Cache save"):
            with open(archive_path, "wb") as f:
                f.write(b"fake 7z")
            return True

        with patch(
            "core.cache_manager.has_robocopy", return_value=False
        ), patch(
            "core.cache_manager.archive_via_7z", side_effect=_fake_7z
        ):
            ok = cache_save(str(src), str(cache), lambda *_: None)
        assert ok is True


# ============================================================
# cache_load
# ============================================================
class TestCacheLoad:
    def test_loads_archive_via_7z(self, tmp_path):
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / _CACHE_7Z_FILENAME).write_bytes(b"fake")
        dst = tmp_path / "dst"

        with patch(
            "core.cache_manager.extract_via_7z",
            return_value=True,
        ) as mock_x:
            with patch("os.path.isdir", return_value=True):
                ok = cache_load(str(cache), str(dst), lambda *_: None)
        assert ok is True
        mock_x.assert_called_once()

    def test_loads_zip_via_python_fallback(self, tmp_path):
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / _CACHE_ZIP_FILENAME).write_bytes(b"fake")
        dst = tmp_path / "dst"

        with patch(
            "core.cache_manager.extract_via_7z", return_value=False
        ), patch(
            "core.cache_manager.extract_via_python", return_value=True
        ) as mock_py:
            ok = cache_load(str(cache), str(dst), lambda *_: None)
        assert ok is True
        mock_py.assert_called_once()

    def test_raw_load_uses_robocopy_no_junction(self, tmp_path):
        """v2: raw cache load KHÔNG dùng junction."""
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "apktool.yml").write_text("v:3")
        dst = tmp_path / "dst"

        with patch(
            "core.cache_manager.has_robocopy", return_value=True
        ), patch(
            "core.cache_manager.robocopy_copy", return_value=True
        ) as mock_rc, patch("core.cache_manager.remove_dst"):
            with patch("os.path.isdir", return_value=True):
                ok = cache_load(str(cache), str(dst), lambda *_: None)
        assert ok is True
        mock_rc.assert_called_once()

    def test_no_archive_returns_raw_copy(self, tmp_path):
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "apktool.yml").write_text("v:3")
        dst = tmp_path / "dst"

        with patch(
            "core.cache_manager.has_robocopy", return_value=False
        ), patch(
            "core.cache_manager.safe_copytree", return_value=True
        ) as mock_copy:
            ok = cache_load(str(cache), str(dst), lambda *_: None)
        assert ok is True
        mock_copy.assert_called_once()