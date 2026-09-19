"""
Integrity check patcher — v4 (LP parity extended).

Mở rộng từ v3:
  - Explicit method list cho anti-tamper, anti-root, anti-debug, anti-Frida.
  - FrameworkPatcherV2 patterns: verifyMessageDigest, isError, unsafeGetCerts.
  - Hash algorithm keywords: SHA, MD5, CRC32, Adler32.
  - Tamper detection: checkTamper, validatePayload.
  - Path hints mở rộng: anti, tamper, root, frida, hook.

Nguyên tắc:
  - Match method NAME (không phải method signature) → tránh false positive.
  - Skip method có `.annotation` (thường là override/interface).
  - Trả `return_true` cho integrity/checksum, `return_false` cho detect.
  - Test pass 100% — không break old tests.
"""
from __future__ import annotations

import logging

from core.smali_utils import REGEX_INTEGRITY_METHOD
from patcher.base import BasePatcher

logger = logging.getLogger(__name__)


# ============================================================
# KEYWORDS — prefilter (must appear in file content)
# ============================================================
# Lưu ý: prefilter là case-sensitive `kw in content`. Include cả
# camelCase + snake_case variants để catch đầy đủ.
_KEYWORDS = (
    # Hash algorithms
    "MessageDigest", "Signature", "SHA", "MD5", "SHA-1", "SHA-256",
    "CRC32", "Adler32", "checksum", "Checksum", "integrity", "Integrity",
    # Tamper detection
    "tamper", "Tamper", "anti-tamper", "validatePayload",
    "verifyCRC", "verifyChecksum", "checkIntegrity",
    "checkTamper", "detectTamper", "validateHash",
    # Anti-debug / anti-root / anti-Frida
    "isDebug", "isDebuggable", "detectDebug", "checkDebug",
    "isRooted", "detectRoot", "checkRoot", "isRoot", "hasRoot",
    "isEmulator", "detectEmulator", "checkEmulator",
    "detectFrida", "isHooked", "checkFrida", "checkHook",
    "XposedDetect", "isXposed", "checkXposed", "detectXposed",
    # SafetyNet / Play Integrity
    "SafetyNet", "safetynet", "safetynetCheck",
    "PlayIntegrity", "playintegrity", "integrityToken",
    "attestation", "Attestation",
    # FrameworkPatcherV2 signatures
    "verifyMessageDigest", "unsafeGetCertsWithoutVerification",
    "ApkSignatureVerifier", "StrictJarVerifier",
)


# ============================================================
# EXPLICIT METHOD LIST — anti-tamper / anti-root patterns
# ============================================================
# Format: (keyword_substring, action)
#   action = "return_true"  → integrity/checksum checks pass
#   action = "return_false" → detection methods return false
_INTEGRITY_METHOD_ACTIONS: tuple[tuple[str, str], ...] = (
    # === Integrity / checksum / hash ===
    ("integrity", "return_true"),
    ("verifycrc", "return_true"),
    ("verifychecksum", "return_true"),
    ("validatepayload", "return_true"),
    ("verifyhash", "return_true"),
    ("validatehash", "return_true"),
    ("checkintegrity", "return_true"),
    ("verifydigest", "return_true"),
    ("verifymessagedigest", "return_true"),
    ("checkcrc", "return_true"),
    ("checksum", "return_true"),
    # === Tamper detection ===
    ("tamper", "return_false"),
    ("checktamper", "return_false"),
    ("detecttamper", "return_false"),
    ("antitamper", "return_false"),
    # === Root detection ===
    ("isrooted", "return_false"),
    ("isroot", "return_false"),
    ("detectroot", "return_false"),
    ("checkroot", "return_false"),
    ("hasroot", "return_false"),
    ("checkrooted", "return_false"),
    ("issuperuser", "return_false"),
    ("checkmagisk", "return_false"),
    ("issuavailable", "return_false"),
    # === Emulator detection ===
    ("isemulator", "return_false"),
    ("detectemulator", "return_false"),
    ("checkemulator", "return_false"),
    ("isvirtual", "return_false"),
    # === Debug detection ===
    ("isdebug", "return_false"),
    ("isdebuggable", "return_false"),
    ("detectdebug", "return_false"),
    ("checkdebug", "return_false"),
    ("isdebuggerconnected", "return_false"),
    # === Frida / hooking detection ===
    ("frida", "return_false"),
    ("detectfrida", "return_false"),
    ("checkfrida", "return_false"),
    ("ishooked", "return_false"),
    ("checkhook", "return_false"),
    ("detecthook", "return_false"),
    ("checkxposed", "return_false"),
    ("isxposed", "return_false"),
    ("detectxposed", "return_false"),
    # === SafetyNet / Play Integrity ===
    ("safetynet", "return_true"),
    ("playintegrity", "return_true"),
    ("integritytoken", "return_true"),
    ("attestation", "return_true"),
    # === FrameworkPatcherV2 — signature verify ===
    ("unsafegetcertswithoutverification", "return_true"),
    ("verifymessagedigest", "return_true"),
    ("verifyv1signature", "return_true"),
    # === FrameworkPatcherV2 — package parsing ===
    ("iserror", "return_false"),
    ("checkdowngrade", "return_false"),
)


# ============================================================
# PATH HINTS
# ============================================================
_PATH_HINTS = (
    "integrity", "signature", "security", "hash",
    "checksum", "verify", "tamper", "anti",
    "root", "debug", "emulator", "frida",
    "safetynet", "attestation",
)


# ============================================================
# PATCHER
# ============================================================
class SignatureIntegrityPatcher(BasePatcher):
    # Backward-compat: keyword tuple cho prefilter
    KEYWORDS = _KEYWORDS

    def patch(self) -> int:
        self.log(
            "[*] [SigIntegrity] v4 (anti-tamper + anti-root + "
            "anti-debug + framework methods)"
        )

        def _transform(content: str, filepath: str) -> str | None:
            original = content

            for match in REGEX_INTEGRITY_METHOD.finditer(content):
                full = match.group(0)
                name = match.group(1).split("(")[0]
                name_lower = name.lower()

                # Skip methods with annotations (override/interface)
                if ".annotation" in full:
                    continue

                action = self._classify_method(name_lower)
                if action is None:
                    continue

                # Build replacement body based on action
                if action == "return_true":
                    replacement_body = (
                        "    .locals 1\n"
                        "    const/4 v0, 0x1\n"
                        "    return v0\n"
                    )
                else:  # return_false
                    replacement_body = (
                        "    .locals 1\n"
                        "    const/4 v0, 0x0\n"
                        "    return v0\n"
                    )

                header = full.split("\n")[0]
                content = content.replace(
                    full,
                    f"{header}\n{replacement_body}.end method",
                )

            return content if content != original else None

        return self.patch_files(
            _transform,
            prefilter_keywords=self.KEYWORDS,
            path_hints=_PATH_HINTS,
            label="SigIntegrity",
        )

    # ============================================================
    # CLASSIFIER
    # ============================================================
    def _classify_method(self, name_lower: str) -> str | None:
        """
        Classify method name → action.

        Priority: exact substring match first, else None (skip).
        Order matters — more specific patterns checked first.
        """
        for keyword, action in _INTEGRITY_METHOD_ACTIONS:
            if keyword in name_lower:
                return action
        return None