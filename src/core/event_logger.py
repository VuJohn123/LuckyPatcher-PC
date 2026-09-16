"""
Event logger runtime — dùng cho pipeline ghi log có cấu trúc.
Khác với patcher/event_logger.py (inject smali vào APK).
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)


class EventLogger:
    """
    Runtime event logger với counters + ring buffer.
    Thread-safe, dùng cho pipeline monitoring.
    """
    MAX_BUFFER = 1000

    def __init__(self):
        self._lock = threading.RLock()
        self._events: list[dict] = []
        self._counters: dict[str, int] = defaultdict(int)

    def log(self, event_type: str, message: str, **kwargs: Any) -> None:
        with self._lock:
            self._counters[event_type] += 1
            record = {
                "type": event_type,
                "message": message,
                "count": self._counters[event_type],
                "extra": kwargs or {},
            }
            self._events.append(record)
            if len(self._events) > self.MAX_BUFFER:
                self._events = self._events[-self.MAX_BUFFER:]
        logger.debug("[%s] %s", event_type, message)

    def get_events(self, event_type: str | None = None) -> list[dict]:
        with self._lock:
            if event_type is None:
                return list(self._events)
            return [e for e in self._events if e["type"] == event_type]

    def get_counters(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._counters.clear()


# Singleton
event_logger = EventLogger()