"""Test patch history — atomic save, max entries."""
import json
import os
import tempfile

from core.patch_history import PatchHistory


def test_add_record_and_get():
    with tempfile.TemporaryDirectory() as tmp:
        h = PatchHistory(history_dir=tmp)
        h.add_record("/tmp/app.apk", "license", True, "/out.apk", ["license"])
        records = h.get_history()
        assert len(records) == 1
        assert records[0]["mode"] == "license"
        assert records[0]["success"] is True


def test_newest_first():
    with tempfile.TemporaryDirectory() as tmp:
        h = PatchHistory(history_dir=tmp)
        h.add_record("a.apk", "m1", True, "", [])
        h.add_record("b.apk", "m2", True, "", [])
        records = h.get_history()
        assert records[0]["apk"] == "b.apk"


def test_max_entries_cap():
    with tempfile.TemporaryDirectory() as tmp:
        h = PatchHistory(history_dir=tmp)
        h.max_entries = 5
        for i in range(10):
            h.add_record(f"a{i}.apk", "m", True, "", [])
        assert len(h.get_history()) == 5


def test_clear():
    with tempfile.TemporaryDirectory() as tmp:
        h = PatchHistory(history_dir=tmp)
        h.add_record("x.apk", "m", True, "", [])
        h.clear()
        assert h.get_history() == []


def test_corrupted_file_recovery():
    with tempfile.TemporaryDirectory() as tmp:
        # Ghi file JSON hỏng
        path = os.path.join(tmp, "patch_history.json")
        with open(path, "w") as f:
            f.write("{invalid json")
        h = PatchHistory(history_dir=tmp)
        assert h.get_history() == []