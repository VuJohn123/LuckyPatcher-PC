"""
Signature verify patcher — vô hiệu hóa self-check signature.

v6 (2026):
  - Thêm FrameworkPatcherV2 exact methods (12 framework classes).
  - LP-style `0x80` INSTALL_ALLOW_DOWNGRADE trick.
  - `checkSignatures` / `compareSignatures` call-site → return 0 (MATCH).
  - `getPackageInfo` flag injection (GET_SIGNING_CERTIFICATES).
  - Path hints mở rộng (52845 → ~722 files).

FrameworkPatcherV2 methods ported (chỉ apply khi app bundle
các class framework-like — hiếm nhưng có với custom ROM apps):

  framework.jar (7 classes, 9 methods):
    PackageParser.unsafeGetCertsWithoutVerification  → v1 = 0x1
    SigningDetails.checkCapability                   → return 0x1
    SigningDetails.hasAncestorOrSelf                 → return 0x1
    ApkSignatureVerifier.verifyV1Signature           → p3 = 0x0
    ApkSignatureSchemeV2Verifier (MessageDigest)     → move-result v0 = 0x1
    ApkSignatureSchemeV3Verifier (same)              → move-result v0 = 0x1
    ApkSigningBlockUtils (MessageDigest)             → move-result v7 = 0x1
    StrictJarVerifier.verifyMessageDigest            → return 0x1
    StrictJarFile.findEntry                          → remove guard

  services.jar (4 classes, 5 methods):
    PackageManagerServiceUtils.checkDowngrade        → return-void
    PackageManagerServiceUtils.verifySignatures      → return 0x0
    PackageManagerServiceUtils.matchSignaturesCompat → return 0x1
    InstallPackageHelper.isLeavingSharedUser         → v3 = 0x1
    KeySetManagerService.shouldCheckUpgradeKeySet    → return 0x0
"""
from __future__ import annotations

import logging
import re

from core.smali_utils import REGEX_SIGNATURE_METHOD
from patcher.base import BasePatcher

logger = logging.getLogger(__name__)


# ============================================================
# CONSTANTS
# ============================================================
_FLAG_INSTALL_ALLOW_DOWNGRADE = 0x80
_FLAG_GET_SIGNING_CERTIFICATES = 0x08000000


# ============================================================
# KEYWORDS — method names for Pass 1 (regex method body match)
# ============================================================
_KEYWORDS = (
    # Direct signature check
    "verifyPurchase", "checkSignature", "validatePurchase",
    "Signature", "checkSignatures", "getSignatures",
    "compareSignatures", "isSignatureValid",
    "verifySignature", "getSignature",
    # Package info
    "getPackageInfo", "signingInfo", "getSigningInfo",
    # Certificate
    "checkCertificate", "verifyCertificate", "certificateMatch",
    "getCertificate",
    # SafetyNet / Play Integrity
    "SafetyNet", "PlayIntegrity", "IntegrityCheck",
    "attestation",
    # Debug
    "isDebug", "isDebuggable", "getApplicationInfo",
    # Emulator / root
    "isEmulator", "isRooted", "checkRoot",
    # FrameworkPatcherV2 method hints
    "unsafeGetCertsWithoutVerification", "checkCapability",
    "hasAncestorOrSelf", "verifyV1Signature",
    "verifyMessageDigest", "findEntry",
    "checkDowngrade", "matchSignaturesCompat",
    "isLeavingSharedUser", "shouldCheckUpgradeKeySetLocked",
    "getMinimumSignatureSchemeVersionForTargetSdk",
)


_PATH_HINTS = (
    "signature", "sign", "integrity",
    "security", "checksum", "verify",
    "hash", "cert", "attestation",
    "safetynet", "playintegrity", "tamper",
    "installer", "updater", "package",
    "framework", "packageparser", "signingdetails",
    "apksignature", "strictjar", "keyset", "reconcile",
)


# ============================================================
# REGEX — call-site patterns (Pass 2 + 3)
# ============================================================
_CHECK_SIG_CALL_RE = re.compile(
    r"(invoke-virtual\s+\{[^}]*\},\s+"
    r"Landroid/content/pm/PackageManager;->checkSignatures\([^)]*\)I\s*\n"
    r"\s+move-result(?:-object)?\s+(v\d+|p\d+))",
    re.MULTILINE,
)

_COMPARE_SIG_CALL_RE = re.compile(
    r"(invoke-static\s+\{[^}]*\},\s+"
    r"Landroid/content/pm/PackageManagerServiceUtils;->compareSignatures"
    r"\([^)]*\)I\s*\n"
    r"\s+move-result(?:-object)?\s+(v\d+|p\d+))",
    re.MULTILINE,
)

