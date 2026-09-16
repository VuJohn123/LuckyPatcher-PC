"""Metrics collection — track patch success rate, timing, errors."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PatchMetrics:
    """Metrics cho 1 lần patch."""
    apk_name: str
    mode: str
    success: bool
    duration_sec: float
    patches_applied: int = 0
    error: str = ""
    timestamp: float = field(default_factory=time.time)


class MetricsCollector:
    """
    Thu thập + persist metrics.
    Storage: workspace/metrics.json (append-only, cap 1000 records).
    """

    MAX_RECORDS = 1000
    _lock = threading.Lock()

    def __init__(self, metrics_dir: str | None = None):
        if metrics_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            metrics_dir = os.path.join(base, "workspace")
        self.metrics_dir = metrics_dir
        os.makedirs(self.metrics_dir, exist_ok=True)
        self.metrics_file = os.path.join(self.metrics_dir, "metrics.json")

    def record(self, m: PatchMetrics) -> None:
        """Append 1 record — atomic write."""
        with self._lock:
            records = self._load()
            records.append(asdict(m))
            if len(records) > self.MAX_RECORDS:
                records = records[-self.MAX_RECORDS:]

            tmp = self.metrics_file + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(records, f, indent=2)
                os.replace(tmp, self.metrics_file)
            except OSError as e:
                logger.warning("Metrics save failed: %s", e)
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass

    def _load(self) -> list[dict]:
        if not os.path.exists(self.metrics_file):
            return []
        try:
            with open(self.metrics_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def get_summary(self) -> dict:
        """Tổng hợp: success rate, avg duration, top modes, recent errors."""
        records = self._load()
        if not records:
            return {
                "total": 0,
                "success_rate": 0.0,
                "avg_duration": 0.0,
                "by_mode": {},
                "recent_errors": [],
            }

        total = len(records)
        successes = sum(1 for r in records if r.get("success"))
        durations = [r.get("duration_sec", 0) for r in records]

        by_mode: dict[str, dict] = defaultdict(
            lambda: {"count": 0, "success": 0, "avg_time": 0.0}
        )
        for r in records:
            mode = r.get("mode", "unknown")
            by_mode[mode]["count"] += 1
            if r.get("success"):
                by_mode[mode]["success"] += 1
            by_mode[mode]["avg_time"] += r.get("duration_sec", 0)

        for mode_data in by_mode.values():
            if mode_data["count"] > 0:
                mode_data["avg_time"] /= mode_data["count"]
                mode_data["success_rate"] = (
                    mode_data["success"] / mode_data["count"]
                )

        recent_errors = [
            {
                "apk": r.get("apk_name", "?"),
                "mode": r.get("mode", "?"),
                "error": r.get("error", "?")[:200],
                "when": r.get("timestamp", 0),
            }
            for r in records[-20:]
            if not r.get("success")
        ]

        return {
            "total": total,
            "success_rate": successes / total if total else 0.0,
            "avg_duration": sum(durations) / total if total else 0.0,
            "by_mode": dict(by_mode),
            "recent_errors": recent_errors,
        }

    def clear(self) -> None:
        with self._lock:
            try:
                os.remove(self.metrics_file)
            except OSError:
                pass


# Singleton
_collector: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector