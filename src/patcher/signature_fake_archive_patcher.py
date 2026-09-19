"""Giả mạo archive signature check."""
from __future__ import annotations
from core.smali_utils import REGEX_INTEGRITY_METHOD
from patcher.base import BasePatcher

class SignatureFakeArchivePatcher(BasePatcher):
    KEYWORDS = ("ZipEntry", "getEntry")

    def patch(self) -> int:
        self.log("[*] [SigFakeArchive] Faking archive checks")

        def _transform(content, filepath):
            original = content
            for match in REGEX_INTEGRITY_METHOD.finditer(content):
                full = match.group(0)
                name = match.group(1).split("(")[0]
                if not any(k in name.lower()
                           for k in ("zip", "archive", "entry", "apk")):
                    continue
                header = full.split("\n")[0]
                content = content.replace(full,
                    f"{header}\n    .locals 1\n"
                    "    const/4 v0, 0x1\n    return v0\n.end method")
            return content if content != original else None

        return self.patch_files(
            _transform,
            prefilter_keywords=self.KEYWORDS,
            label="SigFakeArchive",
        )