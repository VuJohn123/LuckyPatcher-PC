"""
License Extreme — bytecode pattern matching (LP parity).

v3 (2026):
  - Mở rộng invoke-removal: Google LVL + Amazon DRM + Samsung IAP +
    Huawei IAP + Play Billing v3-v7 (getBuyIntent, launchBillingFlow).
  - Thêm pattern detection cho binding-based license check.
  - Market-specific mở rộng (Amazon/Samsung/Huawei/Yandex).
"""
from __future__ import annotations

import logging
import re

from core.smali_utils import (
    REGEX_BOOLEAN_METHOD,
    REGEX_INVOKE_LICENSE,
    REGEX_INVOKE_ILICENSING,
)
from patcher.base import BasePatcher

logger = logging.getLogger(__name__)

LICENSE_KEYWORDS = frozenset({
    "allow", "dontallow", "checklicense", "islicensed",
    "verifylicense", "ispurchased", "haspurchased",
    "ispro", "isproversion", "ispremiumuser", "ispaiduser",
    "isfullversion", "isunlocked",
})

# Thêm invoke patterns cho các market khác
_EXTRA_INVOKE_PATTERNS = (
    # Google Play Billing license-in-purchase
    re.compile(r".*invoke.*getBuyIntent.*\n"),
    re.compile(r".*invoke.*launchBillingFlow.*\n"),
    re.compile(r".*invoke.*queryPurchases.*\n"),
    # Amazon DRM
    re.compile(r".*invoke.*amazon.*verify.*\n", re.IGNORECASE),
    re.compile(r".*invoke.*com/amazon/venezia.*\n"),
    # Samsung IAP
    re.compile(r".*invoke.*com/sec/android/iap.*\n"),
    # Huawei IAP
    re.compile(r".*invoke.*com/huawei/hms/iap.*\n"),
)


class LicenseExtremePatcher(BasePatcher):
    def patch(self) -> int:
        return self.patch_extreme()

    # ============================================================
    # EXTREME — remove invoke patterns
    # ============================================================
    def patch_extreme(self) -> int:
        self.log("[*] [LicenseExtreme] Extreme mode (invoke removal)")

        def _transform(content: str, filepath: str) -> str | None:
            # Quick prefilter
            if not any(k in content for k in (
                "LicenseChecker", "ILicensingService", "checkLicense",
                "getBuyIntent", "launchBillingFlow", "queryPurchases",
                "com/amazon/venezia", "com/sec/android/iap",
                "com/huawei/hms/iap",
            )):
                return None

            original = content
            content = REGEX_INVOKE_LICENSE.sub(
                "# invoke-removed by LicenseExtreme\n", content,
            )
            content = REGEX_INVOKE_ILICENSING.sub(
                "# invoke-removed by LicenseExtreme\n", content,
            )
            for pat in _EXTRA_INVOKE_PATTERNS:
                content = pat.sub(
                    "# invoke-removed by LicenseExtreme\n", content,
                )
            return content if content != original else None

        return self.patch_files(
            _transform,
            prefilter_keywords=(
                "LicenseChecker", "ILicensingService", "checkLicense",
                "getBuyIntent", "launchBillingFlow",
                "com/amazon/venezia", "com/sec/android/iap",
            ),
            path_hints=(
                "license", "licensing", "lvl",
                "billing", "purchase", "iap", "store",
            ),
            label="LicenseExtreme",
        )

    # ============================================================
    # PATTERN — bindService-based LVL
    # ============================================================
    def patch_pattern(self) -> int:
        self.log("[*] [LicenseExtreme] Bytecode pattern mode")

        from core.regex_safe import safe_search

        LVL_BIND_PATTERN = (
            r"\.method\s+(?:(?:public|private|protected|static|final)"
            r"\s+)+(\S+)\s*\([^)]*\)Z\s+"
            r"\.registers\s+\d+\s+"
            r".{0,3000}?"
            r"invoke-virtual\s+\{[^}]*\},\s+"
            r"Landroid/content/Context;->bindService"
            r".{0,3000}?"
            r"\.end\s+method"
        )

        def _transform(content: str, filepath: str) -> str | None:
            if "bindService" not in content:
                return None
            m = safe_search(
                LVL_BIND_PATTERN, content,
                flags=re.DOTALL,
            )
            if not m:
                return None
            full = m.group(0)
            header = full.split("\n")[0]
            replacement = (
                f"{header}\n"
                "    .locals 1\n"
                "    const/4 v0, 0x1\n"
                "    return v0\n"
                ".end method"
            )
            return content.replace(full, replacement)

        return self.patch_files(
            _transform,
            prefilter_keywords=("bindService",),
            label="LicenseExtreme-Pattern",
        )

    # ============================================================
    # MARKET-SPECIFIC
    # ============================================================
    def patch_reverse_auto(self) -> int:
        return self.patch_extreme()

    def patch_amazon_market(self) -> int:
        return self._patch_by_keyword(
            ("amazon", "appstore", "venezia"), "Amazon",
        )

    def patch_samsung_apps(self) -> int:
        return self._patch_by_keyword(
            ("samsung", "galaxy", "com/sec/android/iap"), "Samsung",
        )

    def _patch_by_keyword(
        self, keywords: tuple[str, ...], label: str,
    ) -> int:
        self.log(f"[*] [LicenseExtreme] {label} mode")

        def _transform(content: str, filepath: str) -> str | None:
            c_lower = content.lower()
            if not any(kw in c_lower for kw in keywords):
                return None
            original = content
            for match in REGEX_BOOLEAN_METHOD.finditer(content):
                name = match.group(1).split("(")[0].lower()
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
            return content if content != original else None

        return self.patch_files(
            _transform,
            prefilter_keywords=keywords,
            label=f"LicenseExtreme-{label}",
        )