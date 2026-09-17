"""Test smali_utils — các phần chưa được cover."""
import os
from unittest.mock import MagicMock, patch

import pytest

from core.smali_utils import (
    APKCache,
    FileContentCache,
    JSON_FAST,
    RE_ENGINE,
    get_all_smali_files,
    get_smali_dirs,
    json_dumps,
    json_loads,
)


# ============================================================
# json_loads / json_dumps
# ============================================================
def test_json_loads_from_string():
    assert json_loads('{"a": 1}') == {"a": 1}


def test_json_loads_from_bytes():
    assert json_loads(b'{"a": 1}') == {"a": 1}


def test_json_dumps_returns_str():
    result = json_dumps({"a": 1})
    assert isinstance(result, str)
    assert "a" in result


# ============================================================
# get_smali_dirs
# ============================================================
def test_get_smali_dirs_multiple(tmp_path):
    (tmp_path / "smali").mkdir()
    (tmp_path / "smali_classes2").mkdir()
    (tmp_path / "smali_classes3").mkdir()
    (tmp_path / "assets").mkdir()

    dirs = get_smali_dirs(str(tmp_path))
    assert len(dirs) == 3


def test_get_smali_dirs_fallback(tmp_path):
    dirs = get_smali_dirs(str(tmp_path))
    assert len(dirs) == 1
    assert dirs[0].endswith("smali")


def test_get_smali_dirs_invalid_path():
    dirs = get_smali_dirs("/nonexistent/xyz")
    assert len(dirs) == 1


# ============================================================
# get_all_smali_files
# ============================================================
def test_get_all_smali_files_recursive(tmp_path):
    (tmp_path / "smali").mkdir()
    (tmp_path / "smali" / "com").mkdir()
    (tmp_path / "smali" / "com" / "A.smali").write_text("a")
    (tmp_path / "smali" / "B.smali").write_text("b")
    (tmp_path / "smali" / "not_smali.txt").write_text("x")

    files = get_all_smali_files(str(tmp_path))
    assert len(files) == 2
    assert all(f.endswith(".smali") for f in files)


def test_get_all_smali_files_empty(tmp_path):
    (tmp_path / "smali").mkdir()
    assert get_all_smali_files(str(tmp_path)) == []


# ============================================================
# FileContentCache
# ============================================================
def test_file_cache_write_then_read(tmp_path):
    f = tmp_path / "test.smali"
    f.write_text("original")

    cache = FileContentCache(str(tmp_path))
    assert cache.read(str(f)) == "original"

    cache.write(str(f), "modified")
    assert cache.read(str(f)) == "modified"


def test_file_cache_flush(tmp_path):
    f = tmp_path / "test.smali"
    f.write_text("original")

    cache = FileContentCache(str(tmp_path))
    cache.write(str(f), "modified")
    logs = []
    cache.flush(logs.append)

    assert f.read_text() == "modified"
    # Sau flush: _modified rỗng, _read_cache cũng cleared
    assert cache._modified == {}
    assert len(cache._read_cache) == 0


def test_file_cache_flush_error_isolated(tmp_path):
    """Flush lỗi 1 file → không crash, log warning, tiếp tục file khác."""
    cache = FileContentCache(str(tmp_path))
    # File với null char — os.makedirs raise ValueError
    cache.write("/invalid\x00path/file.smali", "bad")
    # File hợp lệ — phải flush được dù có file lỗi phía trước
    good = tmp_path / "good.smali"
    good.write_text("orig")
    cache.write(str(good), "modified-good")

    logs = []
    cache.flush(logs.append)  # Không raise

    assert good.read_text() == "modified-good"
    assert any("FileCache" in l for l in logs)
    # Cache đã clear
    assert cache._modified == {}


def test_file_cache_flush_type_error_isolated(tmp_path):
    """Cache chứa key không phải str → không crash (TypeError)."""
    cache = FileContentCache(str(tmp_path))
    # key là int, không phải str → os.makedirs sẽ raise TypeError
    cache._modified[12345] = "content"  # type: ignore
    logs = []
    cache.flush(logs.append)  # Không raise


def test_file_cache_get_modified_files(tmp_path):
    cache = FileContentCache(str(tmp_path))
    cache.write("a.smali", "x")
    cache.write("b.smali", "y")
    modified = cache.get_modified_files()
    assert "a.smali" in modified
    assert "b.smali" in modified


def test_file_cache_is_modified(tmp_path):
    cache = FileContentCache(str(tmp_path))
    assert cache.is_modified("test.smali") is False
    cache.write("test.smali", "x")
    assert cache.is_modified("test.smali") is True


# ============================================================
# APKCache
# ============================================================
def test_apk_cache_save_and_get(tmp_path):
    apk = tmp_path / "test.apk"
    apk.write_bytes(b"fake apk content")

    cache = APKCache(str(tmp_path / "cache"))
    cache.save_analysis(
        str(apk),
        findings=[{"type": "test"}],
        summary={"app_name": "Test"},
        colors=["green"],
    )

    result = cache.get_cached_analysis(str(apk))
    assert result is not None
    assert result["colors"] == ["green"]
    assert result["summary"]["app_name"] == "Test"
    assert result["findings"] == [{"type": "test"}]


def test_apk_cache_miss(tmp_path):
    apk = tmp_path / "test.apk"
    apk.write_bytes(b"fake")
    cache = APKCache(str(tmp_path / "cache"))
    assert cache.get_cached_analysis(str(apk)) is None


def test_apk_cache_corrupted_json(tmp_path):
    apk = tmp_path / "test.apk"
    apk.write_bytes(b"fake")
    cache = APKCache(str(tmp_path / "cache"))
    cache_path = cache.get_cache_path(str(apk))

    with open(cache_path, "w") as f:
        f.write("not json {{{")

    assert cache.get_cached_analysis(str(apk)) is None


def test_apk_cache_save_handles_oserror(tmp_path):
    cache = APKCache(str(tmp_path / "cache"))
    with pytest.raises((FileNotFoundError, OSError)):
        cache.get_cache_path("/nonexistent.apk")


# ============================================================
# Constants
# ============================================================
def test_re_engine_defined():
    assert RE_ENGINE in ("re2", "re")


def test_json_fast_defined():
    assert isinstance(JSON_FAST, bool)