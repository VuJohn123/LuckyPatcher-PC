"""Test metrics collector."""
import json
import time

from core.metrics import MetricsCollector, PatchMetrics, get_metrics


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


def test_patch_metrics_explicit_values():
    m = PatchMetrics(
        apk_name="app.apk", mode="ads",
        success=False, duration_sec=3.2,
        patches_applied=5, error="test error",
    )
    assert m.apk_name == "app.apk"
    assert m.patches_applied == 5
    assert m.error == "test error"


# ============================================================
# MetricsCollector — record
# ============================================================
def test_collector_creates_dir(tmp_path):
    subdir = tmp_path / "new_metrics"
    c = MetricsCollector(str(subdir))
    assert subdir.exists()
    assert c.metrics_file.endswith("metrics.json")


def test_collector_record_single(tmp_path):
    c = MetricsCollector(str(tmp_path))
    c.record(PatchMetrics(
        apk_name="test.apk", mode="license",
        success=True, duration_sec=1.5,
    ))
    records = c._load()
    assert len(records) == 1
    assert records[0]["apk_name"] == "test.apk"
    assert records[0]["success"] is True


def test_collector_appends(tmp_path):
    c = MetricsCollector(str(tmp_path))
    for i in range(3):
        c.record(PatchMetrics(
            apk_name=f"t{i}.apk", mode="m",
            success=True, duration_sec=1.0,
        ))
    assert len(c._load()) == 3


def test_collector_caps_at_max(tmp_path):
    c = MetricsCollector(str(tmp_path))
    c.MAX_RECORDS = 5
    for i in range(10):
        c.record(PatchMetrics(
            apk_name=f"t{i}.apk", mode="m",
            success=True, duration_sec=1.0,
        ))
    records = c._load()
    assert len(records) == 5
    # Chỉ giữ 5 record mới nhất (t5..t9)
    assert records[-1]["apk_name"] == "t9.apk"


# ============================================================
# MetricsCollector — load robustness
# ============================================================
def test_collector_load_missing_file(tmp_path):
    c = MetricsCollector(str(tmp_path))
    assert c._load() == []


def test_collector_load_corrupted_json(tmp_path):
    c = MetricsCollector(str(tmp_path))
    with open(c.metrics_file, "w") as f:
        f.write("this is not json {{{")
    assert c._load() == []


def test_collector_load_non_list(tmp_path):
    c = MetricsCollector(str(tmp_path))
    with open(c.metrics_file, "w") as f:
        json.dump({"foo": "bar"}, f)
    assert c._load() == []


# ============================================================
# MetricsCollector — get_summary
# ============================================================
def test_get_summary_empty(tmp_path):
    c = MetricsCollector(str(tmp_path))
    s = c.get_summary()
    assert s["total"] == 0
    assert s["success_rate"] == 0.0
    assert s["avg_duration"] == 0.0
    assert s["by_mode"] == {}
    assert s["recent_errors"] == []


def test_get_summary_with_success_and_failure(tmp_path):
    c = MetricsCollector(str(tmp_path))
    c.record(PatchMetrics(
        apk_name="a.apk", mode="license",
        success=True, duration_sec=2.0,
    ))
    c.record(PatchMetrics(
        apk_name="b.apk", mode="license",
        success=False, duration_sec=4.0, error="failed badly",
    ))
    s = c.get_summary()
    assert s["total"] == 2
    assert s["success_rate"] == 0.5
    assert s["avg_duration"] == 3.0
    assert "license" in s["by_mode"]
    assert s["by_mode"]["license"]["count"] == 2
    assert s["by_mode"]["license"]["success"] == 1


def test_get_summary_by_mode_multiple(tmp_path):
    c = MetricsCollector(str(tmp_path))
    for mode in ("license", "license", "ads"):
        c.record(PatchMetrics(
            apk_name="x.apk", mode=mode,
            success=True, duration_sec=1.0,
        ))
    s = c.get_summary()
    assert s["by_mode"]["license"]["count"] == 2
    assert s["by_mode"]["ads"]["count"] == 1


def test_get_summary_recent_errors(tmp_path):
    c = MetricsCollector(str(tmp_path))
    c.record(PatchMetrics(
        apk_name="ok.apk", mode="m",
        success=True, duration_sec=1.0,
    ))
    c.record(PatchMetrics(
        apk_name="fail.apk", mode="m",
        success=False, duration_sec=1.0, error="boom",
    ))
    s = c.get_summary()
    assert len(s["recent_errors"]) == 1
    assert s["recent_errors"][0]["apk"] == "fail.apk"
    assert "boom" in s["recent_errors"][0]["error"]


# ============================================================
# MetricsCollector — clear
# ============================================================
def test_collector_clear(tmp_path):
    c = MetricsCollector(str(tmp_path))
    c.record(PatchMetrics(
        apk_name="a.apk", mode="m", success=True, duration_sec=1.0,
    ))
    assert len(c._load()) == 1
    c.clear()
    assert c._load() == []


def test_collector_clear_nonexistent(tmp_path):
    """Clear khi chưa có file → không crash."""
    c = MetricsCollector(str(tmp_path))
    c.clear()  # Không raise


# ============================================================
# Singleton
# ============================================================
def test_get_metrics_returns_instance():
    m = get_metrics()
    assert isinstance(m, MetricsCollector)


def test_get_metrics_singleton():
    m1 = get_metrics()
    m2 = get_metrics()
    assert m1 is m2