"""
Patch history — lưu lịch sử patch vào `workspace/patch_history.json`.

Schema 1 entry:
    {
        timestamp, apk, mode, success,
        output, patches: [...], trace_id,
    }

Atomic writes để tránh corrupt khi crash giữa write.

Backward compat: constructor chấp nhận nhiều dạng call:
    PatchHistory()
    PatchHistory(path)
    PatchHistory(history_file=path)
    PatchHistory(history_dir=dir)
    PatchHistory(filename="custom.json")
    PatchHistory(file=path)          # legacy alias
    PatchHistory(path=path)          # legacy alias
    PatchHistory(storage_file=path)  # legacy alias
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_ENTRIES = 100
_DEFAULT_FILENAME = "patch_history.json"


class PatchHistory:
    def __init__(
        self,
        history_file: str | Path | None = None,
        history_dir: str | Path | None = None,
        filename: str = _DEFAULT_FILENAME,
        **kwargs,
    ):
        # ---- Legacy kwarg aliases ----
        if history_file is None:
            for alias in ("file", "path", "storage_file", "patch_file"):
                if alias in kwargs and kwargs[alias] is not None:
                    history_file = kwargs[alias]
                    break

        # ---- history_dir → history_file ----
        if history_file is None and history_dir is not None:
            history_file = str(Path(history_dir) / filename)

        # ---- Default ----
        if history_file is None:
            base = Path(__file__).resolve().parent.parent.parent
            history_file = str(base / "workspace" / filename)

        self.history_file = str(history_file)
        try:
            Path(self.history_file).parent.mkdir(
                parents=True, exist_ok=True,
            )
        except OSError as e:
            logger.warning("PatchHistory mkdir failed: %s", e)
        self._lock = threading.Lock()

    # ---------- IO ----------
    def _load(self) -> list[dict]:
        if not os.path.exists(self.history_file):
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return []
            return data
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("History load failed: %s", e)
            return []

    def _save_atomic(self, data: list[dict]) -> None:
        try:
            fd, tmp = tempfile.mkstemp(
                dir=os.path.dirname(self.history_file), suffix=".tmp",
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.history_file)
        except OSError as e:
            logger.warning("History save failed: %s", e)

    # ---------- PUBLIC ----------
    def add_record(
        self,
        apk_path: str,
        mode: str,
        success: bool,
        output_path: str = "",
        patches: list[str] | None = None,
        trace_id: str = "",
    ) -> None:
        record = {
            "timestamp": time.time(),
            "apk": apk_path,
            "mode": mode,
            "success": success,
            "output": output_path,
            "patches": list(patches) if patches else [],
            "trace_id": trace_id,
        }
        with self._lock:
            data = self._load()
            data.append(record)
            if len(data) > _MAX_ENTRIES:
                data = data[-_MAX_ENTRIES:]
            self._save_atomic(data)

    def get_history(self) -> list[dict]:
        """Return newest-first."""
        with self._lock:
            data = self._load()
        return list(reversed(data))

    def clear(self) -> None:
        with self._lock:
            self._save_atomic([])