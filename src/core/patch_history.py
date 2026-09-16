"""Lưu lịch sử patch — JSON file, thread-safe."""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()


class PatchHistory:
    def __init__(self, history_dir: str | None = None):
        if history_dir is None:
            history_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "workspace", "history",
            )
        self.history_dir = history_dir
        os.makedirs(self.history_dir, exist_ok=True)
        self.history_file = os.path.join(self.history_dir, "patch_history.json")
        self.max_entries = 500

    def _load(self) -> list[dict]:
        if not os.path.exists(self.history_file):
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("history load failed: %s", e)
            return []

    def _save_atomic(self, data: list[dict]) -> None:
        """Ghi atomic — tránh corrupt khi crash giữa chừng."""
        fd, tmp = tempfile.mkstemp(dir=self.history_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.history_file)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    def add_record(self, apk_path: str, mode: str, success: bool,
                   output_path: str, patches: list[str]) -> None:
        with _LOCK:
            history = self._load()
            record = {
                "apk": apk_path,
                "mode": mode,
                "success": success,
                "output": output_path,
                "patches": patches or [],
                "timestamp": time.time(),
            }
            history.insert(0, record)
            if len(history) > self.max_entries:
                history = history[: self.max_entries]
            try:
                self._save_atomic(history)
            except OSError as e:
                logger.error("history save failed: %s", e)

    def get_history(self) -> list[dict]:
        with _LOCK:
            return self._load()

    def clear(self) -> None:
        with _LOCK:
            try:
                self._save_atomic([])
            except OSError as e:
                logger.error("history clear failed: %s", e)