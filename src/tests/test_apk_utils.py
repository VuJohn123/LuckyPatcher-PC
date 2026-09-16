"""Test apk_utils helpers (không cần Android tools)."""
import os
import tempfile

from core.apk_utils import get_apk_hash, get_cache_dir


def test_apk_hash_deterministic():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "x.apk")
        with open(path, "wb") as f:
            f.write(b"hello world")
        h1 = get_apk_hash(path)
        h2 = get_apk_hash(path)
        assert h1 == h2


def test_apk_hash_changes_with_content():
    with tempfile.TemporaryDirectory() as tmp:
        a = os.path.join(tmp, "a.apk")
        b = os.path.join(tmp, "b.apk")
        with open(a, "wb") as f:
            f.write(b"AAAA")
        with open(b, "wb") as f:
            f.write(b"BBBB")
        assert get_apk_hash(a) != get_apk_hash(b)


def test_get_cache_dir_creates():
    with tempfile.TemporaryDirectory() as tmp:
        apk = os.path.join(tmp, "x.apk")
        with open(apk, "wb") as f:
            f.write(b"data")
        base = os.path.join(tmp, "cache")
        cache = get_cache_dir(apk, base_cache_dir=base)
        assert os.path.isdir(cache)
        assert os.path.dirname(cache) == base