"""Test mode registry + parallel grouping."""
from core.mode_registry import (
    MODE_MAP,
    PARALLEL_GROUPS,
    get_mode_group,
)


def test_all_parallel_groups_have_modes():
    for group, modes in PARALLEL_GROUPS.items():
        assert modes, f"{group} rỗng"


def test_get_mode_group_known():
    assert get_mode_group("license") == "license_group"
    assert get_mode_group("ads_offline") == "ads_group"
    assert get_mode_group("sig_disable") == "sig_group"


def test_get_mode_group_unknown():
    assert get_mode_group("nonexistent") is None
    assert get_mode_group("backup") is None


def test_mode_map_values_are_strings():
    for k, v in MODE_MAP.items():
        assert isinstance(k, str) and isinstance(v, str)


def test_no_duplicate_group_membership():
    seen = {}
    for group, modes in PARALLEL_GROUPS.items():
        for m in modes:
            assert m not in seen, f"{m} in {group} and {seen.get(m)}"
            seen[m] = group