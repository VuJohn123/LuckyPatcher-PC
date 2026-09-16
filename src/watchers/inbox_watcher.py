"""Watcher theo dõi thư mục inbox, emit event khi có APK mới."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from core.event_bus import event_bus

logger = logging.getLogger(__name__)


class InboxWatcher:
    def __init__(self, inbox_path: str | None = None,
                 poll_interval: float = 5.0, log_callback=print):
        self.inbox = Path(
            inbox_path or (Path.home() / "LP_Inbox")
        )
        self.interval = poll_interval
        self.log = log_callback
        self._known: set[str] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.inbox.mkdir(parents=True, exist_ok=True)
        self._known = self._scan()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.log(f"[*] [Inbox] Watching {self.inbox}")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _scan(self) -> set[str]:
        out = set()
        for ext in ("*.apk", "*.xapk"):
            for p in self.inbox.glob(ext):
                out.add(str(p))
        return out

    def _run(self) -> None:
        while not self._stop.is_set():
            current = self._scan()
            for new_file in current - self._known:
                self.log(f"[*] [Inbox] New: {Path(new_file).name}")
                try:
                    event_bus.emit("apk.detected", {"path": new_file})
                except Exception as e:
                    logger.warning("emit failed: %s", e)
            self._known = current
            self._stop.wait(self.interval)