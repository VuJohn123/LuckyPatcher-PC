"""
Test trace_id persistence — metrics.json + patch_history.json.

Verify:
  - Schema fields round-trip (write → read).
  - Correlation: 2 pipeline runs → 2 distinct trace_id.
  - Filter by trace_id (mock helper).
  - Atomic write survives concurrent calls.
  - Backward-compat PatchHistory constructor.
  - trace_context integration (auto-capture via get_trace_id).
"""
from __future__ import annotations

import json
import os
import threading
import time

import pytest

from core.patch_history import PatchHistory
from core.metrics import (
    PatchMetrics,
    get_metrics,
    reset_metrics,
)
from core.trace_context import (
    get_trace_id,
    trace_context,
)


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def history(tmp_path) -> PatchHistory:
    return PatchHistory(history_file=str(tmp_path / "hist.json"))


@pytest.fixture
def metrics(tmp_path):
    """Fresh metrics singleton bound to tmp path."""
    path = str(tmp_path / "metrics.json")
    reset_metrics(path)
    yield get_metrics()
    reset_metrics()  # restore default for other tests


# ============================================================
# PATCH HISTORY — trace_id round-trip
# ============================================================
class TestPatchHistoryTraceId:
    def test_add_record_with_trace_id(self, history):
        history.add_record(
            apk_path="/tmp/a.apk",
            mode="license:auto",
            success=True,
            output_path="/out/a.apk",
            patches=["license"],
            trace_id="abc12345",
        )
        entries = history.get_history()
        assert len(entries) == 1
        assert entries[0]["trace_id"] == "abc12345"

    def test_default_trace_id_empty(self, history):
        history.add_record(
            apk_path="/tmp/a.apk",
            mode="license:auto",
            success=True,
        )
        entries = history.get_history()
        assert entries[0]["trace_id"] == ""

    def test_multiple_records_distinct_trace_ids(self, history):
        for tid in ("aaa11111", "bbb22222", "ccc33333"):
            history.add_record(
                apk_path=f"/tmp/{tid}.apk",
                mode="license:auto",
                success=True,
                trace_id=tid,
            )
        entries = history.get_history()
        assert len(entries) == 3
        tids = {e["trace_id"] for e in entries}
        assert tids == {"aaa11111", "bbb22222", "ccc33333"}

    def test_round_trip_preserves_all_fields(self, history):
        history.add_record(
            apk_path="/in/apk.apk",
            mode="iap:dex",
            success=True,
            output_path="/out/patched.apk",
            patches=["iap", "ads"],
            trace_id="tid_xyz",
        )
        entries = history.get_history()
        e = entries[0]
        assert e["apk"] == "/in/apk.apk"
        assert e["mode"] == "iap:dex"
        assert e["success"] is True
        assert e["output"] == "/out/patched.apk"
        assert e["patches"] == ["iap", "ads"]
        assert e["trace_id"] == "tid_xyz"
        assert isinstance(e["timestamp"], (int, float))

    def test_newest_first_ordering(self, history):
        history.add_record("/a.apk", "m1", True, trace_id="t1")
        time.sleep(0.01)
        history.add_record("/b.apk", "m2", True, trace_id="t2")
        entries = history.get_history()
        assert entries[0]["trace_id"] == "t2"
        assert entries[1]["trace_id"] == "t1"

    def test_failure_record_has_trace_id(self, history):
        history.add_record(
            apk_path="/bad.apk",
            mode="license:auto",
            success=False,
            trace_id="fail0001",
        )
        e = history.get_history()[0]
        assert e["success"] is False
        assert e["trace_id"] == "fail0001"

    def test_cap_at_max_entries(self, history):
        for i in range(150):
            history.add_record(
                f"/apk{i}.apk", "m", True, trace_id=f"t{i:04d}",
            )
        entries = history.get_history()
        # _MAX_ENTRIES = 100
        assert len(entries) == 100
        # Oldest (t0000..t0049) bị drop
        tids = {e["trace_id"] for e in entries}
        assert "t0149" in tids
        assert "t0000" not in tids

    def test_clear(self, history):
        history.add_record("/a.apk", "m", True, trace_id="t1")
        history.clear()
        assert history.get_history() == []


