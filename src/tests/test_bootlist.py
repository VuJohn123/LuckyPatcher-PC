"""Test core/bootlist.py — bootlist manager."""
from __future__ import annotations

import os
import time

import pytest

from core.bootlist import (
    _BOOTLIST_VERSION,
    _MAX_ENTRIES,
    BootListManager,
    BootlistEntry,
    _compute_file_hash,
    get_bootlist,
)


# ============================================================
# Helpers
# ============================================================
def _make_apk(tmp_path, name="app.apk", content=b"fake apk"):
    apk = tmp_path / name
    apk.write_bytes(content)
    return apk


# ============================================================
# BootlistEntry
# ============================================================
class TestBootlistEntry:
    def test_defaults(self):
        e = BootlistEntry(package="com.x", apk_path="/tmp/x.apk")
        assert e.modes == []
        assert e.custom_patch is None
        assert e.apply_count == 0

    def test_age_days(self):
        e = BootlistEntry(
            package="com.x", apk_path="/tmp/x.apk",
            created_at=time.time() - 86400,
        )
        assert 0.9 <= e.age_days <= 1.1


# ============================================================
# _compute_file_hash
# ============================================================
class TestComputeFileHash:
    def test_deterministic(self, tmp_path):
        f = _make_apk(tmp_path)
        h1 = _compute_file_hash(str(f))
        h2 = _compute_file_hash(str(f))
        assert h1 == h2
        assert len(h1) == 32

    def test_changes_with_content(self, tmp_path):
        f1 = _make_apk(tmp_path, "a.apk", b"content1")
        f2 = _make_apk(tmp_path, "b.apk", b"content2")
        assert _compute_file_hash(str(f1)) != _compute_file_hash(str(f2))


# ============================================================
# Add
# ============================================================
class TestAddEntry:
    def test_add_new(self, tmp_path):
        bl = BootListManager(
            str(tmp_path / "bootlist.json"),
            log_callback=lambda *a: None,
        )
        apk = _make_apk(tmp_path)
        ok = bl.add_entry(
            package="com.example.app",
            apk_path=str(apk),
            modes=["iap_dex", "license"],
        )
        assert ok is True
        entries = bl.get_entries()
        assert len(entries) == 1
        assert entries[0]["package"] == "com.example.app"
        assert entries[0]["modes"] == ["iap_dex", "license"]
        assert entries[0]["apk_hash"]

    def test_add_updates_existing(self, tmp_path):
        bl = BootListManager(
            str(tmp_path / "bootlist.json"),
            log_callback=lambda *a: None,
        )
        apk = _make_apk(tmp_path)
        bl.add_entry("com.x", str(apk), ["iap_dex"])
        bl.add_entry("com.x", str(apk), ["license", "ads"])

        entries = bl.get_entries()
        assert len(entries) == 1
        assert entries[0]["modes"] == ["license", "ads"]

    def test_add_missing_apk_returns_false(self, tmp_path):
        bl = BootListManager(
            str(tmp_path / "bootlist.json"),
            log_callback=lambda *a: None,
        )
        ok = bl.add_entry(
            package="com.x",
            apk_path=str(tmp_path / "nonexistent.apk"),
            modes=["iap_dex"],
        )
        assert ok is False
        assert bl.get_entries() == []

    def test_add_empty_package_returns_false(self, tmp_path):
        bl = BootListManager(
            str(tmp_path / "bootlist.json"),
            log_callback=lambda *a: None,
        )
        apk = _make_apk(tmp_path)
        ok = bl.add_entry("", str(apk), ["iap"])
        assert ok is False

    def test_add_custom_patch(self, tmp_path):
        bl = BootListManager(
            str(tmp_path / "bootlist.json"),
            log_callback=lambda *a: None,
        )
        apk = _make_apk(tmp_path)
        bl.add_entry(
            "com.x", str(apk), ["iap"],
            custom_patch="/patches/custom.txt",
        )
        entries = bl.get_entries()
        assert entries[0]["custom_patch"] == "/patches/custom.txt"


# ============================================================
# Remove
# ============================================================
class TestRemoveEntry:
    def test_remove_existing(self, tmp_path):
        bl = BootListManager(
            str(tmp_path / "bootlist.json"),
            log_callback=lambda *a: None,
        )
        apk = _make_apk(tmp_path)
        bl.add_entry("com.x", str(apk), ["iap"])
        assert bl.remove_entry("com.x") is True
        assert bl.get_entries() == []

    def test_remove_nonexistent_returns_false(self, tmp_path):
        bl = BootListManager(
            str(tmp_path / "bootlist.json"),
            log_callback=lambda *a: None,
        )
        assert bl.remove_entry("com.nonexistent") is False