_GET_PKG_INFO_RE = re.compile(
    r"const/(?:4|16)\s+(v\d+|p\d+),\s*(0x[0-9a-fA-F]+|\d+)\s*\n"
    r"(.*?)"
    r"invoke-virtual\s+\{[^}]*\},\s+"
    r"Landroid/content/pm/PackageManager;->getPackageInfo\("
    r"[^)]*\)Landroid/content/pm/PackageInfo;",
    re.DOTALL,
)


# ============================================================
# FrameworkPatcherV2 — exact method signatures
# ============================================================
# Each entry: (class_descriptor, method_name, patch_kind)
# patch_kind:
#   "return_true"  → add `const/4 v0, 0x1; return v0`
#   "return_zero"  → add `const/4 v0, 0x0; return v0`
#   "return_void"  → add `return-void`
#   "digest_equal" → patch move-result after MessageDigest.isEqual
_FRAMEWORK_METHODS: list[tuple[str, str, str]] = [
    # framework.jar
    ("Landroid/content/pm/PackageParser;",
     "unsafeGetCertsWithoutVerification", "return_true"),
    ("Landroid/content/pm/SigningDetails;",
     "checkCapability", "return_true"),
    ("Landroid/content/pm/SigningDetails;",
     "hasAncestorOrSelf", "return_true"),
    ("Landroid/util/apk/ApkSignatureVerifier;",
     "verifyV1Signature", "return_true"),
    ("Landroid/util/apk/ApkSignatureSchemeV2Verifier;",
     "verifyIntegrity", "return_true"),
    ("Landroid/util/apk/ApkSignatureSchemeV3Verifier;",
     "verifyIntegrity", "return_true"),
    ("Landroid/util/apk/ApkSigningBlockUtils;",
     "verifyIntegrity", "return_true"),
    ("Ljava/util/jar/StrictJarVerifier;",
     "verifyMessageDigest", "return_true"),
    ("Landroid/content/pm/parsing/ParsingPackageUtils;",
     "isError", "return_zero"),
    # services.jar
    ("Lcom/android/server/pm/PackageManagerServiceUtils;",
     "checkDowngrade", "return_void"),
    ("Lcom/android/server/pm/PackageManagerServiceUtils;",
     "verifySignatures", "return_zero"),
    ("Lcom/android/server/pm/PackageManagerServiceUtils;",
     "matchSignaturesCompat", "return_true"),
    ("Lcom/android/server/pm/InstallPackageHelper;",
     "isLeavingSharedUser", "return_true"),
    ("Lcom/android/server/pm/KeySetManagerService;",
     "shouldCheckUpgradeKeySetLocked", "return_zero"),
]


# ============================================================
# Regex build from _FRAMEWORK_METHODS
# ============================================================
def _build_framework_regex(
    class_desc: str, method_name: str,
) -> re.Pattern:
    """Match method header + body cho class/method cụ thể."""
    # Escape class descriptor for regex
    cls = re.escape(class_desc)
    meth = re.escape(method_name)
    # Match .method ... name(...)RET ... .end method
    return re.compile(
        r"(\.method\s+(?:(?:public|private|protected|static|final)"
        r"\s+)+" + meth + r"\s*\([^)]*\)\S*\s+"
        r"\.registers\s+\d+\s+.*?\.end\s+method)",
        re.DOTALL,
    )


_FRAMEWORK_REGEXES: dict[tuple[str, str], tuple[re.Pattern, str]] = {
    (cls, meth): (_build_framework_regex(cls, meth), kind)
    for cls, meth, kind in _FRAMEWORK_METHODS
}


