"""Test core/patch_history.py — record + atomic IO + trace_id."""
from __future__ import annotations

import json
import os
import time

import pytest

from core.patch_history import PatchHistory, _MAX_ENTRIES


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def hist(tmp_path):
    """Fresh PatchHistory pointing at tmp file."""
    return PatchHistory(str(tmp_path / "history.json"))


# ============================================================
# Constructor flexibility
# ============================================================
class TestConstructor:
    def test_default_path(self):
        h = PatchHistory()
        assert "workspace" in h.history_file
        assert h.history_file.endswith("patch_history.json")

    def test_positional_path(self, tmp_path):
        target = tmp_path / "custom.json"
        h = PatchHistory(str(target))
        assert h.history_file == str(target)

    def test_path_object(self, tmp_path):
        target = tmp_path / "pathobj.json"
        h = PatchHistory(target)  # Path accepted
        assert h.history_file == str(target)

    def test_kwarg_history_file(self, tmp_path):
        target = tmp_path / "kw.json"
        h = PatchHistory(history_file=str(target))
        assert h.history_file == str(target)

    def test_kwarg_history_dir(self, tmp_path):
        h = PatchHistory(history_dir=str(tmp_path))
        assert h.history_file == str(tmp_path / "patch_history.json")

    def test_kwarg_filename(self, tmp_path):
        h = PatchHistory(
            history_dir=str(tmp_path), filename="custom.json",
        )
        assert h.history_file == str(tmp_path / "custom.json")

    def test_legacy_file_alias(self, tmp_path):
        target = tmp_path / "legacy.json"
        h = PatchHistory(file=str(target))
        assert h.history_file == str(target)

    def test_legacy_path_alias(self, tmp_path):
        target = tmp_path / "legacy2.json"
        h = PatchHistory(path=str(target))
        assert h.history_file == str(target)

    def test_creates_parent_dir(self, tmp_path):
        target = tmp_path / "deep" / "nested" / "h.json"
        assert not target.parent.exists()
        PatchHistory(str(target))
        assert target.parent.exists()


# ============================================================
# Add + Get
# ============================================================
class TestAddRecord:
    def test_add_and_get(self, hist):
        hist.add_record("a.apk", "license", True, "out.apk", ["license"])
        records = hist.get_history()
        assert len(records) == 1
        assert records[0]["apk"] == "a.apk"
        assert records[0]["mode"] == "license"
        assert records[0]["success"] is True
        assert records[0]["output"] == "out.apk"
        assert records[0]["patches"] == ["license"]

    def test_newest_first(self, hist):
        for i in range(3):
            hist.add_record(f"a{i}.apk", "license", True)
        records = hist.get_history()
        # Newest first → a2, a1, a0
        assert [r["apk"] for r in records] == ["a2.apk", "a1.apk", "a0.apk"]

    def test_default_fields(self, hist):
        hist.add_record("a.apk", "license", False)
        r = hist.get_history()[0]
        assert r["output"] == ""
        assert r["patches"] == []
        assert r["trace_id"] == ""

    def test_trace_id_persisted(self, hist):
        hist.add_record(
            "a.apk", "license", True, trace_id="abcd1234",
        )
        r = hist.get_history()[0]
        assert r["trace_id"] == "abcd1234"

    def test_max_entries_cap(self, hist):
        for i in range(_MAX_ENTRIES + 20):
            hist.add_record(f"a{i}.apk", "license", True)
        records = hist.get_history()
        assert len(records) == _MAX_ENTRIES
        # Newest preserved — a119 (last) should be first
        assert records[0]["apk"] == f"a{_MAX_ENTRIES + 19}.apk"

    def test_patches_list_is_copied(self, hist):
        patches = ["a", "b"]
        hist.add_record("x.apk", "license", True, patches=patches)
        patches.append("c")  # mutate original
        r = hist.get_history()[0]
        assert r["patches"] == ["a", "b"]  # unchanged


# ============================================================
# Clear
# ============================================================
class TestClear:
    def test_clear(self, hist):
        hist.add_record("a.apk", "license", True)
        hist.clear()
        assert hist.get_history() == []

    def test_clear_empty(self, hist):
        hist.clear()  # no prior records
        assert hist.get_history() == []


# ============================================================
# Corrupted file recovery
# ============================================================
class TestCorruptedFile:
    def test_corrupted_json_recovers(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{ corrupted json !!!")
        h = PatchHistory(str(p))
        assert h.get_history() == []

    def test_non_list_json_recovers(self, tmp_path):
        p = tmp_path / "dict.json"
        p.write_text('{"not": "a list"}')
        h = PatchHistory(str(p))
        assert h.get_history() == []

    def test_missing_file_empty(self, tmp_path):
        h = PatchHistory(str(tmp_path / "missing.json"))
        assert h.get_history() == []

    def test_after_corrupt_still_writable(self, tmp_path):
        p = tmp_path / "recover.json"
        p.write_text("{ bad")
        h = PatchHistory(str(p))
        h.add_record("a.apk", "license", True)
        assert len(h.get_history()) == 1


# ============================================================
# Atomic IO
# ============================================================
class TestAtomicIO:
    def test_file_valid_json_after_write(self, hist):
        hist.add_record("a.apk", "license", True)
        with open(hist.history_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) == 1

    def test_no_tmp_file_left_behind(self, hist):
        hist.add_record("a.apk", "license", True)
        d = os.path.dirname(hist.history_file)
        tmps = [f for f in os.listdir(d) if f.endswith(".tmp")]
        assert tmps == []


# ============================================================
# Timestamp monotonic
# ============================================================
class TestTimestamp:
    def test_timestamp_increases(self, hist):
        hist.add_record("a.apk", "license", True)
        t1 = hist.get_history()[0]["timestamp"]
        time.sleep(0.01)
        hist.add_record("b.apk", "license", True)
        t2 = hist.get_history()[0]["timestamp"]
        assert t2 > t1