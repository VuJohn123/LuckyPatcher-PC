"""
Qt signals cho pipeline — safe cross-thread update.

Fallback (không có PyQt6): thread-safe emit với lock.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


# ============================================================
# FALLBACK (module-level — testable)
# ============================================================
class _FallbackSignal:
    """Thread-safe signal — connect/disconnect/emit."""
    __slots__ = ("_cbs", "_lock", "name")

    def __init__(self, name: str = ""):
        self.name = name
        self._cbs: list = []
        self._lock = threading.RLock()

    def connect(self, callback) -> None:
        if callback is None:
            return
        with self._lock:
            self._cbs.append(callback)

    def disconnect(self, callback=None) -> None:
        with self._lock:
            if callback is None:
                self._cbs.clear()
            else:
                try:
                    self._cbs.remove(callback)
                except ValueError:
                    pass

    def emit(self, *args) -> None:
        with self._lock:
            cbs = list(self._cbs)
        for cb in cbs:
            try:
                cb(*args)
            except Exception as e:
                logger.debug(
                    "Signal %s emit failed: %s", self.name, e
                )

    def __len__(self) -> int:
        with self._lock:
            return len(self._cbs)


# ============================================================
# QT OR FALLBACK
# ============================================================
try:
    from PyQt6.QtCore import QObject, pyqtSignal

    class PipelineSignals(QObject):
        progress = pyqtSignal(int, int)
        step = pyqtSignal(str, int)
        status = pyqtSignal(str)
        patch_complete = pyqtSignal(str, str)
        finished = pyqtSignal(bool, str)
        safety_prompt = pyqtSignal(str, dict, int, object)

    _HAS_QT = True

except ImportError:
    _HAS_QT = False

    class PipelineSignals:
        """Fallback cho môi trường không có PyQt6."""

        def __init__(self):
            self.progress = _FallbackSignal("progress")
            self.step = _FallbackSignal("step")
            self.status = _FallbackSignal("status")
            self.patch_complete = _FallbackSignal("patch_complete")
            self.finished = _FallbackSignal("finished")
            self.safety_prompt = _FallbackSignal("safety_prompt")


__all__ = ["PipelineSignals", "_FallbackSignal", "_HAS_QT"]