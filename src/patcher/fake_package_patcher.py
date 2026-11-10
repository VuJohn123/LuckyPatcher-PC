"""Fake package patcher — change package id in AndroidManifest + smali refs."""
from __future__ import annotations

import logging
import os
import re

from patcher.base import BasePatcher

logger = logging.getLogger(__name__)
_PKG_RE = re.compile(r'package="([^"]+)"')

class FakePackagePatcher(BasePatcher):
    def __init__(self, decompiled_path, log_callback=print, file_cache=None, *, new_package: str | None = None):
        super().__init__(decompiled_path, log_callback, file_cache)
        import os as _o
        self.new_package = new_package or _o.environ.get("LP_FAKE_PKG") or "fake.lp.pkg"

    def patch(self) -> int:
        manifest = os.path.join(self.decompiled_path, "AndroidManifest.xml")
        try:
            with open(manifest, encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            self._log_traced(f"[!] Manifest read fail: {e}"); return 0
        m = _PKG_RE.search(content)
        if not m:
            self._log_traced("[!] No package= in manifest"); return 0
        old = m.group(1)
        if old == self.new_package:
            self._log_traced("[i] Package already fake"); return 0
        new = _PKG_RE.sub(f'package="{self.new_package}"', content, count=1)
        try:
            with open(manifest, "w", encoding="utf-8") as f:
                f.write(new)
        except OSError as e:
            self._log_traced(f"[!] Manifest write fail: {e}"); return 0
        self._log_traced(f"[✔] Package {old} → {self.new_package}")
        return 1
