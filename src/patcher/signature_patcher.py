"""
Signature verify patcher — vô hiệu hóa self-check signature.

v4 (2026):
  - Mở rộng keywords: getPackageInfo signatures, Signature.hashCode,
    checkSignatures, verifyCertificate, SafetyNet, PlayIntegrity.
  - Path hints mở rộng (đã giảm 52845 → ~722 files).
"""
from __future__ import annotations

import logging

from core.smali_utils import REGEX_SIGNATURE_METHOD
from patcher.base import BasePatcher

logger = logging.getLogger(__name__)

_KEYWORDS = (
    # Direct signature check
    "verifyPurchase", "checkSignature", "validatePurchase",
    "Signature", "checkSignatures", "getSignatures",
    "compareSignatures", "isSignatureValid",
    "verifySignature", "getSignature",
    # Package info
    "getPackageInfo", "signingInfo",
    # Certificate
    "checkCertificate", "verifyCertificate", "certificateMatch",
    "getCertificate",
    # SafetyNet / Play Integrity
    "SafetyNet", "PlayIntegrity", "IntegrityCheck",
    "attestation",
    # Debug check
    "isDebug", "isDebuggable", "getApplicationInfo",
    # Emulator / root (secondary defense)
    "isEmulator", "isRooted", "checkRoot",
)

_PATH_HINTS = (
    "signature", "sign", "integrity",
    "security", "checksum", "verify",
    "hash", "cert", "attestation",
    "safetynet", "playintegrity", "tamper",
)


class SignatureVerifyPatcher(BasePatcher):
    def patch(self) -> int:
        self.log("[*] [SignaturePatcher] Disabling self-signature checks")

        def _transform(content: str, filepath: str) -> str | None:
            original = content
            for match in REGEX_SIGNATURE_METHOD.finditer(content):
                full = match.group(0)
                name = match.group(1).lower()

                # Match expanded keywords
                if not any(
                    k.lower() in name
                    for k in (
                        "signature", "verify", "check", "integrity",
                        "certificate", "attestation", "safetynet",
                        "tamper", "debug",
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
            prefilter_keywords=_KEYWORDS,
            path_hints=_PATH_HINTS,
            label="SignaturePatcher",
        )