"""
License Extreme — bytecode pattern matching (LP parity).

v4 (2026):
  - Mở rộng invoke-removal cho 8 store SDK:
    Google LVL, Play Billing v3-v7, Amazon DRM, Samsung IAP, Huawei IAP,
    Yandex Store, Unity IAP, Facebook IAP.
  - Pattern detection cho bindService-based LVL.
  - Market-specific keyword patch (Amazon/Samsung/Huawei/Yandex).
  - Bytecode signature matching (obfuscation-resistant).
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


# ============================================================
# LICENSE METHOD KEYWORDS
# ============================================================
LICENSE_KEYWORDS = frozenset({
    "allow", "dontallow",
    "checklicense", "islicensed", "verifylicense",
    "licensevalid", "hasvalidlicense",
    "onlicensecheck", "onlicensefail", "onlicenseerror",
    "ispurchased", "haspurchased", "ispurchasevalid",
    "verifypurchase", "validatepurchase",
    "checkpurchase", "verifyreceipt",
    "ispro", "isproversion", "ispremiumuser", "ispaiduser",
    "isfullversion", "isunlocked", "ispremium",
    "haspro", "hassubscription", "issubscribed",
    "checkprostatus", "verifyprostatus", "checkpremium",
    "islicensedapp", "islicensevalid", "isapplicensed",
    "verifyapplicense", "checkapplicense",
    "isamazonlicensed", "checkamazonlicense",
    "issamsunglicensed", "ishuaweilicensed",
})


# ============================================================
# INVOKE-REMOVAL PATTERNS (LP parity, 8 stores)
# ============================================================
_EXTRA_INVOKE_PATTERNS = (
    # Google Play Billing v3-v7
    re.compile(r".*invoke.*getBuyIntent.*\n"),
    re.compile(r".*invoke.*getBuyIntentToReplaceSkus.*\n"),
    re.compile(r".*invoke.*getBuyIntentExtraParams.*\n"),
    re.compile(r".*invoke.*launchBillingFlow.*\n"),
    re.compile(r".*invoke.*queryPurchases.*\n"),
    re.compile(r".*invoke.*querySkuDetails.*\n"),
    re.compile(r".*invoke.*queryProductDetails.*\n"),
    re.compile(r".*invoke.*consumePurchase.*\n"),
    re.compile(r".*invoke.*acknowledgePurchase.*\n"),
    # Amazon DRM/IAP
    re.compile(r".*invoke.*com/amazon/venezia.*\n"),
    re.compile(r".*invoke.*com/amazon/identity.*\n"),
    re.compile(r".*invoke.*com/amazon/device/iap.*\n"),
    # Samsung IAP
    re.compile(r".*invoke.*com/sec/android/iap.*\n"),
    # Huawei IAP
    re.compile(r".*invoke.*com/huawei/hms/iap.*\n"),
    # Yandex Store
    re.compile(r".*invoke.*com/yandex/store.*\n"),
    # Unity IAP
    re.compile(r".*invoke.*UnityPurchasing.*\n"),
    re.compile(r".*invoke.*IStoreListener.*\n"),
    re.compile(r".*invoke.*IExtensionProvider.*\n"),
    # Facebook IAP
    re.compile(r".*invoke.*PurchaseWithProduct.*\n"),
    # Adjust wrapper
    re.compile(r".*invoke.*onTrackedPurchase.*\n"),
)


# Prefilter keywords cho patch_extreme
_EXTREME_PREFILTER_KEYWORDS = (
    "LicenseChecker", "ILicensingService", "checkLicense",
    "getBuyIntent", "launchBillingFlow", "queryPurchases",
    "com/amazon/venezia", "com/sec/android/iap",
    "com/huawei/hms/iap", "com/yandex/store",
    "UnityPurchasing",
)


_PATH_HINTS_EXTREME = (
    "license", "licensing", "lvl",
    "billing", "purchase", "iap", "store",
    "amazon", "samsung", "huawei", "yandex",
    "unity", "facebook",
)


# ============================================================
# PATCHER
# ============================================================
class LicenseExtremePatcher(BasePatcher):
    def patch(self) -> int:
        return self.patch_extreme()

    # ============================================================
    # EXTREME — remove invoke patterns (8 stores)
    # ============================================================
    def patch_extreme(self) -> int:
        self.log("[*] [LicenseExtreme] Extreme mode (invoke removal)")

        def _transform(content: str, filepath: str) -> str | None:
            # Quick prefilter — file có ít nhất 1 signal
            if not any(k in content for k in (
                "LicenseChecker", "ILicensingService", "checkLicense",
                "getBuyIntent", "launchBillingFlow", "queryPurchases",
                "com/amazon/venezia", "com/sec/android/iap",
                "com/huawei/hms/iap", "com/yandex/store",
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
            prefilter_keywords=_EXTREME_PREFILTER_KEYWORDS,
            path_hints=_PATH_HINTS_EXTREME,
            label="LicenseExtreme",
        )

    # ============================================================
    # PATTERN — bindService-based LVL (obfuscation-resistant)
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

    def patch_huawei_apps(self) -> int:
        return self._patch_by_keyword(
            ("huawei", "hms", "com/huawei/hms/iap"), "Huawei",
        )

    def patch_yandex_apps(self) -> int:
        return self._patch_by_keyword(
            ("yandex", "com/yandex/store"), "Yandex",
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