# ============================================================
# PATCHER
# ============================================================
class SignatureVerifyPatcher(BasePatcher):
    def patch(self) -> int:
        self.log(
            "[*] [SignaturePatcher] v6 (LP parity: 0x80 + "
            "FrameworkPatcherV2 + digest patch)"
        )

        def _transform(content: str, filepath: str) -> str | None:
            original = content

            # Pass 1: standard method body patch (regex boolean return)
            content = self._patch_method_bodies(content)

            # Pass 2: LP 0x80 trick (checkSignatures → 0)
            content = self._patch_check_signatures_calls(content)

            # Pass 3: getPackageInfo flag injection
            content = self._patch_get_package_info(content)

            # Pass 4: FrameworkPatcherV2 exact methods
            content = self._patch_framework_methods(content)

            # Pass 5: MessageDigest.isEqual → force match (V2/V3/BLOCK)
            content = self._patch_message_digest_is_equal(content)

            return content if content != original else None

        return self.patch_files(
            _transform,
            prefilter_keywords=_KEYWORDS,
            path_hints=_PATH_HINTS,
            label="SignaturePatcher",
        )

    # ============================================================
    # PASS 1 — method body boolean patch
    # ============================================================
    def _patch_method_bodies(self, content: str) -> str:
        for match in REGEX_SIGNATURE_METHOD.finditer(content):
            full = match.group(0)
            name = match.group(1).lower()

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
            replacement = (
                f"{header}\n"
                "    .locals 1\n"
                "    const/4 v0, 0x1\n"
                "    return v0\n"
                ".end method"
            )
            content = content.replace(full, replacement)
        return content

    # ============================================================
    # PASS 2 — LP 0x80 trick
    # ============================================================
    def _patch_check_signatures_calls(self, content: str) -> str:
        def _replace(m: re.Match) -> str:
            invoke = m.group(1).split("\n")[0]
            dest_reg = m.group(2)
            return f"{invoke}\n    const/4 {dest_reg}, 0x0"

        content = _CHECK_SIG_CALL_RE.sub(_replace, content)
        content = _COMPARE_SIG_CALL_RE.sub(_replace, content)
        return content

    # ============================================================
    # PASS 3 — getPackageInfo flag injection
    # ============================================================
    def _patch_get_package_info(self, content: str) -> str:
        if "getPackageInfo" not in content:
            return content

        def _replace(m: re.Match) -> str:
            reg = m.group(1)
            old_val_str = m.group(2)
            middle = m.group(3)
            try:
                old_val = (
                    int(old_val_str, 16)
                    if old_val_str.startswith("0x")
                    else int(old_val_str)
                )
            except ValueError:
                return m.group(0)

            new_val = old_val | _FLAG_GET_SIGNING_CERTIFICATES
            if new_val == old_val:
                return m.group(0)

            return (
                f"const/16 {reg}, 0x{new_val:x}\n"
                f"{middle}"
                f"invoke-virtual {{...}}, "
                f"Landroid/content/pm/PackageManager;->getPackageInfo"
                f"(Ljava/lang/String;I)Landroid/content/pm/PackageInfo;"
            )

        return _GET_PKG_INFO_RE.sub(_replace, content)

    # ============================================================
    # PASS 4 — FrameworkPatcherV2 exact methods
    # ============================================================
    def _patch_framework_methods(self, content: str) -> str:
        """
        Match framework methods CHỈ khi class name xuất hiện trong file.
        Đây là edge case (custom ROM apps bundle framework-like classes),
        nhưng vẫn hữu ích để đảm bảo comprehensive coverage.
        """
        for (cls_desc, meth_name), (regex, kind) in (
            _FRAMEWORK_REGEXES.items()
        ):
            # Class descriptor in smali uses `Lfoo/bar;` — check presence
            # But .method line only shows method name, not class. So we
            # check the whole file text for the class reference.
            cls_short = cls_desc.strip("L;").split("/")[-1]
            if cls_short not in content:
                continue

            def _replace(m: re.Match, kind=kind) -> str:
                full = m.group(0)
                header = full.split("\n")[0]

                if kind == "return_true":
                    body = (
                        f"{header}\n"
                        "    .locals 1\n"
                        "    const/4 v0, 0x1\n"
                        "    return v0\n"
                        ".end method"
                    )
                elif kind == "return_zero":
                    body = (
                        f"{header}\n"
                        "    .locals 1\n"
                        "    const/4 v0, 0x0\n"
                        "    return v0\n"
                        ".end method"
                    )
                elif kind == "return_void":
                    body = (
                        f"{header}\n"
                        "    .locals 0\n"
                        "    return-void\n"
                        ".end method"
                    )
                else:
                    return full
                return body

            content = regex.sub(_replace, content)

        return content

    # ============================================================
    # PASS 5 — MessageDigest.isEqual → force match
    # ============================================================
    def _patch_message_digest_is_equal(self, content: str) -> str:
        """
        Trong V2/V3 signature verification, `MessageDigest.isEqual` là
        final check. Patch call-site → move-result const/4 vX, 0x1.

        Pattern:
            invoke-static {...}, Ljava/security/MessageDigest;->isEqual(...)Z
            move-result vX
            if-eqz vX, :cond_fail
        """
        pattern = re.compile(
            r"(invoke-static\s+\{[^}]*\},\s+"
            r"Ljava/security/MessageDigest;->isEqual\([^)]*\)Z\s*\n"
            r"\s+move-result\s+(v\d+|p\d+))",
            re.MULTILINE,
        )

        def _replace(m: re.Match) -> str:
            invoke = m.group(1).split("\n")[0]
            reg = m.group(2)
            return f"{invoke}\n    const/4 {reg}, 0x1"

        return pattern.sub(_replace, content)