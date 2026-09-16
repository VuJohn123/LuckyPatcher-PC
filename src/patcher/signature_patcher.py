"""Signature verify patcher — vô hiệu hóa self-check signature."""
from __future__ import annotations

import logging
import os

from core.smali_utils import REGEX_SIGNATURE_METHOD, get_all_smali_files

logger = logging.getLogger(__name__)


class SignatureVerifyPatcher:
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

    def patch(self) -> int:
        self.log("[*] [SignaturePatcher] Disabling self-signature checks...")
        patched = 0
        keywords = ("verifyPurchase", "checkSignature", "validatePurchase",
                    "Signature", "RSA")

        for filepath in get_all_smali_files(self.decompiled_path):
            if len(filepath) > 250:
                continue
            content = self._read(filepath)
            # Pre-filter nhanh
            if not any(kw in content for kw in keywords):
                continue

            original = content
            for match in REGEX_SIGNATURE_METHOD.finditer(content):
                full = match.group(0)
                method_name = match.group(1)
                if not any(k in method_name.lower() for k in
                           ("signature", "verify", "check")):
                    continue
                if ".annotation" in full:
                    continue
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

            if content != original:
                self._write(filepath, content)

        self.log(f"[*] [SignaturePatcher] Patched {patched} files")
        return patched