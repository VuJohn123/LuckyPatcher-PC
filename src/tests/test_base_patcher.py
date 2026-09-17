"""Test patcher/base.py — BasePatcher abstract + helpers."""
import os

import pytest

from patcher.base import BasePatcher


class _ConcretePatcher(BasePatcher):
    """Concrete implementation để test abstract methods."""
    def patch(self) -> int:
        return 0


# ============================================================
# Abstract behavior
# ============================================================
def test_base_is_abstract():
    """Không instantiate trực tiếp được."""
    with pytest.raises(TypeError):
        BasePatcher("/tmp/test")  # type: ignore


def test_concrete_subclass_instantiable(tmp_path):
    p = _ConcretePatcher(str(tmp_path), log_callback=lambda *_: None)
    assert p.decompiled_path == str(tmp_path)
    assert callable(p.log)


def test_concrete_patch_returns_int(tmp_path):
    p = _ConcretePatcher(str(tmp_path))
    result = p.patch()
    assert isinstance(result, int)
    assert result >= 0


# ============================================================
# _read helper — không có cache
# ============================================================
def test_read_without_cache(tmp_path):
    f = tmp_path / "test.smali"
    f.write_text("content", encoding="utf-8")

    p = _ConcretePatcher(str(tmp_path))
    assert p._read(str(f)) == "content"


def test_read_missing_file_raises(tmp_path):
    p = _ConcretePatcher(str(tmp_path))
    with pytest.raises((OSError, FileNotFoundError)):
        p._read(str(tmp_path / "nonexistent.smali"))


# ============================================================
# _read helper — có cache
# ============================================================
def test_read_uses_cache(tmp_path):
    from unittest.mock import MagicMock
    cache = MagicMock()
    cache.read.return_value = "from-cache"

    p = _ConcretePatcher(str(tmp_path), file_cache=cache)
    result = p._read("/any/path.smali")
    assert result == "from-cache"
    cache.read.assert_called_once_with("/any/path.smali")


# ============================================================
# _write helper
# ============================================================
def test_write_without_cache(tmp_path):
    f = tmp_path / "test.smali"
    p = _ConcretePatcher(str(tmp_path))
    p._write(str(f), "new content")
    assert f.read_text(encoding="utf-8") == "new content"


def test_write_uses_cache(tmp_path):
    from unittest.mock import MagicMock
    cache = MagicMock()

    p = _ConcretePatcher(str(tmp_path), file_cache=cache)
    p._write("/any/path.smali", "content")
    cache.write.assert_called_once_with("/any/path.smali", "content")


def test_init_with_all_params(tmp_path):
    cache = object()
    p = _ConcretePatcher(
        str(tmp_path),
        log_callback=lambda *_: None,
        file_cache=cache,
    )
    assert p.file_cache is cache