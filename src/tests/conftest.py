"""
Pytest fixtures chung.

v2:
  - sys.path setup cho src/ (import core/scanner/patcher).
  - metrics isolation (LP_METRICS_FILE env) — tránh test pollute workspace.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


# ============================================================
# SYS.PATH SETUP (BẮT BUỘC — trước mọi import từ src/*)
# ============================================================
_SRC_DIR = str(Path(__file__).resolve().parent.parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


# ============================================================
# METRICS ISOLATION FIXTURE
# ============================================================
@pytest.fixture(autouse=True)
def _isolate_metrics(tmp_path, monkeypatch):
    """
    Mỗi test dùng metrics file riêng → không pollute workspace/metrics.json.
    """
    metrics_file = tmp_path / "_metrics.json"
    monkeypatch.setenv("LP_METRICS_FILE", str(metrics_file))
    # Reset singleton
    try:
        import core.metrics as _m
        _m._collector = None
    except Exception:
        pass
    yield
    try:
        if metrics_file.exists():
            os.remove(str(metrics_file))
    except OSError:
        pass