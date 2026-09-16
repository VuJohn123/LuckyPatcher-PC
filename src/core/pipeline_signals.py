"""Qt signals cho pipeline — safe cross-thread update."""
from __future__ import annotations

try:
    from PyQt6.QtCore import QObject, pyqtSignal

    class PipelineSignals(QObject):
        progress = pyqtSignal(int, int)          # (current, total)
        step = pyqtSignal(str, int)              # (step_name, overall_pct 0-100)
        status = pyqtSignal(str)
        patch_complete = pyqtSignal(str, str)
        finished = pyqtSignal(bool, str)

except ImportError:
    # Fallback CLI mode
    class PipelineSignals:
        class _Signal:
            def __init__(self): self._cbs = []
            def connect(self, cb): self._cbs.append(cb)
            def emit(self, *args):
                for cb in self._cbs:
                    try: cb(*args)
                    except Exception: pass

        def __init__(self):
            self.progress = self._Signal()
            self.step = self._Signal()
            self.status = self._Signal()
            self.patch_complete = self._Signal()
            self.finished = self._Signal()