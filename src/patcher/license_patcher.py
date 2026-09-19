"""
License verification patcher — Auto + Reverse Auto.

v4 (2026):
  - Mở rộng patterns: Google LVL, Google Play Billing (v3-v7 license),
    Amazon DRM, Samsung IAP license, custom license managers.
  - Method name heuristics + content-based detection.
  - path_hints prefilter (giảm 52845 → ~500 files).
"""
from __future__ import annotations

import logging
import re

from core.smali_utils import REGEX_BOOLEAN_METHOD
from patcher.base import BasePatcher

logger = logging.getLogger(__name__)


# ============================================================
# METHOD NAME PATTERNS (case-insensitive matching)
# ============================================================
LICENSE_KEYWORDS = frozenset({
    # Google LVL
    "allow", "dontallow",
    "checklicense", "islicensed", "verifylicense",
    "licensevalid", "hasvalidlicense",
    "onlicensecheck", "onlicensefail", "onlicenseerror",
    "validateLicense".lower(), "checkLicenseInternal".lower(),
    # Google Play Billing (v3+ license as purchase)
    "ispurchased", "haspurchased", "ispurchasevalid",
    "verifypurchase", "validatepurchase",
    "checkpurchase", "verifyreceipt",
    # Pro / Premium flags
    "ispro", "isproversion", "ispremiumuser", "ispaiduser",
    "isfullversion", "isunlocked", "ispremium",
    "haspro", "hassubscription", "issubscribed",
    "checkprostatus", "verifyprostatus", "checkpremium",
    # Custom wrappers
    "islicensedapp", "islicensevalid", "isapplicensed",
    "verifyapplicense", "checkapplicense",
    # Amazon DRM
    "isamazonlicensed", "checkamazonlicense",
    # Samsung
    "issamsunglicensed",
})

# Content-level signals — 1 hit đủ để coi file có license logic
_CONTENT_SIGNALS = (
    "LicenseChecker",
    "LicenseCheckerCallback",
    "ILicensingService",
    "LicenseValidator",
    "ServerManagedPolicy",
    "com.google.android.vending.licensing",
    "com.amazon.venezia",
    "com.sec.android.iap",
    "isProUser", "isPremiumUser",
)

# Broad keyword prefilter — used in patch_files(prefilter_keywords=...)
_PREFILTER_KEYWORDS = (
    "LicenseChecker", "LicenseCheckerCallback", "ServerManagedPolicy",
    "LicenseValidator", "ILicensingService",
    "isProUser", "isPremiumUser", "isLicensed",
    "com.amazon.venezia", "com.sec.android.iap",
)

_BLACKLIST = (
    "offlinelicensehelper",
    "licensinglistener",   # often analytics listener
    "bidtoken",
)

_PATH_HINTS = (
    "license", "licensing", "lvl", "validator", "vending",
    "purchase", "billing", "iap", "pro", "premium",
    "amazon", "samsung", "store",
)


class LicensePatcher(BasePatcher):
    def patch(self) -> int:
        return self.patch_license_check()

    def patch_license_check(self) -> int:
        """Auto mode — patch known license boolean methods."""
        self.log("[*] [LicensePatcher] Auto mode")

        def _transform(content: str, filepath: str) -> str | None:
            fp_lower = filepath.replace("\\", "/").lower()
            if any(bl in fp_lower for bl in _BLACKLIST):
                return None

            # Quick filter: chỉ xử lý file có license signal
            has_signal = any(
                s in content for s in _CONTENT_SIGNALS
            )
            if not has_signal:
                # Fallback: match bằng method name trong file nhỏ
                if not any(
                    kw in content.lower() for kw in LICENSE_KEYWORDS
                ):
                    return None

            modified = False
            for match in REGEX_BOOLEAN_METHOD.finditer(content):
                full = match.group(0)
                name = match.group(1).split("(")[0].lower()
                if name not in LICENSE_KEYWORDS:
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
                modified = True

            return content if modified else None

        return self.patch_files(
            _transform,
            prefilter_keywords=_PREFILTER_KEYWORDS,
            path_hints=_PATH_HINTS,
            label="LicensePatcher",
        )

    # ============================================================
    # REVERSE AUTO — ServerManagedPolicy constructor stub
    # ============================================================
    def patch_reverse_auto(self) -> int:
        self.log("[*] [LicensePatcher] Reverse Auto mode")

        def _transform(content: str, filepath: str) -> str | None:
            if "ServerManagedPolicy" not in content:
                return None

            pat = re.compile(
                r"(\.method\s+(?:public|protected)\s+constructor\s+"
                r"<init>\([^)]*\)V\s+"
                r"\.registers\s+\d+\s*)"
                r".*?"
                r"(\.end\s+method)",
                re.DOTALL,
            )
            m = pat.search(content)
            if not m:
                return None

            header_block = m.group(1)
            lines = header_block.split("\n")
            method_header = lines[0]
            registers = next(
                (l.strip() for l in lines if ".registers" in l),
                "    .registers 1",
            )
            replacement = (
                f"{method_header}\n"
                f"    {registers}\n"
                "    return-void\n"
                ".end method"
            )
            return content[: m.start()] + replacement + content[m.end():]

        return self.patch_files(
            _transform,
            prefilter_keywords=("ServerManagedPolicy",),
            path_hints=_PATH_HINTS,
            label="LicensePatcher-Rev",
        )