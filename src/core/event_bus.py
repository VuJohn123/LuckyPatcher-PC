"""Event bus — pub/sub đơn giản, thread-safe."""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._listeners: dict[str, list[Callable]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, event_type: str, callback: Callable) -> None:
        with self._lock:
            self._listeners[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        with self._lock:
            if callback in self._listeners[event_type]:
                self._listeners[event_type].remove(callback)

    def emit(self, event_type: str, data: Any = None) -> None:
        with self._lock:
            callbacks = list(self._listeners.get(event_type, []))
        for cb in callbacks:
            try:
                cb(data)
            except Exception as e:
                logger.exception("Event %s handler failed: %s", event_type, e)


event_bus = EventBus()