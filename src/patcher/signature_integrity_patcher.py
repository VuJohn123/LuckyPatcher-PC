"""Loại bỏ integrity check (MessageDigest, Signature hash)."""
from __future__ import annotations

import os

from core.smali_utils import REGEX_INTEGRITY_METHOD, get_all_smali_files


class SignatureIntegrityPatcher:
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
        self.log("[*] [SigIntegrity] Removing integrity checks...")
        patched = 0
        keywords = ("MessageDigest", "Signature")

        for filepath in get_all_smali_files(self.decompiled_path):
            if len(filepath) > 250:
                continue
            content = self._read(filepath)
            if not any(kw in content for kw in keywords):
                continue

            original = content
            for match in REGEX_INTEGRITY_METHOD.finditer(content):
                full = match.group(0)
                name = match.group(1).split("(")[0]
                if not any(kw in name.lower() for kw in
                           ("integrity", "verify", "check", "hash", "digest")):
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

        self.log(f"[*] [SigIntegrity] Patched {patched} files")
        return patched