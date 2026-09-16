"""Hàng đợi xử lý APK hàng loạt — chạy tuần tự nền."""
from __future__ import annotations

import logging
import threading
from queue import Queue

logger = logging.getLogger(__name__)


class BatchQueue:
    def __init__(self, pipeline_callback, log_callback=print):
        self.cb = pipeline_callback
        self.log = log_callback
        self.queue: Queue = Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.progress_cb = None

    def add(self, apk_path: str, mode: str = "all") -> None:
        self.queue.put((apk_path, mode))
        self.log(f"[+] [Batch] Queued: {apk_path}")

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        total = self.queue.qsize()
        done = 0
        while not self._stop.is_set():
            try:
                apk, mode = self.queue.get(timeout=1)
            except Exception:
                if self.queue.empty():
                    break
                continue
            self.log(f"[*] [Batch] Processing {done + 1}/{total}: {apk}")
            if self.progress_cb:
                try:
                    self.progress_cb(done, total, apk)
                except Exception:
                    pass
            try:
                self.cb(apk, mode)
            except Exception as e:
                logger.warning("Batch item failed %s: %s", apk, e)
            done += 1
            self.queue.task_done()
        self.log("[*] [Batch] Queue finished")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)