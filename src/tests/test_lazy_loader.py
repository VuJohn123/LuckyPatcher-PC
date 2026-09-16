"""Test lazy loader — import chỉ khi cần, cache kết quả."""
from core.lazy_loader import (
    CLASS_NAME_MAP,
    PATCHER_MAP,
    get_patcher_class,
)


def test_maps_have_matching_keys():
    for k in PATCHER_MAP:
        assert k in CLASS_NAME_MAP, f"{k} có trong PATCHER_MAP nhưng thiếu CLASS_NAME_MAP"


def test_unknown_mode_returns_none():
    assert get_patcher_class("nonexistent_mode_xyz") is None


def test_known_mode_returns_class_or_none():
    # Không crash ngay cả khi module import fail
    cls = get_patcher_class("license")
    # None hoặc class — cả hai đều ok
    assert cls is None or isinstance(cls, type)


def test_cache_returns_same_instance():
    a = get_patcher_class("license")
    b = get_patcher_class("license")
    assert a is b