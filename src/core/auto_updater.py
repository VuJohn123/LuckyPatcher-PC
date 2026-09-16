"""
Auto-update watcher — theo dõi thư mục, tự động patch APK mới.
Chỉ áp dụng khi có lịch sử patch khớp package.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from core.patch_history import PatchHistory

logger = logging.getLogger(__name__)


class AutoUpdater:
    def __init__(self, watch_dir: str | None = None,
                 log_callback=print, pipeline_callback=None,
                 poll_interval: float = 5.0):
        self.watch_dir = Path(
            watch_dir or (Path.home() / "Downloads")
        )
        self.log = log_callback
        self.pipeline_cb = pipeline_callback
        self.interval = poll_interval

        self._known: set[str] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self._known = self._scan()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.log(f"[*] [AutoUpdater] Watching {self.watch_dir}")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _scan(self) -> set[str]:
        out = set()
        for ext in ("*.apk", "*.xapk"):
            for p in self.watch_dir.glob(ext):
                out.add(str(p))
        return out

    def _run(self) -> None:
        while not self._stop.is_set():
            current = self._scan()
            new_files = current - self._known
            for path in new_files:
                self._process(path)
            self._known = current
            self._stop.wait(self.interval)

    def _process(self, apk_path: str) -> None:
        self.log(f"[*] [AutoUpdater] New: {Path(apk_path).name}")
        if not self.pipeline_cb:
            return

        try:
            from androguard.core.apk import APK
            apk = APK(apk_path)
            package = apk.get_package()
        except Exception as e:
            logger.warning("Không đọc được package: %s", e)
            return

        history = PatchHistory().get_history()
        mode = None
        for record in history:
            if record.get("success") and package in str(record.get("apk", "")):
                mode = record.get("mode")
                break

        if not mode:
            self.log(f"[i] Không có lịch sử cho {package}, bỏ qua")
            return

        try:
            self.pipeline_cb(apk_path, mode)
        except Exception as e:
            logger.warning("AutoUpdater pipeline failed: %s", e)