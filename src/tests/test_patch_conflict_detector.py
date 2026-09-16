"""Test conflict detector."""
from core.patch_conflict_detector import detect_conflicts


def test_no_conflict_between_different():
    conflicts = detect_conflicts(["license", "ads_offline"])
    assert conflicts == []


def test_conflict_manifest_ads_vs_change_perms():
    conflicts = detect_conflicts(["ads", "change_perms"])
    # cả hai dùng AndroidManifest.xml
    assert len(conflicts) == 1
    m1, m2, targets = conflicts[0]
    assert "AndroidManifest.xml" in targets


def test_conflict_iap_dex_and_iap_proxy():
    conflicts = detect_conflicts(["iap_dex", "iap_proxy"])
    assert len(conflicts) == 1


def test_multiple_conflicts():
    conflicts = detect_conflicts(["ads", "change_perms", "clone"])
    # ads vs change_perms, ads vs clone, change_perms vs clone
    assert len(conflicts) == 3


def test_empty_modes():
    assert detect_conflicts([]) == []


def test_single_mode():
    assert detect_conflicts(["license"]) == []