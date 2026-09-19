"""
Metrics — theo dõi pipeline runs + stage timings.

Storage: `workspace/metrics.json` (hoặc `LP_METRICS_FILE` env override).
Atomic writes để tránh corrupt khi crash giữa write.

Schema:
    PatchMetrics(
        apk_name, mode, success, duration_sec,
        patches_applied, error, stage, timestamp, trace_id,
    )
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_ENTRIES = 500


# ============================================================
# DATA MODEL
# ============================================================
@dataclass
class PatchMetrics:
    apk_name: str = ""
    mode: str = ""
    success: bool = False
    duration_sec: float = 0.0
    patches_applied: int = 0
    error: str = ""
    stage: str = "pipeline"
    timestamp: float = field(default_factory=time.time)
    trace_id: str = ""


# ============================================================
# MANAGER
# ============================================================
class _MetricsManager:
    def __init__(self, metrics_file: str | None = None):
        if metrics_file is None:
            metrics_file = os.environ.get("LP_METRICS_FILE", "").strip()
        if not metrics_file:
            base = Path(__file__).resolve().parent.parent.parent
            metrics_file = str(base / "workspace" / "metrics.json")
        self.metrics_file = metrics_file
        Path(self.metrics_file).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ---------- IO ----------
    def _load(self) -> list[dict]:
        if not os.path.exists(self.metrics_file):
            return []
        try:
            with open(self.metrics_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return []
            return data
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Metrics load failed: %s", e)
            return []

    def _save_atomic(self, data: list[dict]) -> None:
        try:
            fd, tmp = tempfile.mkstemp(
                dir=os.path.dirname(self.metrics_file), suffix=".tmp",
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.metrics_file)
        except OSError as e:
            logger.warning("Metrics save failed: %s", e)

    # ---------- PUBLIC ----------
    def record(self, metrics: PatchMetrics) -> None:
        with self._lock:
            data = self._load()
            data.append(asdict(metrics))
            if len(data) > _MAX_ENTRIES:
                data = data[-_MAX_ENTRIES:]
            self._save_atomic(data)

    def record_stage(
        self,
        apk_name: str,
        mode: str,
        stage: str,
        duration_sec: float,
        success: bool = True,
        error: str = "",
        trace_id: str = "",
    ) -> None:
        """Convenience — record 1 stage timing."""
        self.record(PatchMetrics(
            apk_name=apk_name,
            mode=mode,
            stage=stage,
            duration_sec=duration_sec,
            success=success,
            error=error,
            trace_id=trace_id,
        ))

    def get_all(self) -> list[dict]:
        with self._lock:
            return self._load()

    def get_summary(self) -> dict:
        data = self.get_all()
        if not data:
            return {
                "total": 0,
                "success_rate": 0.0,
                "by_mode": {},
                "by_stage": {},
                "recent_errors": [],
            }

        pipeline_runs = [d for d in data if d.get("stage") == "pipeline"]
        total = len(pipeline_runs)
        successes = sum(1 for d in pipeline_runs if d.get("success"))
        success_rate = (successes / total) if total else 0.0

        by_mode: dict[str, dict] = {}
        for d in pipeline_runs:
            m = d.get("mode", "?")
            entry = by_mode.setdefault(m, {"count": 0, "success": 0})
            entry["count"] += 1
            if d.get("success"):
                entry["success"] += 1

        by_stage: dict[str, dict] = {}
        for d in data:
            s = d.get("stage", "?")
            if s == "pipeline":
                continue
            entry = by_stage.setdefault(s, {"count": 0, "total_sec": 0.0})
            entry["count"] += 1
            entry["total_sec"] += float(d.get("duration_sec", 0.0))

        for s, entry in by_stage.items():
            entry["avg_sec"] = (
                entry["total_sec"] / entry["count"]
                if entry["count"] else 0.0
            )

        recent_errors = [
            {
                "apk": d.get("apk_name", ""),
                "mode": d.get("mode", ""),
                "stage": d.get("stage", ""),
                "error": d.get("error", ""),
                "trace_id": d.get("trace_id", ""),
            }
            for d in data
            if not d.get("success") and d.get("error")
        ][-10:]

        return {
            "total": total,
            "success_rate": round(success_rate, 4),
            "by_mode": by_mode,
            "by_stage": by_stage,
            "recent_errors": recent_errors,
        }

    def clear(self) -> None:
        with self._lock:
            if os.path.exists(self.metrics_file):
                try:
                    os.remove(self.metrics_file)
                except OSError:
                    pass


# ============================================================
# SINGLETON
# ============================================================
_default: _MetricsManager | None = None
_singleton_lock = threading.Lock()


def get_metrics() -> _MetricsManager:
    global _default
    if _default is None:
        with _singleton_lock:
            if _default is None:
                _default = _MetricsManager()
    return _default


def reset_metrics(metrics_file: str | None = None) -> None:
    """Test helper: reset singleton với path mới."""
    global _default
    with _singleton_lock:
        _default = _MetricsManager(metrics_file)