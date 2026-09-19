"""Test core/metrics.py — recording + summary + trace_id."""
from __future__ import annotations

import json
import os

import pytest

from core.metrics import (
    PatchMetrics,
    _MetricsManager,
    get_metrics,
    reset_metrics,
)


# ============================================================
# Fixture: reset singleton per test
# ============================================================
@pytest.fixture
def mgr(tmp_path):
    m = _MetricsManager(str(tmp_path / "m.json"))
    return m


# ============================================================
# PatchMetrics dataclass
# ============================================================
class TestPatchMetrics:
    def test_defaults(self):
        m = PatchMetrics()
        assert m.apk_name == ""
        assert m.success is False
        assert m.stage == "pipeline"
        assert m.trace_id == ""
        assert m.timestamp > 0

    def test_explicit_fields(self):
        m = PatchMetrics(
            apk_name="a.apk", mode="license", success=True,
            duration_sec=1.5, patches_applied=3,
        )
        assert m.apk_name == "a.apk"
        assert m.patches_applied == 3

    def test_explicit_trace_id(self):
        m = PatchMetrics(trace_id="abcd1234")
        assert m.trace_id == "abcd1234"


# ============================================================
# Recording
# ============================================================
class TestRecord:
    def test_record_single(self, mgr):
        mgr.record(PatchMetrics(apk_name="a.apk", success=True))
        data = mgr.get_all()
        assert len(data) == 1
        assert data[0]["apk_name"] == "a.apk"

    def test_record_multiple(self, mgr):
        for i in range(3):
            mgr.record(PatchMetrics(apk_name=f"a{i}.apk"))
        assert len(mgr.get_all()) == 3

    def test_record_caps_at_max(self, mgr):
        from core.metrics import _MAX_ENTRIES
        for i in range(_MAX_ENTRIES + 20):
            mgr.record(PatchMetrics(apk_name=f"a{i}.apk"))
        assert len(mgr.get_all()) == _MAX_ENTRIES

    def test_record_stage_convenience(self, mgr):
        mgr.record_stage(
            apk_name="x.apk", mode="license", stage="patch",
            duration_sec=2.5, success=True,
        )
        data = mgr.get_all()
        assert data[0]["stage"] == "patch"
        assert data[0]["duration_sec"] == 2.5


# ============================================================
# Trace ID integration
# ============================================================
class TestTraceId:
    def test_record_persists_trace_id(self, mgr):
        mgr.record(PatchMetrics(
            apk_name="a.apk", success=True, trace_id="abcd1234",
        ))
        data = mgr.get_all()
        assert data[0]["trace_id"] == "abcd1234"

    def test_record_stage_accepts_trace_id(self, mgr):
        mgr.record_stage(
            apk_name="x.apk", mode="test", stage="patch",
            duration_sec=1.0, trace_id="xyz98765",
        )
        data = mgr.get_all()
        assert data[0]["trace_id"] == "xyz98765"

    def test_summary_recent_errors_include_trace(self, mgr):
        mgr.record(PatchMetrics(
            apk_name="a.apk", success=False, error="boom",
            stage="pipeline", trace_id="errtrace",
        ))
        summary = mgr.get_summary()
        assert len(summary["recent_errors"]) == 1
        assert summary["recent_errors"][0]["trace_id"] == "errtrace"

    def test_backward_compat_empty_trace(self, mgr):
        """Không có trace_id → vẫn write với "" default."""
        mgr.record(PatchMetrics(apk_name="a.apk"))
        data = mgr.get_all()
        assert data[0]["trace_id"] == ""


# ============================================================
# IO — load edge cases
# ============================================================
class TestLoad:
    def test_load_missing_file(self, tmp_path):
        m = _MetricsManager(str(tmp_path / "missing.json"))
        assert m.get_all() == []

    def test_load_corrupted_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{invalid json")
        m = _MetricsManager(str(p))
        assert m.get_all() == []

    def test_load_non_list(self, tmp_path):
        p = tmp_path / "dict.json"
        p.write_text('{"not": "a list"}')
        m = _MetricsManager(str(p))
        assert m.get_all() == []

    def test_load_valid(self, tmp_path):
        p = tmp_path / "ok.json"
        p.write_text(json.dumps([
            {"apk_name": "x", "stage": "pipeline", "success": True},
        ]))
        m = _MetricsManager(str(p))
        assert len(m.get_all()) == 1


# ============================================================
# Summary
# ============================================================
class TestSummary:
    def test_summary_empty(self, mgr):
        s = mgr.get_summary()
        assert s["total"] == 0
        assert s["success_rate"] == 0.0

    def test_summary_success_rate(self, mgr):
        for success in (True, True, False, True):
            mgr.record(PatchMetrics(
                stage="pipeline", success=success,
            ))
        s = mgr.get_summary()
        assert s["total"] == 4
        assert s["success_rate"] == 0.75

    def test_summary_by_mode(self, mgr):
        mgr.record(PatchMetrics(
            mode="license", stage="pipeline", success=True,
        ))
        mgr.record(PatchMetrics(
            mode="license", stage="pipeline", success=False,
        ))
        mgr.record(PatchMetrics(
            mode="iap", stage="pipeline", success=True,
        ))
        s = mgr.get_summary()
        assert s["by_mode"]["license"]["count"] == 2
        assert s["by_mode"]["license"]["success"] == 1
        assert s["by_mode"]["iap"]["count"] == 1

    def test_summary_by_stage_avg(self, mgr):
        mgr.record(PatchMetrics(
            stage="patch", duration_sec=2.0, success=True,
        ))
        mgr.record(PatchMetrics(
            stage="patch", duration_sec=4.0, success=True,
        ))
        s = mgr.get_summary()
        assert s["by_stage"]["patch"]["count"] == 2
        assert s["by_stage"]["patch"]["avg_sec"] == 3.0

    def test_summary_recent_errors(self, mgr):
        for i in range(3):
            mgr.record(PatchMetrics(
                stage="pipeline", success=False, error=f"err{i}",
            ))
        s = mgr.get_summary()
        assert len(s["recent_errors"]) == 3
        assert s["recent_errors"][0]["error"] == "err0"


# ============================================================
# Clear
# ============================================================
class TestClear:
    def test_clear(self, mgr):
        mgr.record(PatchMetrics(apk_name="a.apk"))
        mgr.clear()
        assert mgr.get_all() == []

    def test_clear_nonexistent(self, tmp_path):
        m = _MetricsManager(str(tmp_path / "missing.json"))
        m.clear()  # should not raise


# ============================================================
# Singleton
# ============================================================
class TestSingleton:
    def test_get_metrics_returns_instance(self):
        m = get_metrics()
        assert isinstance(m, _MetricsManager)

    def test_get_metrics_singleton(self):
        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2

    def test_reset_metrics(self, tmp_path):
        reset_metrics(str(tmp_path / "new.json"))
        m = get_metrics()
        assert "new.json" in m.metrics_file
        # Cleanup: reset về default
        reset_metrics()