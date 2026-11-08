"""Install-dir metadata patcher — records custom install path in apk.yml."""
from __future__ import annotations
import logging, os
from patcher.base import BasePatcher
logger = logging.getLogger(__name__)

class InstallDirPatcher(BasePatcher):
    def __init__(self, decompiled_path, log_callback=print, file_cache=None, *, install_dir: str | None = None):
        super().__init__(decompiled_path, log_callback, file_cache)
        import os as _o
        self.install_dir = install_dir or _o.environ.get("LP_INSTALL_DIR") or "/data/local/tmp/lp"

    def patch(self) -> int:
        path = os.path.join(self.decompiled_path, "apk.yml")
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
        except OSError:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"install_dir: {self.install_dir}\n")
            except OSError as e:
                self._log_traced(f"[!] apk.yml write fail: {e}"); return 0
            self._log_traced(f"[✔] Install dir → {self.install_dir}")
            return 1
        if "install_dir:" in content:
            self._log_traced("[i] install_dir already set"); return 0
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"\ninstall_dir: {self.install_dir}\n")
        except OSError as e:
            self._log_traced(f"[!] apk.yml append fail: {e}"); return 0
        self._log_traced(f"[✔] Install dir → {self.install_dir}")
        return 1