# ============================================================
# METRICS — trace_id round-trip
# ============================================================
class TestMetricsTraceId:
    def test_record_with_trace_id(self, metrics):
        metrics.record(PatchMetrics(
            apk_name="a.apk",
            mode="license:auto",
            success=True,
            duration_sec=1.5,
            patches_applied=3,
            stage="pipeline",
            trace_id="abc12345",
        ))
        all_entries = metrics.get_all()
        assert len(all_entries) == 1
        assert all_entries[0]["trace_id"] == "abc12345"

    def test_record_stage_with_trace_id(self, metrics):
        metrics.record_stage(
            apk_name="a.apk",
            mode="license:auto",
            stage="decompile",
            duration_sec=12.5,
            success=True,
            trace_id="stage001",
        )
        entries = metrics.get_all()
        assert entries[0]["stage"] == "decompile"
        assert entries[0]["trace_id"] == "stage001"

    def test_multiple_records_distinct_tids(self, metrics):
        for tid in ("t1", "t2", "t3"):
            metrics.record(PatchMetrics(
                apk_name=f"{tid}.apk", mode="m",
                success=True, trace_id=tid,
            ))
        all_entries = metrics.get_all()
        tids = {e["trace_id"] for e in all_entries}
        assert tids == {"t1", "t2", "t3"}

    def test_record_stage_default_trace_id_empty(self, metrics):
        metrics.record_stage(
            apk_name="a.apk", mode="m",
            stage="sign", duration_sec=0.5,
        )
        entries = metrics.get_all()
        assert entries[0]["trace_id"] == ""

    def test_summary_includes_trace_in_errors(self, metrics):
        metrics.record(PatchMetrics(
            apk_name="bad.apk",
            mode="m",
            success=False,
            error="Boom",
            trace_id="errr1234",
        ))
        summary = metrics.get_summary()
        assert len(summary["recent_errors"]) == 1
        err = summary["recent_errors"][0]
        assert err["trace_id"] == "errr1234"
        assert err["error"] == "Boom"

    def test_cap_max_entries(self, metrics):
        for i in range(600):
            metrics.record(PatchMetrics(
                apk_name=f"a{i}.apk", mode="m",
                success=True, trace_id=f"t{i:04d}",
            ))
        all_entries = metrics.get_all()
        # _MAX_ENTRIES = 500
        assert len(all_entries) == 500

    def test_clear_removes_file(self, metrics, tmp_path):
        metrics.record(PatchMetrics(
            apk_name="a.apk", mode="m", success=True,
            trace_id="t1",
        ))
        metrics.clear()
        assert metrics.get_all() == []


# ============================================================
# CORRELATION — filter by trace_id (mock helper)
# ============================================================
class TestCorrelation:
    """Simulate what UI/debug tooling would do: grep by tid."""

    @staticmethod
    def _filter_by_trace(entries: list[dict], tid: str) -> list[dict]:
        return [e for e in entries if e.get("trace_id") == tid]

    def test_history_filter_by_tid(self, history):
        for tid in ("run1", "run2", "run1", "run3", "run2"):
            history.add_record(
                "/a.apk", "m", True, trace_id=tid,
            )
        entries = history.get_history()
        run1 = self._filter_by_trace(entries, "run1")
        run2 = self._filter_by_trace(entries, "run2")
        assert len(run1) == 2
        assert len(run2) == 2

    def test_metrics_filter_by_tid(self, metrics):
        # 1 pipeline run "abc" → 3 stages
        for stage in ("decompile", "patch", "sign"):
            metrics.record_stage(
                apk_name="a.apk", mode="m", stage=stage,
                duration_sec=1.0, trace_id="abc12345",
            )
        # 1 run "xyz" → 1 stage
        metrics.record_stage(
            apk_name="b.apk", mode="m", stage="decompile",
            duration_sec=2.0, trace_id="xyz98765",
        )
        entries = metrics.get_all()
        abc = self._filter_by_trace(entries, "abc12345")
        xyz = self._filter_by_trace(entries, "xyz98765")
        assert len(abc) == 3
        assert len(xyz) == 1

    def test_cross_file_correlation(self, history, metrics, tmp_path):
        """
        Cùng 1 trace_id phải xuất hiện trong CẢ 2 file
        (giả lập pipeline run thật).
        """
        tid = "shared01"

        # History record (end of pipeline)
        history.add_record(
            "/in.apk", "license:auto", True,
            "/out.apk", ["license"], trace_id=tid,
        )

        # Metrics records (during pipeline)
        for stage in ("analyze", "decompile", "patch", "sign"):
            metrics.record_stage(
                apk_name="in.apk", mode="license:auto",
                stage=stage, duration_sec=1.0, trace_id=tid,
            )

        hist_entries = history.get_history()
        met_entries = metrics.get_all()

        hist_tids = {e["trace_id"] for e in hist_entries}
        met_tids = {e["trace_id"] for e in met_entries}

        assert tid in hist_tids
        assert tid in met_tids
        assert len([e for e in met_entries if e["trace_id"] == tid]) == 4