# ============================================================
# Has package
# ============================================================
class TestHasPackage:
    def test_has_existing(self, tmp_path):
        bl = BootListManager(
            str(tmp_path / "bootlist.json"),
            log_callback=lambda *a: None,
        )
        apk = _make_apk(tmp_path)
        bl.add_entry("com.x", str(apk), ["iap"])
        assert bl.has_package("com.x") is True

    def test_has_not_existing(self, tmp_path):
        bl = BootListManager(
            str(tmp_path / "bootlist.json"),
            log_callback=lambda *a: None,
        )
        assert bl.has_package("com.y") is False


# ============================================================
# Get pending
# ============================================================
class TestGetPending:
    def test_pending_verify_hash(self, tmp_path):
        bl = BootListManager(
            str(tmp_path / "bootlist.json"),
            log_callback=lambda *a: None,
        )
        apk = _make_apk(tmp_path)
        bl.add_entry("com.x", str(apk), ["iap"])

        pending = bl.get_pending_reapply(verify_hash=True)
        assert len(pending) == 1

    def test_skip_missing_apk(self, tmp_path):
        bl = BootListManager(
            str(tmp_path / "bootlist.json"),
            log_callback=lambda *a: None,
        )
        apk = _make_apk(tmp_path)
        bl.add_entry("com.x", str(apk), ["iap"])
        os.remove(str(apk))

        pending = bl.get_pending_reapply(verify_hash=True)
        assert pending == []

    def test_skip_hash_mismatch(self, tmp_path):
        bl = BootListManager(
            str(tmp_path / "bootlist.json"),
            log_callback=lambda *a: None,
        )
        apk = _make_apk(tmp_path, content=b"original")
        bl.add_entry("com.x", str(apk), ["iap"])

        apk.write_bytes(b"modified")

        pending = bl.get_pending_reapply(verify_hash=True)
        assert pending == []

    def test_include_mismatch_when_not_verifying(self, tmp_path):
        bl = BootListManager(
            str(tmp_path / "bootlist.json"),
            log_callback=lambda *a: None,
        )
        apk = _make_apk(tmp_path, content=b"original")
        bl.add_entry("com.x", str(apk), ["iap"])
        apk.write_bytes(b"modified")

        pending = bl.get_pending_reapply(verify_hash=False)
        assert len(pending) == 1


# ============================================================
# Mark applied
# ============================================================
class TestMarkApplied:
    def test_mark_increments_count(self, tmp_path):
        bl = BootListManager(
            str(tmp_path / "bootlist.json"),
            log_callback=lambda *a: None,
        )
        apk = _make_apk(tmp_path)
        bl.add_entry("com.x", str(apk), ["iap"])

        bl.mark_applied("com.x")
        entries = bl.get_entries()
        assert entries[0]["apply_count"] == 1
        assert entries[0]["last_applied"] > 0

    def test_mark_nonexistent_noop(self, tmp_path):
        bl = BootListManager(
            str(tmp_path / "bootlist.json"),
            log_callback=lambda *a: None,
        )
        bl.mark_applied("com.nonexistent")


# ============================================================
# Cap entries
# ============================================================
class TestCapEntries:
    def test_max_entries_respected(self, tmp_path):
        bl = BootListManager(
            str(tmp_path / "bootlist.json"),
            log_callback=lambda *a: None,
        )
        for i in range(_MAX_ENTRIES + 10):
            apk = _make_apk(tmp_path, f"app{i}.apk", str(i).encode())
            bl.add_entry(f"com.x{i}", str(apk), ["iap"])

        entries = bl.get_entries()
        assert len(entries) <= _MAX_ENTRIES


# ============================================================
# Clear
# ============================================================
class TestClear:
    def test_clear(self, tmp_path):
        bl = BootListManager(
            str(tmp_path / "bootlist.json"),
            log_callback=lambda *a: None,
        )
        apk = _make_apk(tmp_path)
        bl.add_entry("com.x", str(apk), ["iap"])
        bl.clear()
        assert bl.get_entries() == []


# ============================================================
# Corrupted JSON
# ============================================================
class TestCorruptedJson:
    def test_corrupted_file_recovers(self, tmp_path):
        path = tmp_path / "bootlist.json"
        path.write_text("{ corrupted json")
        bl = BootListManager(str(path), log_callback=lambda *a: None)
        assert bl.get_entries() == []

    def test_non_dict_json_recovers(self, tmp_path):
        path = tmp_path / "bootlist.json"
        path.write_text('["not a dict"]')
        bl = BootListManager(str(path), log_callback=lambda *a: None)
        assert bl.get_entries() == []

    def test_missing_entries_key_recovers(self, tmp_path):
        path = tmp_path / "bootlist.json"
        path.write_text('{"version": 1}')
        bl = BootListManager(str(path), log_callback=lambda *a: None)
        assert bl.get_entries() == []


# ============================================================
# Singleton
# ============================================================
def test_get_bootlist_returns_instance(tmp_path, monkeypatch):
    import core.bootlist as _b
    monkeypatch.setattr(_b, "_default_manager", None)

    bl = get_bootlist(
        str(tmp_path / "bootlist.json"),
        log_callback=lambda *a: None,
    )
    assert isinstance(bl, BootListManager)