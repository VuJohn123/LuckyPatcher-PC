"""Tự động sao lưu APK khi phát hiện event apk.detected."""
from __future__ import annotations

import logging
import os
import shutil

from core.event_bus import event_bus

logger = logging.getLogger(__name__)


class OneClickBackupPipeline:
    def __init__(self, backup_dir: str | None = None, log_callback=print):
        if backup_dir is None:
            backup_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "workspace", "backups",
            )
        self.backup_dir = backup_dir
        os.makedirs(self.backup_dir, exist_ok=True)
        self.log = log_callback
        event_bus.subscribe("apk.detected", self._on_apk)

    def _on_apk(self, data: dict) -> None:
        apk_path = (data or {}).get("path")
        if not apk_path or not os.path.exists(apk_path):
            return
        try:
            dest = os.path.join(self.backup_dir, os.path.basename(apk_path))
            if not os.path.exists(dest):
                shutil.copy2(apk_path, dest)
                self.log(f"[✔] [Backup] {dest}")
        except OSError as e:
            logger.warning("Backup failed: %s", e)