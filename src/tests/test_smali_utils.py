"""Test smali utils — regex, path scanning, cache."""
import os
import tempfile

from core.smali_utils import (
    FileContentCache,
    get_all_smali_files,
    get_smali_dirs,
    REGEX_BOOLEAN_METHOD,
)


def test_get_smali_dirs_finds_smali():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "smali"))
        os.makedirs(os.path.join(tmp, "smali_classes2"))
        os.makedirs(os.path.join(tmp, "res"))
        dirs = get_smali_dirs(tmp)
        assert len(dirs) == 2
        assert any("smali" in d for d in dirs)


def test_get_smali_dirs_fallback():
    with tempfile.TemporaryDirectory() as tmp:
        dirs = get_smali_dirs(tmp)
        assert len(dirs) == 1
        assert dirs[0].endswith("smali")


def test_get_all_smali_files():
    with tempfile.TemporaryDirectory() as tmp:
        smali = os.path.join(tmp, "smali", "com", "test")
        os.makedirs(smali)
        with open(os.path.join(smali, "A.smali"), "w") as f:
            f.write(".class public LA;")
        with open(os.path.join(smali, "not.txt"), "w") as f:
            f.write("skip")
        files = get_all_smali_files(tmp)
        assert len(files) == 1
        assert files[0].endswith(".smali")


def test_file_content_cache_read():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "x.smali")
        with open(path, "w") as f:
            f.write(".class public LX;")
        cache = FileContentCache(tmp)
        assert cache.read(path) == ".class public LX;"
        # Cache hit — sửa file ngoài disk, cache không đổi
        with open(path, "w") as f:
            f.write("modified")
        assert cache.read(path) == ".class public LX;"


def test_file_content_cache_write_flush():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "sub", "x.smali")
        cache = FileContentCache(tmp)
        cache.write(path, ".class public LX;")
        cache.flush()
        with open(path) as f:
            assert f.read() == ".class public LX;"


def test_file_content_cache_read_missing():
    with tempfile.TemporaryDirectory() as tmp:
        cache = FileContentCache(tmp)
        assert cache.read(os.path.join(tmp, "nope.smali")) == ""


def test_regex_boolean_method():
    sample = (
        ".method public allow()Z\n"
        "    .locals 1\n"
        "    const/4 v0, 0x1\n"
        "    return v0\n"
        ".end method"
    )
    m = REGEX_BOOLEAN_METHOD.search(sample)
    assert m is not None
    assert "allow" in m.group(0)