"""
Loại bỏ integrity check.

v3 (2026):
  - Mở rộng keywords: hash algorithms, checksum, tamper detection.
  - Thêm path_hints để giảm scan.
"""
from __future__ import annotations

from core.smali_utils import REGEX_INTEGRITY_METHOD
from patcher.base import BasePatcher


class SignatureIntegrityPatcher(BasePatcher):
    # Expanded: hash algorithms + integrity + tamper detection
    KEYWORDS = (
        "MessageDigest", "Signature", "SHA", "MD5", "SHA-1", "SHA-256",
        "CRC32", "Adler32", "checksum", "integrity",
        "tamper", "anti-tamper",
    )

    _PATH_HINTS = (
        "integrity", "signature", "security", "hash",
        "checksum", "verify", "tamper", "anti",
    )

    def patch(self) -> int:
        self.log("[*] [SigIntegrity] Removing integrity checks")

        def _transform(content, filepath):
            original = content
            for match in REGEX_INTEGRITY_METHOD.finditer(content):
                full = match.group(0)
                name = match.group(1).split("(")[0].lower()
                if not any(
                    k.lower() in name
                    for k in (
                        "integrity", "verify", "check", "hash",
                        "digest", "checksum", "tamper",
                        "validate", "crc",
                    )
                ):
                    continue
                if ".annotation" in full:
                    continue
                header = full.split("\n")[0]
                content = content.replace(
                    full,
                    f"{header}\n    .locals 1\n"
                    "    const/4 v0, 0x1\n    return v0\n.end method",
                )
            return content if content != original else None

        return self.patch_files(
            _transform,
            prefilter_keywords=self.KEYWORDS,
            path_hints=self._PATH_HINTS,
            label="SigIntegrity",
        )