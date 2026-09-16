"""
License Extreme — 5 chế độ license bypass.
"""
from __future__ import annotations

import logging

from core.smali_utils import (
    REGEX_BOOLEAN_METHOD,
    REGEX_INVOKE_LICENSE,
    REGEX_INVOKE_ILICENSING,
    get_all_smali_files,
)

logger = logging.getLogger(__name__)

LICENSE_KEYWORDS = {
    "allow", "dontAllow", "checkLicense", "isLicensed", "verifyLicense",
}


class LicenseExtremePatcher:
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

    def patch_extreme(self) -> int:
        """Xóa mọi invoke liên quan LicenseChecker/ILicensingService."""
        self.log("[*] [LicenseExtreme] Extreme mode...")
        patched = 0
        for filepath in get_all_smali_files(self.decompiled_path):
            if len(filepath) > 250:
                continue
            content = self._read(filepath)

            if not ("LicenseChecker" in content
                    or "ILicensingService" in content
                    or "checkLicense" in content):
                continue

            original = content
            content = REGEX_INVOKE_LICENSE.sub("", content)
            content = REGEX_INVOKE_ILICENSING.sub("", content)

            if content != original:
                self._write(filepath, content)
                patched += 1

        self.log(f"[*] [LicenseExtreme] Patched {patched} files")
        return patched

    def patch_reverse_auto(self) -> int:
        return self.patch_extreme()

    def patch_amazon_market(self) -> int:
        self.log("[*] [LicenseExtreme] Amazon mode...")
        return self._patch_by_keyword(
            ("amazon", "appstore"),
            "Amazon",
        )

    def patch_samsung_apps(self) -> int:
        self.log("[*] [LicenseExtreme] Samsung mode...")
        return self._patch_by_keyword(
            ("samsung", "galaxy"),
            "Samsung",
        )

    def _patch_by_keyword(self, keywords: tuple[str, ...], label: str) -> int:
        patched = 0
        for filepath in get_all_smali_files(self.decompiled_path):
            if len(filepath) > 250:
                continue
            content = self._read(filepath)
            if not any(kw in content.lower() for kw in keywords):
                continue

            original = content
            for match in REGEX_BOOLEAN_METHOD.finditer(content):
                name = match.group(1).split("(")[0]
                if name not in LICENSE_KEYWORDS:
                    continue
                header = match.group(0).split("\n")[0]
                replacement = (
                    f"{header}\n"
                    "    .locals 1\n"
                    "    const/4 v0, 0x1\n"
                    "    return v0\n"
                    ".end method"
                )
                content = content.replace(match.group(0), replacement)
                patched += 1
                break

            if content != original:
                self._write(filepath, content)

        self.log(f"[*] [LicenseExtreme] {label} patched {patched} files")
        return patched

    def patch(self) -> int:
        return self.patch_extreme()