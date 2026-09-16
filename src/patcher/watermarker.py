"""Thêm watermark vào APK — đánh dấu đã vá."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import time
import zipfile

logger = logging.getLogger(__name__)


class Watermarker:
    MARKER_FILE = "assets/lp_pc_suite_marker.json"

    @staticmethod
    def add_watermark(decompiled_path: str, patches_applied: list[str],
                      apk_path: str) -> None:
        marker_path = os.path.join(decompiled_path, Watermarker.MARKER_FILE)
        os.makedirs(os.path.dirname(marker_path), exist_ok=True)

        original_hash = ""
        try:
            hasher = hashlib.md5()
            with open(apk_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hasher.update(chunk)
            original_hash = hasher.hexdigest()
        except OSError as e:
            logger.warning("Không hash được APK: %s", e)

        marker = {
            "tool": "LP-PC Suite",
            "timestamp": time.time(),
            "original_hash": original_hash,
            "patches": patches_applied,
        }
        with open(marker_path, "w", encoding="utf-8") as f:
            json.dump(marker, f, indent=2)

    @staticmethod
    def check_watermark(apk_path: str) -> dict | None:
        try:
            with zipfile.ZipFile(apk_path, "r") as z:
                if Watermarker.MARKER_FILE in z.namelist():
                    data = z.read(Watermarker.MARKER_FILE)
                    return json.loads(data.decode("utf-8"))
        except (zipfile.BadZipFile, OSError, ValueError):
            pass
        return None

    @staticmethod
    def check_watermark_installed(package_name: str) -> dict | None:
        try:
            result = subprocess.run(
                ["adb", "shell", "run-as", package_name, "cat",
                 Watermarker.MARKER_FILE],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
        except (subprocess.SubprocessError, ValueError):
            pass
        return None