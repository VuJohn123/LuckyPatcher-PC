"""Quản lý emulator Android — start, install, launch."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time

logger = logging.getLogger(__name__)


class EmulatorManager:
    def __init__(self, avd_name: str = "LP_PC_Emulator", log_callback=print):
        self.avd_name = avd_name
        self.log = log_callback
        self.adb = shutil.which("adb") or "adb"
        self.emulator = self._find_emulator()

    def _find_emulator(self) -> str | None:
        if shutil.which("emulator"):
            return "emulator"
        home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
        if home:
            exe = "emulator.exe" if os.name == "nt" else "emulator"
            path = os.path.join(home, "emulator", exe)
            if os.path.exists(path):
                return path
        return None

    def is_running(self) -> bool:
        try:
            proc = subprocess.run([self.adb, "devices"],
                                  capture_output=True, text=True, timeout=5)
            return "emulator" in proc.stdout
        except subprocess.SubprocessError:
            return False

    def start(self, timeout: int = 120) -> bool:
        if self.is_running():
            self.log("[i] Emulator đã chạy")
            return True
        if not self.emulator:
            self.log("[!] Không tìm thấy emulator binary")
            return False

        cmd = [self.emulator, "-avd", self.avd_name,
               "-no-snapshot", "-no-boot-anim"]
        try:
            subprocess.Popen(cmd,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except OSError as e:
            self.log(f"[!] Không khởi động được: {e}")
            return False

        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if self.is_running():
                return True
            time.sleep(3)
        return False

    def install_apk(self, apk_path: str) -> bool:
        if not self.is_running():
            self.log("[!] Emulator chưa chạy")
            return False
        try:
            proc = subprocess.run(
                [self.adb, "-e", "install", "-r", apk_path],
                capture_output=True, text=True, timeout=120,
            )
            return "Success" in (proc.stdout or "")
        except subprocess.SubprocessError:
            return False

    def launch(self, package: str) -> bool:
        try:
            subprocess.run(
                [self.adb, "-e", "shell", "monkey",
                 "-p", package, "-c",
                 "android.intent.category.LAUNCHER", "1"],
                capture_output=True, timeout=15,
            )
            return True
        except subprocess.SubprocessError:
            return False