# ============================================================
# trace_context integration (auto-capture path)
# ============================================================
class TestTraceContextIntegration:
    def test_explicit_capture_from_context(self, history):
        """Pattern dùng trong main.py: pass trace_id từ context."""
        with trace_context("ctx12345") as tid:
            history.add_record(
                "/a.apk", "m", True, trace_id=tid,
            )
        entries = history.get_history()
        assert entries[0]["trace_id"] == "ctx12345"

    def test_get_trace_id_inside_context(self, metrics):
        with trace_context("auto0001"):
            current = get_trace_id()
            metrics.record_stage(
                apk_name="a.apk", mode="m", stage="analyze",
                duration_sec=1.0, trace_id=current,
            )
        entries = metrics.get_all()
        assert entries[0]["trace_id"] == "auto0001"

    def test_outside_context_returns_dash(self, history, metrics):
        """
        Ngoài trace_context, get_trace_id() = "-".
        Nếu caller vẫn pass → record "-".
        """
        tid = get_trace_id()
        assert tid == "-"
        history.add_record("/a.apk", "m", True, trace_id=tid)
        assert history.get_history()[0]["trace_id"] == "-"


# ============================================================
# ATOMICITY + THREAD SAFETY
# ============================================================
class TestAtomicity:
    def test_atomic_write_no_tmp_left(self, history, tmp_path):
        history.add_record("/a.apk", "m", True, trace_id="t1")
        files = list(tmp_path.glob("*.tmp"))
        assert files == [], f"Leftover tmp files: {files}"

    def test_json_valid_after_writes(self, history):
        for i in range(5):
            history.add_record(
                f"/a{i}.apk", "m", True, trace_id=f"t{i}",
            )
        with open(history.history_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) == 5

    def test_concurrent_writes_no_corrupt(self, history):
        def _writer(idx: int):
            history.add_record(
                f"/apk{idx}.apk", "m", True, trace_id=f"tid{idx}",
            )

        threads = [
            threading.Thread(target=_writer, args=(i,))
            for i in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        entries = history.get_history()
        # Với lock, không mất entry
        assert len(entries) == 20
        tids = {e["trace_id"] for e in entries}
        assert len(tids) == 20


# ============================================================
# BACKWARD COMPAT — PatchHistory constructor
# ============================================================
class TestPatchHistoryBackwardCompat:
    def test_default_path(self):
        h = PatchHistory()
        assert "workspace" in h.history_file
        assert h.history_file.endswith("patch_history.json")

    def test_history_file_kwarg(self, tmp_path):
        path = str(tmp_path / "custom.json")
        h = PatchHistory(history_file=path)
        assert h.history_file == path

    def test_legacy_file_kwarg(self, tmp_path):
        path = str(tmp_path / "legacy.json")
        h = PatchHistory(file=path)
        assert h.history_file == path

    def test_legacy_path_kwarg(self, tmp_path):
        path = str(tmp_path / "viapath.json")
        h = PatchHistory(path=path)
        assert h.history_file == path

    def test_storage_file_kwarg(self, tmp_path):
        path = str(tmp_path / "storage.json")
        h = PatchHistory(storage_file=path)
        assert h.history_file == path

    def test_history_dir_kwarg(self, tmp_path):
        h = PatchHistory(history_dir=str(tmp_path))
        assert h.history_file == str(
            tmp_path / "patch_history.json"
        )

    def test_filename_kwarg(self, tmp_path):
        h = PatchHistory(
            history_dir=str(tmp_path),
            filename="custom.json",
        )
        assert h.history_file == str(tmp_path / "custom.json")

    def test_creates_parent_dir(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "hist.json"
        h = PatchHistory(history_file=str(deep))
        assert os.path.isdir(os.path.dirname(h.history_file))

    def test_positional_path(self, tmp_path):
        path = str(tmp_path / "pos.json")
        h = PatchHistory(path)
        assert h.history_file == path


# ============================================================
# SCHEMA CONSISTENCY — metrics vs history
# ============================================================
class TestSchemaConsistency:
    def test_both_have_trace_id_field(self, history, metrics):
        history.add_record("/a.apk", "m", True, trace_id="x")
        metrics.record(PatchMetrics(
            apk_name="a.apk", mode="m", success=True,
            trace_id="x",
        ))
        h_entry = history.get_history()[0]
        m_entry = metrics.get_all()[0]
        assert "trace_id" in h_entry
        assert "trace_id" in m_entry

    def test_both_have_timestamp(self, history, metrics):
        history.add_record("/a.apk", "m", True)
        metrics.record(PatchMetrics(
            apk_name="a.apk", mode="m", success=True,
        ))
        assert isinstance(
            history.get_history()[0]["timestamp"], (int, float),
        )
        assert isinstance(
            metrics.get_all()[0]["timestamp"], (int, float),
        )

    def test_patchmetrics_dataclass_has_trace_id(self):
        m = PatchMetrics()
        assert hasattr(m, "trace_id")
        assert m.trace_id == ""