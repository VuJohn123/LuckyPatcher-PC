"""License verification patcher — Auto + Reverse Auto modes."""
from __future__ import annotations

import logging
import os

from core.smali_utils import (
    REGEX_BOOLEAN_METHOD,
    REGEX_SERVERMANAGEDPOLICY_CONSTRUCTOR,
    get_all_smali_files,
)

logger = logging.getLogger(__name__)

LICENSE_KEYWORDS = {"allow", "dontAllow", "checkLicense", "isLicensed", "verifyLicense"}


class LicensePatcher:
    def __init__(self, decompiled_path: str, log_callback=print, file_cache=None):
        self.decompiled_path = decompiled_path
        self.log = log_callback
        self.file_cache = file_cache

    def _read(self, path: str) -> str:
        if self.file_cache:
            return self.file_cache.read(path)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def _write(self, path: str, content: str) -> None:
        if self.file_cache:
            self.file_cache.write(path, content)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

    def patch_license_check(self) -> int:
        self.log("[*] [LicensePatcher] Auto mode...")
        patched = 0
        for filepath in get_all_smali_files(self.decompiled_path):
            if len(filepath) > 250:
                continue
            content = self._read(filepath)
            if ("LicenseValidator" not in content
                    and "LicenseCheckerCallback" not in content):
                continue

            original = content
            for match in REGEX_BOOLEAN_METHOD.finditer(content):
                full = match.group(0)
                name = match.group(1).split("(")[0]
                if name in LICENSE_KEYWORDS:
                    header = full.split("\n")[0]
                    replacement = (
                        f"{header}\n"
                        "    .locals 1\n"
                        "    const/4 v0, 0x1\n"
                        "    return v0\n"
                        ".end method"
                    )
                    content = content.replace(full, replacement)
                    patched += 1
                    break

            if content != original:
                self._write(filepath, content)

        self.log(f"[*] [LicensePatcher] Patched {patched} files")
        return patched

    def patch_reverse_auto(self) -> int:
        self.log("[*] [LicensePatcher] Reverse Auto...")
        patched = 0
        for filepath in get_all_smali_files(self.decompiled_path):
            if len(filepath) > 250:
                continue
            content = self._read(filepath)
            if "ServerManagedPolicy" not in content:
                continue

            original = content
            for match in REGEX_SERVERMANAGEDPOLICY_CONSTRUCTOR.finditer(content):
                full = match.group(0)
                header = full.split("\n")[0]
                replacement = (
                    f"{header}\n"
                    "    .locals 1\n"
                    "    return-void\n"
                    ".end method"
                )
                content = content.replace(full, replacement)
                patched += 1
                break

            if content != original:
                self._write(filepath, content)

        self.log(f"[*] [LicensePatcher] Reverse auto patched {patched} files")
        return patched

    def patch(self) -> int:
        """Interface tương thích lazy_loader."""
        return self.patch_license_check()