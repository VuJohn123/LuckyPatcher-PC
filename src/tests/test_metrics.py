"""Test core/metrics.py."""
import json
import os

import pytest

from core.metrics import (
    MetricsCollector,
    PatchMetrics,
    get_metrics,
)


# ============================================================
# PatchMetrics dataclass
# ============================================================
def test_patch_metrics_defaults():
    m = PatchMetrics(
        apk_name="test.apk", mode="license",
        success=True, duration_sec=1.5,
    )
    assert m.patches_applied == 0
    assert m.error == ""
    assert m.timestamp > 0


def test_patch_metrics_explicit():
    m = PatchMetrics(
        apk_name="x.apk", mode="ads",
        success=False, duration_sec=2.0,
        patches_applied=5, error="boom",
    )
    assert m.patches_applied == 5
    assert m.error == "boom"


# ============================================================
# Record / load
# ============================================================
def test_record_single(tmp_path):
    c = MetricsCollector(str(tmp_path))
    c.record(PatchMetrics(
        apk_name="a.apk", mode="license",
        success=True, duration_sec=1.0,
    ))
    records = c._load()
    assert len(records) == 1
    assert records[0]["apk_name"] == "a.apk"


def test_record_multiple(tmp_path):
    c = MetricsCollector(str(tmp_path))
    for i in range(3):
        c.record(PatchMetrics(
            apk_name=f"t{i}.apk", mode="m",
            success=True, duration_sec=1.0,
        ))
    assert len(c._load()) == 3


def test_record_caps_at_max(tmp_path):
    c = MetricsCollector(str(tmp_path))
    c.MAX_RECORDS = 5
    for i in range(10):
        c.record(PatchMetrics(
            apk_name=f"t{i}.apk", mode="m",
            success=True, duration_sec=1.0,
        ))
    records = c._load()
    assert len(records) == 5
    assert records[-1]["apk_name"] == "t9.apk"


# ============================================================
# Load robustness
# ============================================================
def test_load_missing_file(tmp_path):
    c = MetricsCollector(str(tmp_path))
    assert c._load() == []


def test_load_corrupted_json(tmp_path):
    c = MetricsCollector(str(tmp_path))
    with open(c.metrics_file, "w") as f:
        f.write("not json {{{")
    assert c._load() == []


def test_load_non_list(tmp_path):
    c = MetricsCollector(str(tmp_path))
    with open(c.metrics_file, "w") as f:
        json.dump({"foo": "bar"}, f)
    assert c._load() == []


# ============================================================
# get_summary
# ============================================================
def test_summary_empty(tmp_path):
    c = MetricsCollector(str(tmp_path))
    s = c.get_summary()
    assert s["total"] == 0
    assert s["success_rate"] == 0.0
    assert s["avg_duration"] == 0.0


def test_summary_success_rate(tmp_path):
    c = MetricsCollector(str(tmp_path))
    c.record(PatchMetrics(
        apk_name="a.apk", mode="license",
        success=True, duration_sec=2.0,
    ))
    c.record(PatchMetrics(
        apk_name="b.apk", mode="license",
        success=False, duration_sec=4.0, error="fail",
    ))
    s = c.get_summary()
    assert s["total"] == 2
    assert s["success_rate"] == 0.5
    assert s["avg_duration"] == 3.0


def test_summary_by_mode(tmp_path):
    c = MetricsCollector(str(tmp_path))
    for mode in ("license", "license", "ads"):
        c.record(PatchMetrics(
            apk_name="x.apk", mode=mode,
            success=True, duration_sec=1.0,
        ))
    s = c.get_summary()
    assert s["by_mode"]["license"]["count"] == 2
    assert s["by_mode"]["ads"]["count"] == 1


def test_summary_recent_errors(tmp_path):
    c = MetricsCollector(str(tmp_path))
    c.record(PatchMetrics(
        apk_name="fail.apk", mode="m",
        success=False, duration_sec=1.0, error="boom",
    ))
    s = c.get_summary()
    assert len(s["recent_errors"]) == 1
    assert "boom" in s["recent_errors"][0]["error"]


# ============================================================
# Clear
# ============================================================
def test_clear(tmp_path):
    c = MetricsCollector(str(tmp_path))
    c.record(PatchMetrics(
        apk_name="a.apk", mode="m", success=True, duration_sec=1.0,
    ))
    assert len(c._load()) == 1
    c.clear()
    assert c._load() == []


def test_clear_nonexistent(tmp_path):
    c = MetricsCollector(str(tmp_path))
    c.clear()  # Không crash


# ============================================================
# Singleton
# ============================================================
def test_get_metrics_returns_instance():
    m = get_metrics()
    assert isinstance(m, MetricsCollector)


def test_get_metrics_singleton():
    assert get_metrics() is get_metrics()